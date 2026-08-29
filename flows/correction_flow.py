"""
flows/correction_flow.py
─────────────────────────
Single responsibility: Implement the two correction paths after a meal is
initially parsed and displayed.

Path 1 — Manual edit:
  User picks an ingredient from the current breakdown and types a new gram value.
  No LLM call.  Returns the updated ingredient_breakdown_g dict directly.

Path 2 — Fuzzy / talk-to-fix:
  User types a free-text correction.  Calls the LLM re-parser (Call C) with
  the prior parsed state as context, returning an amended ParsedMeal.

Inputs:
  For manual:  dish (DishRow), ingredient_breakdown_g (dict)
  For fuzzy:   correction_text (str), prior_state (ParsedMeal)

Outputs:
  Manual: updated dict[str, float]
  Fuzzy:  updated ParsedMeal
"""

from core.models import DishRow, ParsedMeal
from llm.parser import reparse_with_correction


# ── Path 1: Manual edit ───────────────────────────────────────────────────────

def run_manual_edit(
    dish: DishRow,
    ingredient_breakdown_g: dict[str, float],
) -> dict[str, float]:
    """
    Interactively let the user edit individual ingredient gram values.

    Displays a numbered list of current ingredients and their grams.
    User picks a number, enters new grams.  Loops until user types 'done'.

    Args:
        dish:                    The current dish (used only for ingredient names).
        ingredient_breakdown_g:  Current {ingredient_name: grams} mapping.

    Returns:
        Updated ingredient breakdown dict.
    """
    # Work on a copy — don't mutate the original until user confirms
    breakdown = dict(ingredient_breakdown_g)
    ingredient_names = list(breakdown.keys())

    while True:
        print("\n  ┌─ Current Ingredient Breakdown ──────────────────────")
        for i, (name, grams) in enumerate(breakdown.items(), start=1):
            print(f"  │  {i:2d}. {name:<30s}  {grams:>7.1f} g")
        print("  └─────────────────────────────────────────────────────")
        print("  Enter ingredient number to edit, or 'done' to finish:")

        raw = input("  > ").strip().lower()
        if raw in ("done", "d", ""):
            break

        try:
            idx = int(raw) - 1
            if not (0 <= idx < len(ingredient_names)):
                print("  ⚠  Invalid number. Try again.")
                continue
        except ValueError:
            print("  ⚠  Please enter a number or 'done'.")
            continue

        ingredient = ingredient_names[idx]
        current_grams = breakdown[ingredient]

        try:
            new_grams_raw = input(
                f"  New grams for {ingredient} (currently {current_grams:.1f}g): "
            ).strip()
            new_grams = float(new_grams_raw)
            if new_grams < 0:
                print("  ⚠  Grams cannot be negative.")
                continue
            breakdown[ingredient] = new_grams
            print(f"  ✓  Updated {ingredient} → {new_grams:.1f}g")
        except ValueError:
            print("  ⚠  Please enter a valid number.")
            continue

    return breakdown


# ── Path 2: Fuzzy correction via LLM (Call C) ─────────────────────────────────

def run_fuzzy_correction(
    correction_text: str,
    prior_state: ParsedMeal,
) -> ParsedMeal:
    """
    Send the user's free-text correction to the LLM (Call C) for re-parsing.
    The prior parsed state is included as context so the model only amends
    what the user explicitly changes.

    Args:
        correction_text:  User's natural-language correction.
        prior_state:      Current ParsedMeal (dish_id, portion_bucket, overrides).

    Returns:
        Amended ParsedMeal.  If the LLM cannot parse the correction, the original
        prior_state is returned unchanged and a warning is printed.
    """
    try:
        updated = reparse_with_correction(correction_text, prior_state)
        return updated
    except Exception as exc:
        print(f"\n  ⚠  Could not apply correction: {exc}")
        print("  Keeping previous values. Try manual edit instead.")
        return prior_state
