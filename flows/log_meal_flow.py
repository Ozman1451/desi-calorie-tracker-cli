"""
flows/log_meal_flow.py
───────────────────────
Single responsibility: Orchestrate the full end-to-end meal logging pipeline
as specified in blueprint §7.

Pipeline steps:
  1. Resolve input mode (text arg vs. voice recording)
  2. [Voice] Record mic → WAV → Gemini transcription (Call A) → raw_text
     [Text]  raw_text = CLI argument directly
  3. Call B: parse_meal(raw_text) → ParsedMeal
  4. If matched=False → queue unknown dish, print message, exit
  5. DB fetch: get_dish_with_ingredients(dish_id) → DishRow
  6. merge_engine.merge(dish, scale_factor, overrides) → ingredient_breakdown_g
  7. nutrition_calc.compute_macros(dish, breakdown) → MacroTotals
  8. Print full breakdown + macros + assumption_summary to terminal
  9. Correction loop: [m]anual / [t]alk-to-fix / [s]ave / [d]iscard
 10. Every external call is wrapped with core/timing.py instrumentation.

Inputs:  input_mode ('text'|'voice'), text_input (str, for text mode).
Outputs: Side-effects only — meal logged to DB or discarded.
"""

import logging
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config.settings import DEFAULT_USER_ID
from core.merge_engine import merge
from core.models import MealLogInsert, ParsedMeal, DishRow, MacroTotals
from core.nutrition_calc import compute_macros
from core.timing import timer, timed
from db.dish_repository import get_dish_with_ingredients
from db.meal_repository import insert_meal_log, insert_unknown_dish
from flows.correction_flow import run_manual_edit, run_fuzzy_correction
from llm.parser import parse_meal

logger = logging.getLogger(__name__)


# ── Display helpers ───────────────────────────────────────────────────────────

