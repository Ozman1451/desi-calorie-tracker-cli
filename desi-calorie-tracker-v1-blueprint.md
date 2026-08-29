# Desi Calorie Tracker — v1 CLI Prototype Blueprint

## Purpose & Scope

Test and perfect the **core parsing → scaling → merge → macro** workflow and its latency, before building the mobile app. This is a terminal-based harness against a real online backend (Supabase/Postgres) — everything except UI and user management is built to first-release quality.

**In scope (v1):**
- Text input AND live mic voice input
- Two-call STT architecture: audio → transcript (Gemini), transcript → structured parse (Gemini) — same code path handles both input modes from the transcript stage onward
- LLM parser: dish matching + portion-bucket scaling (LLM-steered via fixed scale factors) + ingredient overrides + verbose assumption reporting
- Deterministic backend merge engine (all math outside the LLM)
- Nutrition/macro calculation
- Correction loop: both manual (direct field edit) and fuzzy (talk to the LLM) — both converge on the same merge engine
- Supabase (Postgres) hosted online, sized for first ~1000 users
- 20 dummy Pakistani dishes (home-cooked + fast food), seeded with agreed-upon standard recipes and portion sizes
- Single fixed user entity — one `user_id`, no auth — meals logged consistently across a day for later analysis
- Latency instrumentation at every stage (this is a primary goal of v1)

**Explicitly out of scope (v1):**
- Mobile app / any UI beyond terminal
- User accounts, auth, multi-user management
- Vision/photo-based portion estimation
- Persistent per-user calibration memory (correction is stateless — helps immediately, not stored as a learned multiplier yet)
- Manual weighing/photo-based calibration data — v1 uses agreed-upon trusted-source estimates instead

**CLI contract:**
```
python main.py --text "one plate karahi with 3 pieces of chicken"
python main.py --voice
```
One command = one meal logged. No persistent REPL in v1.

---

## 1. Directory Structure

```
/desi-calorie-cli
  /config
    settings.py            # env loading, model names, default user_id, constants
  /db
    schema.sql              # Postgres/Supabase table definitions
    client.py               # Supabase client init
    dish_repository.py      # read dish + ingredient + portion-bucket data
    meal_repository.py      # insert/update meal_logs, unknown_dish_queue
  /audio
    recorder.py              # live mic recording -> local wav file
    transcriber.py            # Gemini audio understanding call -> transcript text
  /llm
    gemini_client.py          # thin shared wrapper around Gemini API calls
    parser.py                 # combined dish-match + portion/override extraction call
    prompts.py                 # ALL system prompt templates, centralized
  /core
    merge_engine.py            # deterministic: scale recipe, apply overrides
    nutrition_calc.py          # grams -> macros using per-100g nutrition data
    models.py                  # pydantic models for all data shapes
    timing.py                  # latency instrumentation decorator/logger
  /flows
    log_meal_flow.py            # orchestrates the full pipeline end-to-end
    correction_flow.py          # manual-edit path + fuzzy-reparse path
  /seed
    dishes_seed.json             # the 20 dummy dishes (recipe + portions)
    load_seed_data.py            # uploads seed JSON into Supabase
  main.py                        # CLI entrypoint
  README.md                      # setup, module map, extension notes
  requirements.txt
  .env.example
```

Each module = one responsibility. This is intentional so a coding agent (or you) can alter one stage (e.g. swap the parser prompt, or change scale factors) without touching unrelated code.

---

## 2. Database Schema (Supabase / Postgres)

