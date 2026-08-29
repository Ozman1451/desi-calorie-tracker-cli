"""
llm/prompts.py
──────────────
Single responsibility: Centralised store of ALL prompt templates.  No prompt
text lives in any other file.  Flow and logic files reference these functions
by name — they never construct prompt strings inline.

Functions:
  build_parser_prompt(dishes, buckets, raw_text)          → str  (Call B)
  build_correction_prompt(dishes, buckets, raw_text, prior_state) → str  (Call C)
  TRANSCRIPTION_PROMPT                                    → str constant (Call A)

Inputs:  Structured data (dish list, bucket table, raw text, optional prior state).
Outputs: Complete, ready-to-send prompt strings.
"""

import json
from core.models import DishSummary, ParsedMeal


# ── Call A — Transcription prompt (static constant) ───────────────────────────

TRANSCRIPTION_PROMPT: str = (
    "Transcribe this audio exactly as spoken. "
    "Output only the transcript text — no commentary, no punctuation correction, "
    "no paraphrasing. Preserve Urdu/Pashto/Punjabi words as-is using Roman script."
)


# ── Shared base instructions injected into both parser and correction prompts ──

_DISH_MATCHING_INSTRUCTIONS = """\
## Dish Matching Rules
- Match the user's description to ONE dish from the list below using the dish's
  display_name AND its synonyms.
- Be generous: "chicken kadai", "kadhi", "karahi gosht" should all match Chicken Karahi.
- Urdu/Punjabi/Pashto words are expected — match phonetically if needed.
- Set confidence:
    "high"   — clearly identified dish, strong match
    "medium" — plausible match but some ambiguity (e.g. dish name partially used)
    "low"    — no confident match found
- If confidence = "low", set matched = false and do NOT guess a dish_id.
"""

_PORTION_INSTRUCTIONS = """\
## Portion Extraction Rules
- Map the user's size description to the closest bucket_label from the table below.
- Default to "normal_plate" if no size is mentioned.
- Common mappings:
    "ek plate" / "normal" / no size mentioned → normal_plate
    "thoda sa" / "katori" / "half" → katori or half_plate
    "chota" / "choti plate" → chota_plate
    "bara" / "bari plate" / "full" → bara_plate
    "zyada" / "extra" / "derhh plate" → plate_and_a_half
- Set scale_factor_applied to the numeric value from the table for that bucket.
"""

_OVERRIDE_INSTRUCTIONS = """\
## Override Extraction Rules
- Identify ingredient quantities EXPLICITLY stated by the user.
- Examples:
    "3 pieces of chicken" → {"ingredient": "chicken_bone_in", "unit": "piece", "qty": 3}
    "4 boti" → {"ingredient": "chicken_boneless", "unit": "piece", "qty": 4}
    "2 chapli kebabs" → {"ingredient": "beef_mince", "unit": "piece", "qty": 2}
- For bucket-type ingredients (sauces, gravy, rice, oil) only create an override
  if the user gives an explicit gram or portion amount.
- "extra oil" or "thoda zyada" alone is NOT an override — only explicit quantities.
- Use the exact ingredient_name from the dish's ingredient list (shown in the dish catalogue below).
"""

_OUTPUT_FORMAT = """\
## Output Format
Return ONLY a valid JSON object — no markdown fences, no commentary.

If the dish is matched (confidence = "high" or "medium"):
{
  "matched": true,
  "dish_id": "<dish_id>",
  "confidence": "high" | "medium",
  "portion_bucket": "<bucket_label>",
  "scale_factor_applied": <float>,
  "overrides": [
    {"ingredient": "<ingredient_name>", "unit": "piece" | "grams", "qty": <number>}
  ],
  "assumption_summary": "<user-friendly explanation of assumed portion, overrides, and defaults>"
}

If no confident match (confidence = "low"):
{
  "matched": false,
  "confidence": "low",
  "raw_text": "<original user input verbatim>"
}

The assumption_summary MUST be written as if speaking to the user — clear, specific,
and in plain English. Example: "Matched to Chicken Karahi. Assumed normal plate (1×
standard recipe, ~558g). Chicken overridden to 3 pieces (~300g). All other
ingredients at standard proportions."
"""


