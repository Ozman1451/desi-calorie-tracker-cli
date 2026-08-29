-- ═══════════════════════════════════════════════════════════════════════════
-- Desi Calorie Tracker v1 — Postgres / Supabase Schema
-- Run this entire file in your Supabase SQL editor (Project → SQL Editor).
-- All tables are created fresh; run DROP TABLE statements first if re-seeding.
-- ═══════════════════════════════════════════════════════════════════════════


-- ── 1. Shared ingredient nutrition table ─────────────────────────────────────
--   Normalized: ingredients are shared across dishes (chicken, onion, oil etc.)
--   avoiding duplicate nutrition data entries.
CREATE TABLE IF NOT EXISTS ingredients_master (
    ingredient_name    TEXT PRIMARY KEY,
    calories_per_100g  NUMERIC NOT NULL,
    protein_g_per_100g NUMERIC NOT NULL,
    carbs_g_per_100g   NUMERIC NOT NULL,
    fat_g_per_100g     NUMERIC NOT NULL
);


-- ── 2. Dish catalogue ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dishes (
    dish_id                    TEXT PRIMARY KEY,
    display_name               TEXT NOT NULL,
    synonyms                   TEXT[] NOT NULL DEFAULT '{}',  -- injected into LLM prompt for matching
    category                   TEXT NOT NULL,                 -- 'home_cooked' | 'fast_food'
    default_portion_label      TEXT NOT NULL,                 -- e.g. 'normal_plate'
    default_portion_total_grams NUMERIC NOT NULL
);


-- ── 3. Per-dish ingredient composition at the DEFAULT portion ─────────────────
--   scaling_type:
--     'bucket' — grams scale proportionally with the portion bucket scale_factor
--     'count'  — quantity is explicitly stated (e.g. chicken pieces); uses avg_unit_grams
--
--   default_count: dish-specific default unit count for 'count' ingredients
--                  (e.g. karahi defaults to 3 chicken pieces).
--                  NULL for 'bucket' ingredients.
CREATE TABLE IF NOT EXISTS dish_ingredients (
    id               BIGSERIAL PRIMARY KEY,
    dish_id          TEXT NOT NULL REFERENCES dishes(dish_id) ON DELETE CASCADE,
    ingredient_name  TEXT NOT NULL REFERENCES ingredients_master(ingredient_name),
    scaling_type     TEXT NOT NULL CHECK (scaling_type IN ('count', 'bucket')),
    default_grams    NUMERIC,        -- required when scaling_type = 'bucket'
    avg_unit_grams   NUMERIC,        -- required when scaling_type = 'count' (grams per 1 piece/unit)
    default_count    INTEGER         -- required when scaling_type = 'count' (dish-specific default qty)
);

CREATE INDEX IF NOT EXISTS idx_dish_ingredients_dish_id ON dish_ingredients(dish_id);


-- ── 4. Global portion-bucket vocabulary ──────────────────────────────────────
--   Single source of truth — read at runtime, injected into LLM prompts.
--   Changing a scale factor here requires NO code change.
CREATE TABLE IF NOT EXISTS portion_scale_factors (
    bucket_label TEXT PRIMARY KEY,
    scale_factor NUMERIC NOT NULL
);


-- ── 5. Single-user meal log ───────────────────────────────────────────────────
--   ingredient_breakdown_g and macro_totals stored as JSONB snapshots of the
--   final computed state — enables clean downstream daily/weekly aggregation
--   without recomputing from raw ingredients.
CREATE TABLE IF NOT EXISTS meal_logs (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 TEXT        NOT NULL DEFAULT 'v1_test_user',
    dish_id                 TEXT        REFERENCES dishes(dish_id),
    input_mode              TEXT        NOT NULL CHECK (input_mode IN ('text', 'voice')),
    raw_input_text          TEXT        NOT NULL,
    portion_bucket          TEXT,
    scale_factor_applied    NUMERIC,
    overrides               JSONB,       -- [{"ingredient": ..., "unit": ..., "qty": ...}, ...]
    ingredient_breakdown_g  JSONB,       -- {"ingredient_name": grams, ...}  final post-merge state
    macro_totals            JSONB,       -- {"calories": ..., "protein_g": ..., "carbs_g": ..., "fat_g": ...}
    assumption_summary      TEXT,        -- user-facing verbose description of what was assumed
    correction_count        INT         NOT NULL DEFAULT 0,
    logged_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meal_logs_user_id_logged_at ON meal_logs(user_id, logged_at DESC);


-- ── 6. Unknown dish queue ─────────────────────────────────────────────────────
--   Captures unmatched inputs so the dish catalogue can grow over time.
CREATE TABLE IF NOT EXISTS unknown_dish_queue (
    id             BIGSERIAL   PRIMARY KEY,
    raw_input_text TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
