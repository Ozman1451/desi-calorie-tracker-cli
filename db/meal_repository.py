"""
db/meal_repository.py
─────────────────────
Single responsibility: Write meal data to Supabase — insert confirmed meal logs
and queue unrecognized dish descriptions for later catalogue expansion.

Inputs:  MealLogInsert pydantic model | raw_text string.
Outputs: The inserted row's UUID (for meal_logs) | None (for unknown queue).
"""

from core.models import MealLogInsert
from config.settings import TABLE_NAMES
from db.client import supabase


def insert_meal_log(meal: MealLogInsert) -> str:
    """
    Persist a finalized meal log to the meal_logs table.

    Returns the generated UUID of the inserted row.
    Raises on Supabase error (let the caller handle or propagate).
    """
    payload = {
        "user_id": meal.user_id,
        "dish_id": meal.dish_id,
        "input_mode": meal.input_mode,
        "raw_input_text": meal.raw_input_text,
        "portion_bucket": meal.portion_bucket,
        "scale_factor_applied": meal.scale_factor_applied,
        "overrides": [o.model_dump() for o in meal.overrides] if meal.overrides else [],
        "ingredient_breakdown_g": meal.ingredient_breakdown_g,
        "macro_totals": meal.macro_totals.model_dump(),
        "assumption_summary": meal.assumption_summary,
        "correction_count": meal.correction_count,
    }

    result = (
        supabase
        .table(TABLE_NAMES["meal_logs"])
        .insert(payload)
        .execute()
    )

    inserted = result.data[0] if result.data else {}
    return inserted.get("id", "")


def insert_unknown_dish(raw_input_text: str) -> None:
    """
    Queue an unrecognized dish description in unknown_dish_queue.
    These accumulate over time to guide dish catalogue expansion.
    """
    supabase.table(TABLE_NAMES["unknown_dish_queue"]).insert(
        {"raw_input_text": raw_input_text}
    ).execute()