# ── Call B — Parser prompt ────────────────────────────────────────────────────

def build_parser_prompt(
    dishes: list[DishSummary],
    buckets: dict[str, float],
    raw_text: str,
) -> str:
    """
    Build the full system + user prompt for Call B (dish match + portion parse).

    Args:
        dishes:    All dishes from get_all_dishes_for_prompt().
        buckets:   Portion bucket vocabulary from get_portion_scale_factors().
        raw_text:  The user's meal description (typed or transcribed).

    Returns:
        Complete prompt string ready to send to Gemini.
    """
    dish_catalogue = json.dumps(
        [
            {
                "dish_id": d.dish_id,
                "display_name": d.display_name,
                "synonyms": d.synonyms,
                "category": d.category,
            }
            for d in dishes
        ],
        indent=2,
        ensure_ascii=False,
    )

    bucket_table = json.dumps(
        [{"bucket_label": k, "scale_factor": v} for k, v in sorted(buckets.items(), key=lambda x: x[1])],
        indent=2,
    )

    return f"""\
You are a precise nutrition tracking assistant for Pakistani and Desi cuisine.
Analyse the user's meal description and extract structured meal data.

{_DISH_MATCHING_INSTRUCTIONS}
{_PORTION_INSTRUCTIONS}
{_OVERRIDE_INSTRUCTIONS}
{_OUTPUT_FORMAT}

## Available Dishes (dish catalogue)
{dish_catalogue}

## Portion Bucket Vocabulary
{bucket_table}

## User's Meal Description
"{raw_text}"
"""


# ── Call C — Correction re-parse prompt ──────────────────────────────────────

def build_correction_prompt(
    dishes: list[DishSummary],
    buckets: dict[str, float],
    correction_text: str,
    prior_state: ParsedMeal,
) -> str:
    """
    Build the prompt for Call C (fuzzy correction re-parse).
    The prior parsed state is included so the model amends rather than
    re-derives from scratch.

    Args:
        dishes:           Full dish catalogue (same as parser prompt).
        buckets:          Portion bucket vocabulary.
        correction_text:  The user's free-text correction (e.g. "make it bara plate").
        prior_state:      The current ParsedMeal that the user wants to correct.

    Returns:
        Complete prompt string for the correction call.
    """
    prior_json = prior_state.model_dump_json(indent=2)

    dish_catalogue = json.dumps(
        [
            {
                "dish_id": d.dish_id,
                "display_name": d.display_name,
                "synonyms": d.synonyms,
                "category": d.category,
            }
            for d in dishes
        ],
        indent=2,
        ensure_ascii=False,
    )

    bucket_table = json.dumps(
        [{"bucket_label": k, "scale_factor": v} for k, v in sorted(buckets.items(), key=lambda x: x[1])],
        indent=2,
    )

    return f"""\
You are a precise nutrition tracking assistant for Pakistani and Desi cuisine.
The user previously logged a meal that was parsed into the JSON state below.
They are now providing a CORRECTION — amend only what they explicitly change.

## Prior Parsed State (DO NOT change fields the user does not mention)
{prior_json}

## Amendment Rules
- If the user changes the portion only (e.g. "make it bara plate"):
    Update portion_bucket and scale_factor_applied only. Keep overrides unchanged.
- If the user changes an ingredient quantity (e.g. "I had 4 pieces of chicken"):
    Update or add the relevant override only. Keep portion_bucket unchanged.
- If the user changes the dish entirely, update dish_id and reset overrides.
- Always update assumption_summary to reflect the corrected full picture.
- Return the COMPLETE corrected JSON (same schema as before), not just the delta.

{_DISH_MATCHING_INSTRUCTIONS}
{_PORTION_INSTRUCTIONS}
{_OVERRIDE_INSTRUCTIONS}
{_OUTPUT_FORMAT}

## Available Dishes (dish catalogue)
{dish_catalogue}

## Portion Bucket Vocabulary
{bucket_table}

## User's Correction Text
"{correction_text}"
"""
