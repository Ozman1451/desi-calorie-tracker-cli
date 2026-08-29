"""
core/merge_engine.py
────────────────────
Single responsibility: Deterministically compute final ingredient gram amounts
from a dish's default recipe, a portion scale factor, and any user overrides.
ALL nutrition math lives here — the LLM never touches numbers directly.

Inputs:
  dish          (DishRow)        — full recipe from DB
  scale_factor  (float)          — from portion_scale_factors table (e.g. 1.4 for bara_plate)
  overrides     (list[Override]) — explicit user ingredient quantities from LLM output

Outputs:
  dict[str, float] — {ingredient_name: final_grams} after scaling and overrides applied.

Override rules (from blueprint §5):
  - Overrides REPLACE the scaled default; they never add on top.
  - Untouched ingredients stay at their scaled-default value.
  - v1 independence assumption: overriding one ingredient does NOT auto-adjust others.
  - Override unit='piece': final_grams = qty × avg_unit_grams
  - Override unit='grams': final_grams = qty (direct gram value)
"""

import logging
from core.models import DishRow, Override

logger = logging.getLogger(__name__)


def merge(
    dish: DishRow,
    scale_factor: float,
    overrides: list[Override],
) -> dict[str, float]:
    """
    Apply portion scaling and user overrides to produce the final ingredient
    gram breakdown for a meal.

    Args:
        dish:          Full dish data including ingredient composition.
        scale_factor:  Multiplier from the portion bucket (1.0 = normal_plate).
        overrides:     Explicit user ingredient quantities parsed by the LLM.

    Returns:
        Mapping of ingredient_name → final grams (floats, ≥ 0).
    """
    result: dict[str, float] = {}

    # ── Step 1: Apply default recipe with portion scaling ─────────────────────
    for ingredient in dish.ingredients:
        if ingredient.scaling_type == "bucket":
            if ingredient.default_grams is None:
                logger.warning(
                    "Bucket ingredient '%s' in dish '%s' has no default_grams — skipping.",
                    ingredient.ingredient_name,
                    dish.dish_id,
                )
                continue
            result[ingredient.ingredient_name] = ingredient.default_grams * scale_factor

        elif ingredient.scaling_type == "count":
            if ingredient.avg_unit_grams is None or ingredient.default_count is None:
                logger.warning(
                    "Count ingredient '%s' in dish '%s' missing avg_unit_grams or default_count — skipping.",
                    ingredient.ingredient_name,
                    dish.dish_id,
                )
                continue
            # Count-type ingredients are NOT scaled by the portion bucket;
            # their quantity is determined by the user (or defaulted).
            result[ingredient.ingredient_name] = (
                ingredient.avg_unit_grams * ingredient.default_count
            )

    # ── Step 2: Apply user overrides (REPLACE, never add) ────────────────────
    override_index = {o.ingredient: o for o in overrides}

    for ingredient_name, override in override_index.items():
        # Locate the ingredient definition for avg_unit_grams lookup
        ing_def = next(
            (i for i in dish.ingredients if i.ingredient_name == ingredient_name),
            None,
        )

        if ing_def is None:
            logger.warning(
                "Override references unknown ingredient '%s' in dish '%s' — ignoring.",
                ingredient_name,
                dish.dish_id,
            )
            continue

        if override.unit == "piece":
            # Count-type override: qty × avg_unit_grams
            if ing_def.avg_unit_grams is None:
                logger.warning(
                    "Cannot apply piece override for '%s' — avg_unit_grams not set. Skipping.",
                    ingredient_name,
                )
                continue
            result[ingredient_name] = override.qty * ing_def.avg_unit_grams

        elif override.unit == "grams":
            # Direct gram override — used for bucket-type ingredients
            result[ingredient_name] = override.qty

        else:
            logger.warning(
                "Unsupported override unit '%s' for ingredient '%s' — ignoring.",
                override.unit,
                ingredient_name,
            )

    return result
