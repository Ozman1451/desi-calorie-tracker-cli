"""
config/settings.py
──────────────────
Single responsibility: Load all configuration from the .env file and expose
typed constants to the rest of the application.  Nothing else imports .env
directly — every other module reads from here.

Inputs:  .env file in the project root (or environment variables already set).
Outputs: Named constants — SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY,
         DEFAULT_USER_ID, GEMINI_MODEL, LATENCY_LOG_PATH, TABLE_NAMES.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from the project root (two levels up from this file) ──────────
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _require(key: str) -> str:
    """Read an env var or raise a clear error if it's missing."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: '{key}'. "
            f"Copy .env.example → .env and fill in your values."
        )
    return value


# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str = _require("SUPABASE_URL")
SUPABASE_ANON_KEY: str = _require("SUPABASE_ANON_KEY")

# ── Google Gemini ─────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# ── App constants ─────────────────────────────────────────────────────────────
DEFAULT_USER_ID: str = os.getenv("DEFAULT_USER_ID", "v1_test_user")
LATENCY_LOG_PATH: Path = _PROJECT_ROOT / os.getenv("LATENCY_LOG_PATH", "latency.log")

# ── Supabase table names (single source of truth — never hardcode elsewhere) ──
TABLE_NAMES: dict[str, str] = {
    "ingredients_master": "ingredients_master",
    "dishes": "dishes",
    "dish_ingredients": "dish_ingredients",
    "portion_scale_factors": "portion_scale_factors",
    "meal_logs": "meal_logs",
    "unknown_dish_queue": "unknown_dish_queue",
}

# ── Temp audio directory ──────────────────────────────────────────────────────
AUDIO_TEMP_DIR: Path = _PROJECT_ROOT / "audio" / "_temp"
AUDIO_TEMP_DIR.mkdir(parents=True, exist_ok=True)
