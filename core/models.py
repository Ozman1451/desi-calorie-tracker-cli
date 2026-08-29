"""
core/models.py
──────────────
Single responsibility: Define all shared Pydantic data models used across the
pipeline.  Every module that passes structured data between stages uses these
models — validated at parse time, never passed as raw dicts across boundaries.

Key model families:
  - LLM output: ParsedMeal, Override
  - DB rows:    DishSummary, DishRow, DishIngredientFull, MealLogInsert
  - Computed:   MacroTotals
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── LLM output models ─────────────────────────────────────────────────────────

class Override(BaseModel):
    """A single user-specified ingredient override extracted by the LLM."""
    ingredient: str = Field(description="ingredient_name matching an entry in ingredients_master")
    unit: str = Field(description="'piece' for count-type ingredients, 'grams' for bucket-type")
    qty: float = Field(description="Quantity in the given unit (e.g. 3 pieces, or 200 grams)")


class ParsedMeal(BaseModel):
    """
    Structured output of the LLM parser (Call B) or correction re-parser (Call C).
    When matched=False, only confidence and raw_text are populated.
    """
    matched: bool
    dish_id: Optional[str] = None
    confidence: str = Field(description="'high' | 'medium' | 'low'")
    portion_bucket: Optional[str] = None
    scale_factor_applied: Optional[float] = None
    overrides: list[Override] = Field(default_factory=list)
    assumption_summary: Optional[str] = None
    raw_text: Optional[str] = None  # populated when matched=False


# ── DB / Repository models ────────────────────────────────────────────────────

class DishSummary(BaseModel):
    """Lightweight dish info injected into the LLM system prompt."""
    dish_id: str
    display_name: str
    synonyms: list[str]
    category: str  # 'home_cooked' | 'fast_food'


class DishIngredientFull(BaseModel):
    """
    A single ingredient row from dish_ingredients, joined with its nutrition
    data from ingredients_master.  Used by the merge engine and nutrition calc.
    """
    ingredient_name: str
    scaling_type: str  # 'bucket' | 'count'

    # bucket-type fields
    default_grams: Optional[float] = None

    # count-type fields
    avg_unit_grams: Optional[float] = None
    default_count: Optional[int] = None

    # from ingredients_master (joined)
    calories_per_100g: float
    protein_g_per_100g: float
    carbs_g_per_100g: float
    fat_g_per_100g: float


class DishRow(BaseModel):
    """Complete dish entity with all ingredient compositions."""
    dish_id: str
    display_name: str
    synonyms: list[str]
    category: str
    default_portion_label: str
    default_portion_total_grams: float
    ingredients: list[DishIngredientFull]


class MacroTotals(BaseModel):
    """Final computed macro totals for a meal."""
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float

    def model_dump_rounded(self, decimals: int = 1) -> dict[str, float]:
        """Return a dict with values rounded to `decimals` places."""
        return {
            "calories": round(self.calories, decimals),
            "protein_g": round(self.protein_g, decimals),
            "carbs_g": round(self.carbs_g, decimals),
            "fat_g": round(self.fat_g, decimals),
        }


class MealLogInsert(BaseModel):
    """Payload for inserting a finalized meal into meal_logs."""
    user_id: str
    dish_id: str
    input_mode: str  # 'text' | 'voice'
    raw_input_text: str
    portion_bucket: Optional[str] = None
    scale_factor_applied: Optional[float] = None
    overrides: list[Override] = Field(default_factory=list)
    ingredient_breakdown_g: dict[str, float]  # {ingredient_name: grams}
    macro_totals: MacroTotals
    assumption_summary: Optional[str] = None
    correction_count: int = 0
