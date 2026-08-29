# Desi Calorie Tracker — v1 CLI

A terminal-based meal logging prototype for Pakistani / Desi cuisine.  Built to test and benchmark the core parsing → scaling → merge → macro pipeline before any mobile app work begins.  Powered by **Gemini 2.0 Flash** (LLM + speech-to-text) and **Supabase / Postgres** as the backend.

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) project (free tier is fine)
- A [Google AI Studio](https://aistudio.google.com/app/apikey) API key (Gemini)
- A microphone (only needed for `--voice` mode)

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> On Windows, `sounddevice` may require the PortAudio DLL.  If you get an error, install it via `pip install sounddevice` and ensure PortAudio is available (ships with most Python audio packages).

### 3. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in:
#   SUPABASE_URL      — your Supabase project URL
#   SUPABASE_ANON_KEY — your Supabase anon/public key
#   GEMINI_API_KEY    — your Google AI Studio API key
```

### 4. Create the database schema

Open your Supabase project → **SQL Editor** → paste and run the contents of [`db/schema.sql`](db/schema.sql).

### 5. Seed the dish catalogue

```bash
python seed/load_seed_data.py
```

This populates all 4 tables with the 20 reference dishes, 33 ingredients, and 6 portion buckets.  Safe to re-run (idempotent upserts).

### 6. Log a meal

```bash
# Text mode
python main.py --text "one plate karahi with 3 pieces of chicken"
python main.py --text "bara plate biryani"
python main.py --text "2 chapli kebabs"

# Voice mode (press Enter to stop recording)
python main.py --voice

# Debug mode (verbose logging from all modules)
python main.py --text "haleem" --debug
```

---

## Module Map

| Module | Single Responsibility |
|---|---|
| `main.py` | CLI entrypoint — parse args, delegate to flow |
| `config/settings.py` | Load `.env`, expose typed constants.  Only file that touches `os.getenv()` |
| `db/schema.sql` | Postgres table definitions — run once in Supabase SQL Editor |
| `db/client.py` | Supabase client singleton |
| `db/dish_repository.py` | Read dish catalogue + ingredient data from Supabase |
| `db/meal_repository.py` | Write meal logs and unknown dish queue to Supabase |
| `audio/recorder.py` | Record mic audio to WAV (Enter-to-stop) |
| `audio/transcriber.py` | Send WAV to Gemini → transcript string (Call A) |
| `llm/gemini_client.py` | Thin Gemini SDK wrapper used by all LLM modules |
| `llm/prompts.py` | **All prompt text lives here** — no inline prompts anywhere else |
| `llm/parser.py` | Call B (parse meal) + Call C (correction re-parse) + JSON validation + 1 retry |
| `core/models.py` | All Pydantic models — validated at parse time, shared across modules |
| `core/merge_engine.py` | Deterministic portion scaling + override application — zero LLM involvement |
| `core/nutrition_calc.py` | Convert final grams per ingredient → macro totals |
| `core/timing.py` | `@timed` decorator + `timer()` context manager — latency to stdout + `latency.log` |
| `flows/log_meal_flow.py` | End-to-end pipeline orchestrator (steps 1–10 from blueprint §7) |
| `flows/correction_flow.py` | Manual edit path (no LLM) + fuzzy talk-to-fix path (Call C) |
| `seed/dishes_seed.json` | 20 hand-curated Pakistani dishes with recipes + nutrition data |
| `seed/load_seed_data.py` | Reads seed JSON, upserts all tables in FK dependency order |

---

## Architecture Overview

```
User input (--text or --voice)
        │
        ▼
[Voice path only]
  recorder.py  ──▶  transcriber.py (Gemini Call A)
                            │
                            ▼  raw_input_text
                     parser.py (Gemini Call B)
                            │
              ┌─────────────┴──────────────┐
         matched=false                matched=true
              │                            │
    unknown_dish_queue            dish_repository.get_dish()
              │                            │
            EXIT                  merge_engine.merge()
                                           │
                                  nutrition_calc.compute()
                                           │
                                    Display to terminal
                                           │
                              ┌────────────┼────────────┐
                           [m]anual      [t]alk       [s]ave   [d]iscard
                           edit          fix           │
                              │    correction_flow      │
                              │    (Gemini Call C)      ▼
                              └────────────────▶  meal_logs (DB)
```

---

## Portion Bucket Vocabulary

| Bucket | Scale Factor | Description |
|---|---|---|
| `katori` | 0.4× | Small bowl / half katori |
| `half_plate` | 0.5× | Half a plate |
| `chota_plate` | 0.6× | Small plate |
| `normal_plate` | 1.0× | Standard serving (default) |
| `bara_plate` | 1.4× | Large plate / full plate |
| `plate_and_a_half` | 1.5× | 1.5× standard serving |

The LLM reads this table from the DB at runtime and maps natural-language descriptions ("bari plate", "thoda sa", "katori bhar") to these labels.

---

## Latency Instrumentation

Every external call is timed.  Timings are printed to stdout during a run AND appended to `latency.log` in the project root:

```
[TIMING] Gemini: audio transcription (Call A): 1.243s
[TIMING] DB: fetch dish catalogue + buckets: 0.312s
[TIMING] LLM: parse meal (Call B): 1.876s
[TIMING] DB: fetch dish with ingredients: 0.287s
[TIMING] DB: insert meal log: 0.198s
```

This latency data is a **primary deliverable of v1** — use it to benchmark and tune before building the mobile app.

---

## The 20 Seed Dishes

### Home-Cooked (10)
| Dish | dish_id |
|---|---|
| Chicken Karahi | `chicken_karahi` |
| Dal Chawal | `dal_chawal` |
| Chicken Biryani | `chicken_biryani` |
| Beef Nihari | `nihari` |
| Beef Haleem | `haleem` |
| Palak Gosht | `palak_gosht` |
| Aloo Gosht | `aloo_gosht` |
| Sarson Ka Saag | `sarson_saag` |
| Chicken Pulao | `chicken_pulao` |
| Dahi Chawal | `dahi_chawal` |

### Fast-Food / Street Food (10)
| Dish | dish_id |
|---|---|
| Chicken Shawarma | `chicken_shawarma` |
| Zinger Burger | `zinger_burger` |
| Chicken Boti (BBQ) | `chicken_boti` |
| Chapli Kebab | `chapli_kebab` |
| Aloo Samosa | `aloo_samosa` |
| Chicken Paratha Roll | `chicken_paratha_roll` |
| Qeema Naan | `qeema_naan` |
| Doodh Patti Chai | `doodh_patti` |
| Aloo Pakora | `aloo_pakora` |
| Plain Paratha | `plain_paratha` |

---

## Correction Loop

After every meal parse, the user is prompted with:

```
Action → [m]anual edit / [t]alk to fix / [s]ave / [d]iscard:
```

| Key | Action |
|---|---|
| `m` | Manual edit — pick an ingredient, type new grams.  No LLM call. |
| `t` | Talk to fix — free-text correction sent to Gemini (Call C) which amends only what you specify. |
| `s` | Save — insert final meal into `meal_logs` in Supabase. |
| `d` | Discard — exit without saving. |

---

## Deferred to v2

The following are explicitly **out of scope for v1** and should NOT be built into this codebase:

- **Mobile app / UI** — v1 is terminal-only by design.
- **User accounts & auth** — v1 uses a single fixed `user_id = v1_test_user`.
- **Vision / photo-based portion estimation** — entirely separate capability.
- **Persistent per-user calibration memory** — corrections in v1 are stateless (they improve the current meal, not stored as a learned multiplier for future meals).
- **Manual weighing / photo-based calibration data** — v1 uses agreed-upon standard estimates only.
- **Auto-expanding dish catalogue** — the 20-dish list is intentionally hand-curated; unknown dishes go to `unknown_dish_queue` for manual review.

---

## Development Notes

- **No inline prompts** — all prompt text lives in `llm/prompts.py`.  Change a prompt there; nothing else changes.
- **No hardcoded table names** — all table names live in `config/settings.py → TABLE_NAMES`.
- **Nutrition values** — every value in `seed/dishes_seed.json` traces to USDA FoodData Central or Pakistan NIFSAT food composition tables.  Do not invent values.
- **Pydantic everywhere** — all LLM JSON outputs are validated immediately via Pydantic models.  Malformed LLM responses retry once, then raise loudly.
- **Scale factors from DB** — portion bucket scale factors are read at runtime and injected into prompts.  Changing a value in Supabase requires no code change.
