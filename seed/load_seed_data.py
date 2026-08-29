"""
seed/load_seed_data.py
───────────────────────
Single responsibility: Read dishes_seed.json and upsert all seed data into
the Supabase database in correct dependency order.

Dependency order (FK constraints):
  1. ingredients_master   (no dependencies)
  2. portion_scale_factors (no dependencies)
  3. dishes               (no dependencies)
  4. dish_ingredients     (depends on dishes + ingredients_master)

Run this once after creating the schema:
  python seed/load_seed_data.py

Safe to re-run (upserts, not plain inserts).

Inputs:  seed/dishes_seed.json
Outputs: Populated Supabase tables.
"""

import json
import sys
from pathlib import Path

# ── Ensure project root is on sys.path so config/db imports work ──────────────
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import TABLE_NAMES
from db.client import supabase

_SEED_FILE = Path(__file__).parent / "dishes_seed.json"


def _upsert(table: str, rows: list[dict], conflict_column: str) -> int:
    """
    Upsert a list of rows into a Supabase table.
    Returns the count of rows processed.
    """
    if not rows:
        return 0
    result = (
        supabase
        .table(table)
        .upsert(rows, on_conflict=conflict_column)
        .execute()
    )
    return len(result.data) if result.data else len(rows)


def load_seed_data() -> None:
    """Load all seed data into Supabase in correct dependency order."""
    print("─" * 60)
    print("  Desi Calorie Tracker v1 — Seed Loader")
    print("─" * 60)

    with open(_SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)

    # ── 1. ingredients_master ────────────────────────────────────────────────
    ing_rows = seed["ingredients_master"]
    count = _upsert(TABLE_NAMES["ingredients_master"], ing_rows, "ingredient_name")
    print(f"  ✓  ingredients_master    : {count:3d} rows upserted")

    # ── 2. portion_scale_factors ─────────────────────────────────────────────
    bucket_rows = seed["portion_scale_factors"]
    count = _upsert(TABLE_NAMES["portion_scale_factors"], bucket_rows, "bucket_label")
    print(f"  ✓  portion_scale_factors : {count:3d} rows upserted")

    # ── 3. dishes ────────────────────────────────────────────────────────────
    dish_rows = [
        {
            "dish_id":                     d["dish_id"],
            "display_name":                d["display_name"],
            "synonyms":                    d["synonyms"],
            "category":                    d["category"],
            "default_portion_label":       d["default_portion_label"],
            "default_portion_total_grams": d["default_portion_total_grams"],
        }
        for d in seed["dishes"]
    ]
    count = _upsert(TABLE_NAMES["dishes"], dish_rows, "dish_id")
    print(f"  ✓  dishes                : {count:3d} rows upserted")

    # ── 4. dish_ingredients ──────────────────────────────────────────────────
    #   Build flat ingredient rows from each dish's ingredients list.
    #   We delete existing rows for each dish_id first to ensure clean upsert
    #   (dish_ingredients has a BIGSERIAL PK, not a natural unique key, so
    #   we use delete-then-insert pattern for idempotency).
    dish_ing_rows: list[dict] = []
    for dish in seed["dishes"]:
        dish_id = dish["dish_id"]
        for ing in dish["ingredients"]:
            row: dict = {
                "dish_id":         dish_id,
                "ingredient_name": ing["ingredient_name"],
                "scaling_type":    ing["scaling_type"],
                "default_grams":   ing.get("default_grams"),
                "avg_unit_grams":  ing.get("avg_unit_grams"),
                "default_count":   ing.get("default_count"),
            }
            dish_ing_rows.append(row)

    # Clear existing dish_ingredients before re-inserting (idempotent)
    all_dish_ids = [d["dish_id"] for d in seed["dishes"]]
    supabase.table(TABLE_NAMES["dish_ingredients"]).delete().in_("dish_id", all_dish_ids).execute()

    # Insert in batches of 50 to stay within Supabase payload limits
    total_inserted = 0
    batch_size = 50
    for i in range(0, len(dish_ing_rows), batch_size):
        batch = dish_ing_rows[i : i + batch_size]
        result = supabase.table(TABLE_NAMES["dish_ingredients"]).insert(batch).execute()
        total_inserted += len(result.data) if result.data else len(batch)
    print(f"  ✓  dish_ingredients      : {total_inserted:3d} rows inserted")

    print("─" * 60)
    print("  ✅  Seed data loaded successfully.")
    print(f"  📦  {len(seed['dishes'])} dishes, {len(ing_rows)} ingredients, {len(bucket_rows)} portion buckets.")
    print("─" * 60)


if __name__ == "__main__":
    load_seed_data()
