# Desi Calorie Tracker — v1 CLI Implementation Walkthrough

All modules, database definitions, seed data, core engines, and documentation specified in [desi-calorie-tracker-v1-blueprint.md](file:///d:/CalLTrack%20CLI-v1/desi-calorie-tracker-v1-blueprint.md) have been implemented and verified.

---

## 1. Summary of Delivered Components

### 📂 Root & Configuration
- **[requirements.txt](file:///d:/CalLTrack%20CLI-v1/requirements.txt)**: Core dependencies (`supabase`, `google-generativeai`, `pydantic`, `python-dotenv`, `sounddevice`, `soundfile`, `numpy`).
- **[.env.example](file:///d:/CalLTrack%20CLI-v1/.env.example)**: Environment template with placeholders for `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`, `DEFAULT_USER_ID`, `GEMINI_MODEL`, and `LATENCY_LOG_PATH`.
- **[config/settings.py](file:///d:/CalLTrack%20CLI-v1/config/settings.py)**: Central configuration loader; raises explicit errors on missing required keys.
- **[main.py](file:///d:/CalLTrack%20CLI-v1/main.py)**: CLI entrypoint handling `--text`, `--voice`, and `--debug` flags.
- **[README.md](file:///d:/CalLTrack%20CLI-v1/README.md)**: Setup guide, architecture overview, module map, seed dishes, and deferred v2 features.

### 🗄 Database Layer (`db/`)
- **[db/schema.sql](file:///d:/CalLTrack%20CLI-v1/db/schema.sql)**: Complete PostgreSQL / Supabase schema for `ingredients_master`, `dishes`, `dish_ingredients` (including `default_count` & scaling type constraints), `portion_scale_factors`, `meal_logs` (with JSONB snapshots), and `unknown_dish_queue`.
- **[db/client.py](file:///d:/CalLTrack%20CLI-v1/db/client.py)**: Singleton Supabase client.
- **[db/dish_repository.py](file:///d:/CalLTrack%20CLI-v1/db/dish_repository.py)**: Repository for fetching prompt summaries, full dish recipes joined with ingredient nutrition in a single PostgREST call, and portion scales.
- **[db/meal_repository.py](file:///d:/CalLTrack%20CLI-v1/db/meal_repository.py)**: Handlers for saving finalized meals to `meal_logs` and storing unrecognized dish text in `unknown_dish_queue`.

### 🧠 LLM & Prompts (`llm/`)
- **[llm/gemini_client.py](file:///d:/CalLTrack%20CLI-v1/llm/gemini_client.py)**: Shared Google Generative AI wrapper for text and audio understanding.
- **[llm/prompts.py](file:///d:/CalLTrack%20CLI-v1/llm/prompts.py)**: Centralized prompt templates for Call A (transcription), Call B (dish match + portion/override parser), and Call C (correction re-parser with prior state context).
- **[llm/parser.py](file:///d:/CalLTrack%20CLI-v1/llm/parser.py)**: Orchestrates LLM parsing, markdown fence cleanup, Pydantic validation, and single automatic retry upon malformed JSON.

### ⚙️ Core Engines & Timing (`core/`)
- **[core/models.py](file:///d:/CalLTrack%20CLI-v1/core/models.py)**: Pydantic schemas (`ParsedMeal`, `Override`, `DishRow`, `DishIngredientFull`, `MacroTotals`, `MealLogInsert`).
- **[core/merge_engine.py](file:///d:/CalLTrack%20CLI-v1/core/merge_engine.py)**: Deterministic recipe scaling and override replacement engine outside the LLM.
- **[core/nutrition_calc.py](file:///d:/CalLTrack%20CLI-v1/core/nutrition_calc.py)**: Converts grams per ingredient into aggregate calories, protein, carbs, and fat.
- **[core/timing.py](file:///d:/CalLTrack%20CLI-v1/core/timing.py)**: Decorator and context manager that logs execution latency to stdout and appends to `latency.log`.

### 🎙 Audio Layer (`audio/`)
- **[audio/recorder.py](file:///d:/CalLTrack%20CLI-v1/audio/recorder.py)**: Live microphone recorder using `sounddevice` with press-Enter-to-stop mechanism.
- **[audio/transcriber.py](file:///d:/CalLTrack%20CLI-v1/audio/transcriber.py)**: Sends audio to Gemini for speech-to-text (Call A) while preserving Desi cuisine terminology.

### 🔄 Flows (`flows/`)
- **[flows/log_meal_flow.py](file:///d:/CalLTrack%20CLI-v1/flows/log_meal_flow.py)**: End-to-end pipeline execution and interactive terminal display.
- **[flows/correction_flow.py](file:///d:/CalLTrack%20CLI-v1/flows/correction_flow.py)**: Interactive manual ingredient gram editing and fuzzy natural language re-parsing.

### 🌱 Seed Data (`seed/`)
- **[seed/dishes_seed.json](file:///d:/CalLTrack%20CLI-v1/seed/dishes_seed.json)**: Curated dataset of 20 authentic Pakistani dishes (10 home-cooked + 10 fast-food/street), 33 master ingredients with USDA/NIFSAT reference nutrition, and 6 standard portion buckets.
- **[seed/load_seed_data.py](file:///d:/CalLTrack%20CLI-v1/seed/load_seed_data.py)**: Idempotent database seeder with foreign key dependency ordering and batching.

---

## 2. Verification Performed

1. **Python Syntax Compilation**: All 24 `.py` files compiled cleanly with `python -m py_compile` (0 errors).
2. **Seed JSON Verification**: Verified `seed/dishes_seed.json` syntax and structure — loaded all 20 dishes, 33 ingredients, and 6 portion scale factors.
3. **CLI Interface Help**: Tested command help structure for `main.py`.

---

## 3. How to Run & Test

1. Copy `.env.example` to `.env` and fill in your Supabase & Gemini API keys:
   ```bash
   cp .env.example .env
   ```
2. Run `db/schema.sql` in the Supabase SQL Editor.
3. Seed the database:
   ```bash
   python seed/load_seed_data.py
   ```
4. Test meal logging via CLI:
   ```bash
   python main.py --text "one plate karahi with 3 pieces of chicken"
   python main.py --voice
   ```
