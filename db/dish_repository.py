"""
db/dish_repository.py
─────────────────────
Single responsibility: Read dish data from Supabase — catalogue for LLM prompt
injection and full ingredient+nutrition data for the merge engine.

Inputs:  dish_id (str) or no args for full list.
Outputs: DishSummary list (for prompts) | DishRow (for merge engine) |
         dict[str, float] (portion scale factors).
"""

from typing import Optional
from core.models import DishSummary, DishRow, DishIngredientFull
from config.settings import TABLE_NAMES
from db.client import supabase


def get_all_dishes_for_prompt() -> list[DishSummary]:
    """
    Return lightweight dish summaries (id, display_name, synonyms, category)
    for injection into the LLM parser prompt.
    """
    result = (
        supabase
        .table(TABLE_NAMES["dishes"])
        .select("dish_id, display_name, synonyms, category")
        .execute()
    )
    return [
        DishSummary(
            dish_id=row["dish_id"],
            display_name=row["display_name"],
            synonyms=row.get("synonyms") or [],
            category=row["category"],
        )
        for row in result.data
    ]


def get_dish_with_ingredients(dish_id: str) -> Optional[DishRow]:
    """
    Return a full DishRow (dish meta + all ingredients with nutrition data)
    for a given dish_id.  Returns None if not found.

    Uses Supabase's PostgREST nested select to join dish_ingredients with
    ingredients_master in a single round-trip.
    """
    # ── Fetch dish metadata ──────────────────────────────────────────────────
    dish_result = (
        supabase
        .table(TABLE_NAMES["dishes"])
        .select("*")
        .eq("dish_id", dish_id)
        .single()
        .execute()
    )
    if not dish_result.data:
        return None

    dish_data = dish_result.data

    # ── Fetch ingredients joined with nutrition ──────────────────────────────
    # PostgREST nested select: dish_ingredients + inline ingredients_master
    ing_result = (
        supabase
        .table(TABLE_NAMES["dish_ingredients"])
        .select("*, ingredients_master(*)")
        .eq("dish_id", dish_id)
        .execute()
    )

    ingredients: list[DishIngredientFull] = []
    for row in ing_result.data:
        nutrition = row.get("ingredients_master") or {}
        ingredients.append(
            DishIngredientFull(
                ingredient_name=row["ingredient_name"],
                scaling_type=row["scaling_type"],
                default_grams=row.get("default_grams"),
                avg_unit_grams=row.get("avg_unit_grams"),
                default_count=row.get("default_count"),
                calories_per_100g=nutrition.get("calories_per_100g", 0.0),
                protein_g_per_100g=nutrition.get("protein_g_per_100g", 0.0),
                carbs_g_per_100g=nutrition.get("carbs_g_per_100g", 0.0),
                fat_g_per_100g=nutrition.get("fat_g_per_100g", 0.0),
            )
        )

    return DishRow(
        dish_id=dish_data["dish_id"],
        display_name=dish_data["display_name"],
        synonyms=dish_data.get("synonyms") or [],
        category=dish_data["category"],
        default_portion_label=dish_data["default_portion_label"],
        default_portion_total_grams=float(dish_data["default_portion_total_grams"]),
        ingredients=ingredients,
    )


def get_portion_scale_factors() -> dict[str, float]:
    """
    Return the full portion bucket vocabulary as {bucket_label: scale_factor}.
    Read from the DB at runtime — changing a scale factor in the DB requires
    no code change.
    """
    result = (
        supabase
        .table(TABLE_NAMES["portion_scale_factors"])
        .select("bucket_label, scale_factor")
        .execute()
    )
    return {row["bucket_label"]: float(row["scale_factor"]) for row in result.data}