def _safe_print(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback to ascii/latin1-safe string
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _print_separator(char: str = "─", width: int = 58) -> None:
    try:
        print(f"  {char * width}")
    except UnicodeEncodeError:
        fallback_char = "=" if char == "═" else "-"
        print(f"  {fallback_char * width}")


def _display_results(
    dish: DishRow,
    parsed: ParsedMeal,
    breakdown: dict[str, float],
    macros: MacroTotals,
) -> None:
    """Print the full meal summary to the terminal."""
    _safe_print()
    _print_separator("═")
    _safe_print(f"  📋  {dish.display_name}  ({parsed.portion_bucket or 'normal_plate'})")
    _print_separator()

    _safe_print("  Ingredient Breakdown:")
    for name, grams in breakdown.items():
        _safe_print(f"    • {name:<30s}  {grams:>7.1f} g")

    _print_separator()
    _safe_print("  Macro Totals:")
    rounded = macros.model_dump_rounded()
    _safe_print(f"    🔥 Calories  {rounded['calories']:>7.1f} kcal")
    _safe_print(f"    💪 Protein   {rounded['protein_g']:>7.1f} g")
    _safe_print(f"    🌾 Carbs     {rounded['carbs_g']:>7.1f} g")
    _safe_print(f"    🧈 Fat       {rounded['fat_g']:>7.1f} g")

    _print_separator()
    if parsed.assumption_summary:
        _safe_print(f"  ℹ  Assumptions: {parsed.assumption_summary}")
    _print_separator("═")


# ── Main flow ─────────────────────────────────────────────────────────────────

def run_log_meal_flow(input_mode: str, text_input: str | None = None) -> None:
    """
    Execute the full meal logging pipeline end-to-end.

    Args:
        input_mode:  'text' or 'voice'.
        text_input:  The meal description string (required when input_mode='text').
    """
    _safe_print()
    _safe_print("  =======================================================")
    _safe_print("  🍛  Desi Calorie Tracker v1")
    _safe_print("  =======================================================")

    # ── Step 1-2: Resolve raw_input_text ─────────────────────────────────────
    raw_text: str

    if input_mode == "voice":
        from audio.recorder import record_audio
        from audio.transcriber import transcribe_audio

        with timer("Voice: record audio"):
            audio_path = record_audio()

        raw_text = transcribe_audio(audio_path)

    elif input_mode == "text":
        if not text_input:
            _safe_print("  ✗  No meal text provided. Use --text \"your meal description\".")
            return
        raw_text = text_input.strip()
        _safe_print(f"\n  📝  Input: \"{raw_text}\"")

    else:
        raise ValueError(f"Unknown input_mode: '{input_mode}'. Must be 'text' or 'voice'.")

    # ── Step 3: Parse meal via LLM (Call B) ───────────────────────────────────
    _safe_print("\n  🔍  Parsing meal...")
    parsed = parse_meal(raw_text)

    # ── Step 4: Handle unmatched dish ─────────────────────────────────────────
    if not parsed.matched:
        _safe_print(
            f"\n  ✗  Couldn't recognize \"{raw_text}\" as a known dish "
            f"(confidence: {parsed.confidence})."
        )
        _safe_print("  ℹ  This has been added to our dish request queue for future support.")
        with timer("DB: insert unknown dish"):
            insert_unknown_dish(raw_text)
        return

    _safe_print(f"\n  ✓  Matched: {parsed.dish_id} (confidence: {parsed.confidence})")

    # ── Step 5: Fetch full dish data from DB ──────────────────────────────────
    dish: DishRow | None
    with timer("DB: fetch dish with ingredients"):
        dish = get_dish_with_ingredients(parsed.dish_id)

    if dish is None:
        _safe_print(f"\n  ✗  Dish '{parsed.dish_id}' matched but not found in DB. Aborting.")
        return

    # ── Step 6: Merge (deterministic — no LLM) ───────────────────────────────
    scale_factor = parsed.scale_factor_applied or 1.0
    breakdown = merge(dish, scale_factor, parsed.overrides)

    # ── Step 7: Compute macros ────────────────────────────────────────────────
    macros = compute_macros(dish, breakdown)

    # ── Step 8: Display results ───────────────────────────────────────────────
    _display_results(dish, parsed, breakdown, macros)

    # ── Step 9: Correction loop ───────────────────────────────────────────────
    correction_count = 0

    while True:
        _safe_print()
        choice = input(
            "  Action → [m]anual edit / [t]alk to fix / [s]ave / [d]iscard: "
        ).strip().lower()

        # ── Manual edit ───────────────────────────────────────────────────────
        if choice == "m":
            breakdown = run_manual_edit(dish, breakdown)
            macros = compute_macros(dish, breakdown)
            _display_results(dish, parsed, breakdown, macros)
            correction_count += 1

        # ── Talk / fuzzy correction (Call C) ──────────────────────────────────
        elif choice == "t":
            correction_text = input("  Describe your correction: ").strip()
            if not correction_text:
                _safe_print("  ⚠  No correction text entered. Skipping.")
                continue

            _safe_print("\n  🔄  Applying correction...")
            updated_parsed = run_fuzzy_correction(correction_text, parsed)

            # If dish changed, re-fetch dish data
            if updated_parsed.dish_id and updated_parsed.dish_id != dish.dish_id:
                with timer("DB: re-fetch dish after correction"):
                    new_dish = get_dish_with_ingredients(updated_parsed.dish_id)
                if new_dish:
                    dish = new_dish
                else:
                    _safe_print(f"  ⚠  Corrected dish_id '{updated_parsed.dish_id}' not found — keeping original dish.")
                    updated_parsed = parsed  # revert dish change

            parsed = updated_parsed
            scale_factor = parsed.scale_factor_applied or 1.0
            breakdown = merge(dish, scale_factor, parsed.overrides)
            macros = compute_macros(dish, breakdown)
            _display_results(dish, parsed, breakdown, macros)
            correction_count += 1

        # ── Save to DB ────────────────────────────────────────────────────────
        elif choice == "s":
            meal_log = MealLogInsert(
                user_id=DEFAULT_USER_ID,
                dish_id=dish.dish_id,
                input_mode=input_mode,
                raw_input_text=raw_text,
                portion_bucket=parsed.portion_bucket,
                scale_factor_applied=scale_factor,
                overrides=parsed.overrides,
                ingredient_breakdown_g=breakdown,
                macro_totals=macros,
                assumption_summary=parsed.assumption_summary,
                correction_count=correction_count,
            )
            with timer("DB: insert meal log"):
                log_id = insert_meal_log(meal_log)
            _safe_print(f"\n  ✅  Meal logged! (id: {log_id})")
            _safe_print(f"  📊  {macros.model_dump_rounded()['calories']:.0f} kcal saved for {DEFAULT_USER_ID}.")
            break

        # ── Discard ───────────────────────────────────────────────────────────
        elif choice == "d":
            _safe_print("\n  🗑  Discarded. Nothing saved.")
            break

        else:
            _safe_print("  ⚠  Invalid choice. Enter m, t, s, or d.")
