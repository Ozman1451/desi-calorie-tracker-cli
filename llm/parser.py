"""
llm/parser.py
─────────────
Single responsibility: Orchestrate LLM parsing calls (Call B and Call C) and
return validated ParsedMeal objects.

Responsibilities:
  - Fetch dish catalogue and bucket table from DB (cached within a single run)
  - Build the appropriate prompt (via llm/prompts.py)
  - Call Gemini (via llm/gemini_client.py)
  - Parse and validate the JSON response with Pydantic
  - Implement ONE retry on malformed JSON before raising loudly (never silently guess)

Inputs:  raw_text (str) for Call B; correction_text + prior_state for Call C.
Outputs: ParsedMeal (validated Pydantic model).
"""

import json
import logging

from core.models import ParsedMeal, DishSummary
from core.timing import timed
from db.dish_repository import get_all_dishes_for_prompt, get_portion_scale_factors
from llm.gemini_client import generate_text
from llm.prompts import build_parser_prompt, build_correction_prompt

logger = logging.getLogger(__name__)

# ── Module-level cache — populated once per process run ──────────────────────
_dishes_cache: list[DishSummary] | None = None
_buckets_cache: dict[str, float] | None = None


def _get_context() -> tuple[list[DishSummary], dict[str, float]]:
    """
    Lazily fetch and cache the dish catalogue and bucket vocabulary.
    Both are stable within a single CLI invocation, so one DB round-trip suffices.
    """
    global _dishes_cache, _buckets_cache
    if _dishes_cache is None or _buckets_cache is None:
        from core.timing import timer
        with timer("DB: fetch dish catalogue + buckets"):
            _dishes_cache = get_all_dishes_for_prompt()
            _buckets_cache = get_portion_scale_factors()
    return _dishes_cache, _buckets_cache


def _parse_llm_json(raw_response: str) -> dict:
    """
    Extract and parse the JSON object from a Gemini response string.
    Handles cases where Gemini wraps the JSON in markdown fences.
    Raises json.JSONDecodeError if the response cannot be parsed.
    """
    text = raw_response.strip()
    # Strip potential markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def _call_and_validate(prompt: str, attempt: int = 1) -> ParsedMeal:
    """
    Send prompt to Gemini, parse JSON, validate with Pydantic.
    Retries once on malformed JSON.  Raises on second failure.
    """
    raw = generate_text(prompt)
    try:
        data = _parse_llm_json(raw)
        return ParsedMeal.model_validate(data)
    except (json.JSONDecodeError, Exception) as exc:
        if attempt == 1:
            logger.warning(
                "Malformed LLM response (attempt %d) — retrying once. Error: %s",
                attempt,
                exc,
            )
            return _call_and_validate(prompt, attempt=2)
        # Second failure: raise loudly as per blueprint §8
        raise ValueError(
            f"LLM returned unparseable JSON after {attempt} attempts.\n"
            f"Raw response:\n{raw}\n"
            f"Parse error: {exc}"
        ) from exc


@timed("LLM: parse meal (Call B)")
def parse_meal(raw_text: str) -> ParsedMeal:
    """
    Call B — Combined dish match + portion/override extraction.

    Args:
        raw_text: User's meal description (typed or transcribed from audio).

    Returns:
        ParsedMeal with matched=True (dish found) or matched=False (unknown dish).
    """
    dishes, buckets = _get_context()
    prompt = build_parser_prompt(dishes, buckets, raw_text)
    return _call_and_validate(prompt)


@timed("LLM: correction re-parse (Call C)")
def reparse_with_correction(
    correction_text: str,
    prior_state: ParsedMeal,
) -> ParsedMeal:
    """
    Call C — Fuzzy correction re-parse.  The prior parsed state is passed as
    context so the model amends only what the user specifies.

    Args:
        correction_text: User's free-text correction (e.g. "make it bara plate").
        prior_state:     Current ParsedMeal to amend.

    Returns:
        Updated ParsedMeal with corrections applied.
    """
    dishes, buckets = _get_context()
    prompt = build_correction_prompt(dishes, buckets, correction_text, prior_state)
    return _call_and_validate(prompt)