```sql
-- Master ingredient nutrition table (shared/reused across dishes)
CREATE TABLE ingredients_master (
    ingredient_name   TEXT PRIMARY KEY,
    calories_per_100g NUMERIC NOT NULL,
    protein_g_per_100g NUMERIC NOT NULL,
    carbs_g_per_100g   NUMERIC NOT NULL,
    fat_g_per_100g     NUMERIC NOT NULL
);

-- Dish master
CREATE TABLE dishes (
    dish_id                    TEXT PRIMARY KEY,
    display_name                TEXT NOT NULL,
    synonyms                    TEXT[] NOT NULL DEFAULT '{}',   -- for LLM matching context
    category                    TEXT NOT NULL,                  -- 'home_cooked' | 'fast_food'
    default_portion_label        TEXT NOT NULL,                  -- e.g. 'normal_plate'
    default_portion_total_grams  NUMERIC NOT NULL
);

-- Per-dish ingredient composition, at the DEFAULT portion
CREATE TABLE dish_ingredients (
    id                  BIGSERIAL PRIMARY KEY,
    dish_id              TEXT REFERENCES dishes(dish_id),
    ingredient_name       TEXT REFERENCES ingredients_master(ingredient_name),
    scaling_type          TEXT NOT NULL,       -- 'count' | 'bucket'
    default_grams          NUMERIC,             -- required if scaling_type='bucket'
    avg_unit_grams          NUMERIC              -- required if scaling_type='count' (e.g. 1 chicken piece)
);

-- Global portion-bucket vocabulary (shared across all dishes, v1 keeps this simple/global)
CREATE TABLE portion_scale_factors (
    bucket_label   TEXT PRIMARY KEY,     -- 'chota_plate','normal_plate','bara_plate','katori', etc.
    scale_factor    NUMERIC NOT NULL
);

-- Single-user meal log, structured for downstream analysis
CREATE TABLE meal_logs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 TEXT NOT NULL DEFAULT 'v1_test_user',
    dish_id                  TEXT REFERENCES dishes(dish_id),
    input_mode               TEXT NOT NULL,        -- 'text' | 'voice'
    raw_input_text            TEXT NOT NULL,
    portion_bucket             TEXT,
    scale_factor_applied        NUMERIC,
    overrides                  JSONB,               -- [{ingredient, unit, qty}, ...]
    ingredient_breakdown_g       JSONB,               -- final grams per ingredient, post-merge
    macro_totals                JSONB,               -- {calories, protein_g, carbs_g, fat_g}
    assumption_summary            TEXT,               -- verbose text shown to user
    correction_count               INT DEFAULT 0,
    logged_at                      TIMESTAMPTZ DEFAULT now()
);

-- Fallback queue for unmatched dishes (grows dish coverage over time)
CREATE TABLE unknown_dish_queue (
    id             BIGSERIAL PRIMARY KEY,
    raw_input_text  TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT now()
);
```

**Design notes:**
- `ingredients_master` is normalized/shared since dishes reuse ingredients (tomato, onion, oil, chicken) — avoids duplicating nutrition data 20 times.
- `portion_scale_factors` is a single global table (not per-dish) for v1 simplicity — one shared bucket vocabulary applies to all 20 dishes. Revisit only if testing shows some dish categories need different scaling (e.g. rice dishes vs. curries).
- `meal_logs.ingredient_breakdown_g` and `macro_totals` are stored as JSONB snapshots of the *final* computed state — this is what enables clean downstream daily/weekly aggregation without recomputing from scratch.

---

## 3. Portion Bucket Vocabulary (seed values — adjust as needed)

| bucket_label | scale_factor |
|---|---|
| katori | 0.4 |
| half_plate | 0.5 |
| chota_plate | 0.6 |
| normal_plate (default) | 1.0 |
| bara_plate | 1.4 |
| plate_and_a_half | 1.5 |

This table lives in the DB (single source of truth) and is **read at runtime and injected into the LLM system prompt** — never hardcoded into prompt text — so changing a scale factor doesn't require touching prompt code.

---

## 4. LLM Call Contracts

### Call A — Transcription (voice path only)
- **Input:** recorded audio file (wav, short clip, inline base64 — well under size limits for a few seconds of speech)
- **Model:** `gemini-3.5-flash` via Gemini's audio understanding capability
- **Prompt:** "Transcribe this audio exactly as spoken. Output only the transcript text, no commentary."
- **Output:** plain transcript string → becomes `raw_input_text`, feeding into the SAME Call B used by the typed-text path.

### Call B — Combined Dish Match + Portion/Override Parser
Combining dish-matching and portion/override extraction into **one call** is the right choice at 20-dish scale — the full dish list + synonyms + bucket table easily fit in one prompt, and it halves round-trips (directly serves your latency goal). Revisit splitting into two calls only if/when the dish catalog grows large enough that injecting the full list every time becomes expensive — that's a v2 concern, not now.

- **Input:** `raw_input_text` + injected context: full list of 20 dishes (id, display_name, synonyms) + portion_scale_factors table + system prompt with scaling/override reasoning instructions
- **Output (structured JSON):**
```json
{
  "matched": true,
  "dish_id": "karahi_chicken",
  "confidence": "high",
  "portion_bucket": "bara_plate",
  "scale_factor_applied": 1.4,
  "overrides": [
    {"ingredient": "chicken", "unit": "piece", "qty": 3}
  ],
  "assumption_summary": "Assumed 'bara plate' = 1.4x a standard plate (~310g base). Chicken overridden to 3 pieces (~300g). Oil, tomato, yogurt, onion scaled proportionally from the standard karahi recipe at 1.4x."
}
```
- If no confident match: `{"matched": false, "confidence": "low", "raw_text": "..."}` → row inserted into `unknown_dish_queue`, user informed, flow ends (v1 does not attempt fuzzy nearest-guess substitution — just flag and stop, keep it simple).

