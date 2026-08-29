"""
core/nutrition_calc.py
──────────────────────
Single responsibility: Convert a final ingredient gram breakdown into macro
totals (calories, protein, carbs, fat).

Formula (per blueprint §6):
  For each ingredient:  grams × (nutrition_per_100g / 100)
  Sum across all ingredients → MacroTotals

Inputs:
  dish              (DishRow)          — provides per-100g nutrition values
  ingredient_breakdown_g (dict)        — {ingredient_name: grams} from merge_engine

Outputs:
  MacroTotals — {calories, protein_g, carbs_g, fat_g}
"""

import logging
from core.models import DishRow, MacroTotals

logger = logging.getLogger(__name__)


def compute_macros(
    dish: DishRow,
    ingredient_breakdown_g: dict[str, float],
) -> MacroTotals:
    """
    Compute aggregate macro totals for a meal from per-ingredient gram amounts.

    Args:
        dish:                    Full dish row (carries per-100g nutrition data).
        ingredient_breakdown_g:  Final grams per ingredient after merge + overrides.

    Returns:
        MacroTotals with summed calories, protein_g, carbs_g, fat_g.
    """
    # Build a lookup from ingredient_name → nutrition data
    nutrition_map = {ing.ingredient_name: ing for ing in dish.ingredients}

    total_calories: float = 0.0
    total_protein: float = 0.0
    total_carbs: float = 0.0
    total_fat: float = 0.0

    for ingredient_name, grams in ingredient_breakdown_g.items():
        ing = nutrition_map.get(ingredient_name)
        if ing is None:
            logger.warning(
                "Nutrition data not found for '%s' — skipping in macro total.",
                ingredient_name,
            )
            continue

        factor = grams / 100.0
        total_calories += ing.calories_per_100g * factor
        total_protein += ing.protein_g_per_100g * factor
        total_carbs += ing.carbs_g_per_100g * factor
        total_fat += ing.fat_g_per_100g * factor

    return MacroTotals(
        calories=total_calories,
        protein_g=total_protein,
        carbs_g=total_carbs,
        fat_g=total_fat,
    )
