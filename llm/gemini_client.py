"""
llm/gemini_client.py
─────────────────────
Single responsibility: Thin shared wrapper around the Google Generative AI SDK.
All other LLM modules (parser.py, transcriber.py) call this wrapper — they
never import google.generativeai directly.

Provides:
  generate_text(prompt, model)               — text-in, text-out call
  generate_from_audio(audio_path, prompt, model) — audio + text prompt, text-out

Inputs:  Prompt strings and optional audio file path.
Outputs: Raw response text string from Gemini.
"""

import base64
import logging
from pathlib import Path

import warnings
# Suppress library deprecation notice from polluting CLI output
warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── Configure the SDK once on module import ───────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)


def generate_text(prompt: str, model: str = GEMINI_MODEL) -> str:
    """
    Send a text prompt to Gemini and return the response text.

    Args:
        prompt: The full prompt string (system + user context combined).
        model:  Gemini model name (defaults to GEMINI_MODEL from settings).

    Returns:
        Stripped response text.

    Raises:
        Exception from the Gemini SDK on API error (let callers handle retry).
    """
    logger.debug("Gemini text call — model: %s, prompt_len: %d", model, len(prompt))
    client = genai.GenerativeModel(model)
    response = client.generate_content(prompt)
    return response.text.strip()


def generate_from_audio(
    audio_path: str | Path,
    text_prompt: str,
    model: str = GEMINI_MODEL,
) -> str:
    """
    Send an audio file + a text instruction to Gemini and return the response text.
    Used by audio/transcriber.py for the Call A transcription step.

    The audio is base64-encoded inline (inline_data) — appropriate for short
    voice clips (seconds, well under Gemini's per-request size limits).

    Args:
        audio_path:   Absolute path to a .wav audio file.
        text_prompt:  Instruction text (e.g. transcription prompt).
        model:        Gemini model name.

    Returns:
        Stripped response text (the transcript).
    """
    audio_bytes = Path(audio_path).read_bytes()
    audio_part = {
        "inline_data": {
            "mime_type": "audio/wav",
            "data": base64.b64encode(audio_bytes).decode("utf-8"),
        }
    }

    logger.debug(
        "Gemini audio call — model: %s, audio_size: %d bytes",
        model,
        len(audio_bytes),
    )
    client = genai.GenerativeModel(model)
    response = client.generate_content([audio_part, text_prompt])
    return response.text.strip()