### Call C — Correction Re-parse (fuzzy correction path only)
Same output shape as Call B, but the prompt also includes the **previous parsed state** as context, so the model amends rather than re-derives from scratch (e.g. "make it bara plate" changes only `portion_bucket`/`scale_factor_applied`, keeping prior `overrides` intact unless the user's correction text says otherwise).

All prompts live in `llm/prompts.py` — nothing prompt-related should be inline in flow/logic files.

---

## 5. Core Logic — Merge Engine (deterministic, non-LLM)

```
merge(default_recipe, scale_factor, overrides):
    result = {}
    for ingredient in default_recipe:
        if ingredient.scaling_type == 'bucket':
            result[ingredient.name] = ingredient.default_grams * scale_factor
        elif ingredient.scaling_type == 'count':
            result[ingredient.name] = ingredient.avg_unit_grams * DEFAULT_UNIT_COUNT  # dish-specific default count

    for override in overrides:
        result[override.ingredient] = override.qty * matching_ingredient.avg_unit_grams  # REPLACES, never adds

    return result   # final grams per ingredient
```

Key rule: overrides **replace** the corresponding ingredient's value, they never add on top of the scaled default. Untouched ingredients stay at their scaled-default value. Independence assumption for v1: overriding one ingredient does not proportionally adjust others (e.g. more chicken pieces doesn't auto-bump oil/gravy) — revisit only if real correction data shows users expect otherwise.

## 6. Nutrition Calc
For each ingredient in the merged breakdown: `grams * (nutrition_per_100g / 100)`, summed across all ingredients → `{calories, protein_g, carbs_g, fat_g}`.

---

## 7. End-to-End Flow (`flows/log_meal_flow.py`)

1. Resolve input mode (`--text` arg or `--voice` flag)
2. **Voice path:** `recorder.py` records from mic (stop on manual key press or silence timeout) → `transcriber.py` (Call A) → `raw_input_text`
   **Text path:** `raw_input_text` = CLI argument directly
3. `parser.py` (Call B) → parsed JSON
4. If `matched == false` → insert into `unknown_dish_queue`, print message, **exit**
5. If `matched == true` → `dish_repository.get_dish_with_ingredients(dish_id)`
6. `merge_engine.merge(...)` → final ingredient grams
7. `nutrition_calc.compute(...)` → macro totals
8. Print to terminal: full ingredient breakdown, macro totals, `assumption_summary`
9. Prompt: `[m]anual edit / [t]alk to fix / [s]ave / [d]iscard`
   - **manual** → direct CLI field edit (pick ingredient, enter new grams, or edit override qty) → skip LLM → re-run step 6–8 → loop back to this prompt
   - **talk** → free-text correction → `correction_flow.py` (Call C, with prior parsed state as context) → re-run step 6–8 → loop back to this prompt
   - **save** → insert final row into `meal_logs` (increment `correction_count` if corrections occurred) → done
   - **discard** → exit without saving
10. Every stage in steps 2–7 is wrapped with `core/timing.py` instrumentation — log stage name + duration (transcription time, parse time, DB lookup time, merge+calc time, total) to stdout or a local latency log file. This is central to v1's purpose — don't skip it.

---

## 8. Dev / Coding-Agent Instructions

- **Docstrings:** every module file starts with a short header docstring stating its single responsibility, inputs, and outputs.
- **Typed models everywhere:** use pydantic models (`core/models.py`) for all LLM JSON outputs and all DB rows — validates shape immediately, and malformed LLM JSON should trigger one retry before failing loudly (never silently guess).
- **No inline prompts:** all prompt text lives in `llm/prompts.py`, referenced by name from `parser.py`/`transcriber.py`. This makes prompt iteration isolated from flow logic.
- **Config-driven constants:** model names, default `user_id`, table names all live in `config/settings.py` — never hardcoded elsewhere.
- **Latency logging is a first-class feature, not an afterthought** — instrument every external call (Gemini calls, Supabase calls).
- **README.md** must include: setup steps (.env values needed, `pip install -r requirements.txt`, `python seed/load_seed_data.py` to populate DB), a one-paragraph description of each module, and a short "deferred to v2" section (mobile UI, auth, vision-based portions, personal calibration memory) so future-you or another agent doesn't accidentally try to build those into v1.
- **Keep the 20-dish seed intentionally small and hand-curated** — resist any temptation to auto-generate more dishes or invent nutrition values; every seed value should trace to an agreed-upon standard reference.

---

## 9. Suggested Next Steps (not included in this document — ask if you want these generated)

- The actual `dishes_seed.json` content for the 20 dishes (recipes, portions, nutrition values)
- The literal `schema.sql` file, ready to run against Supabase
- Full system prompt text for `prompts.py` (dish-matching + portion/override extraction + correction re-parse)

Say which of these you want drafted first and I'll generate it as its own file.
