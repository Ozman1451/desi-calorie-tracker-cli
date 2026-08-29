# Desi Calorie Tracker — v1 CLI Implementation Plan

## Summary

Full implementation of the `desi-calorie-cli` prototype as specified in the blueprint. This is a terminal-based calorie tracker for Pakistani dishes, using Gemini for STT + LLM parsing, Supabase/Postgres as backend, and a deterministic merge engine for all math.

## Clarifications Resolved

| Question | Decision |
|---|---|
| Gemini model | `gemini-2.0-flash` for both Call A (transcription) and Call B (parser) |
| Voice stop mechanism | Press Enter to stop recording |
| Default unit count for `count`-type ingredients | Dish-specific `default_count` column added to `dish_ingredients` |
| 20 seed dishes | All 20 authored with real Pakistani recipes + nutrition data |
| Supabase credentials | `.env.example` with placeholders only — user fills in |

---

## Proposed Changes

### Root Files

#### [NEW] `main.py`
CLI entrypoint. Parses `--text` and `--voice` flags, delegates to `log_meal_flow.py`.

#### [NEW] `requirements.txt`
All dependencies: `supabase`, `google-generativeai`, `pydantic`, `python-dotenv`, `sounddevice`, `soundfile`, `numpy`.

#### [NEW] `.env.example`
Placeholder file with `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`, `DEFAULT_USER_ID`.

#### [NEW] `README.md`
Full setup guide, module map, and deferred-to-v2 section.

---

### `config/`

#### [NEW] `config/settings.py`
Loads `.env`, exposes `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`, `DEFAULT_USER_ID`, `GEMINI_MODEL`, `TABLE_NAMES` dict.

---

### `db/`

#### [NEW] `db/schema.sql`
Full Postgres schema: `ingredients_master`, `dishes`, `dish_ingredients` (with `default_count` column), `portion_scale_factors`, `meal_logs`, `unknown_dish_queue`.

#### [NEW] `db/client.py`
Supabase client singleton.

#### [NEW] `db/dish_repository.py`
Functions: `get_all_dishes_for_prompt()`, `get_dish_with_ingredients(dish_id)`, `get_portion_scale_factors()`.

#### [NEW] `db/meal_repository.py`
Functions: `insert_meal_log(...)`, `insert_unknown_dish(raw_text)`.

---

### `audio/`

#### [NEW] `audio/recorder.py`
Records mic input to a WAV file. Starts on call, stops when user presses Enter. Uses `sounddevice` + `soundfile`.

#### [NEW] `audio/transcriber.py`
Sends WAV to Gemini `gemini-2.0-flash` audio understanding. Returns transcript string.

---

### `llm/`

#### [NEW] `llm/gemini_client.py`
Thin wrapper around `google.generativeai`. Provides `generate_text(prompt, model)` and `generate_from_audio(audio_path, prompt, model)`.

#### [NEW] `llm/prompts.py`
All prompt templates as named constants/functions: `build_parser_prompt(dish_list, bucket_table, raw_text)`, `build_correction_prompt(dish_list, bucket_table, raw_text, prior_state)`, `TRANSCRIPTION_PROMPT`.

#### [NEW] `llm/parser.py`
Calls Call B (and Call C for correction). Loads dish list + bucket table, builds prompt, calls Gemini, parses and validates JSON response via Pydantic. Implements one retry on malformed JSON.

---

### `core/`

#### [NEW] `core/models.py`
Pydantic models: `ParsedMeal`, `Override`, `IngredientRow`, `DishRow`, `MealLogRow`, `MacroTotals`, `IngredientBreakdown`.

#### [NEW] `core/merge_engine.py`
Deterministic merge function per blueprint spec. Handles `bucket` and `count` scaling types with `default_count` from dish data.

#### [NEW] `core/nutrition_calc.py`
Computes macros from grams × per-100g values. Returns `MacroTotals`.

#### [NEW] `core/timing.py`
`@timed(label)` decorator that prints and optionally logs `[TIMING] label: Xs` to a local `latency.log` file.

---

### `flows/`

#### [NEW] `flows/log_meal_flow.py`
Full end-to-end pipeline: resolve input → (voice: record+transcribe) → parse → match check → DB fetch → merge → calc → display → [m/t/s/d] loop.

#### [NEW] `flows/correction_flow.py`
Two correction paths:
- **Manual**: user picks ingredient → types new grams → returns updated breakdown directly.
- **Fuzzy (talk)**: free-text → Call C (parser with prior state) → updated `ParsedMeal`.

---

### `seed/`

#### [NEW] `seed/dishes_seed.json`
20 Pakistani dishes (10 home-cooked, 10 fast-food) with full ingredient compositions, default portions in grams, and per-ingredient nutrition data. Dishes include: Chicken Karahi, Dal Chawal, Biryani, Nihari, Haleem, Palak Gosht, Aloo Gosht, Saag, Chicken Pulao, Dahi Chawal (home-cooked), Shawarma, Burger, Zinger, Pizza (slice), BBQ Boti, Chapli Kebab, Samosa, Paratha Roll, Naan with Qeema, Doodh Patti Chai (fast-food/street).

#### [NEW] `seed/load_seed_data.py`
Reads `dishes_seed.json`, upserts all tables in correct dependency order: `ingredients_master` → `dishes` → `dish_ingredients` → `portion_scale_factors`.

---

## Verification Plan

### Manual Verification
1. `python seed/load_seed_data.py` — all rows inserted without error
2. `python main.py --text "one plate karahi with 3 pieces of chicken"` — should match `karahi_chicken`, show macros, enter correction loop
3. `python main.py --text "biryani bara plate"` — should match biryani at 1.4× scale
4. `python main.py --text "xyz unknown dish"` — should fall through to `unknown_dish_queue`
5. `python main.py --voice` — should record mic, transcribe, then follow text path
6. Correction loop: test `m` (manual edit), `t` (talk fix), `s` (save to DB), `d` (discard)
7. Check `latency.log` exists and shows timing for each stage

### Schema Validation
Run `db/schema.sql` against Supabase SQL editor — all tables created without error.
