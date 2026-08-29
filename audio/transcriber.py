"""
audio/transcriber.py
─────────────────────
Single responsibility: Send a recorded WAV file to Gemini (Call A) and return
the transcript as a plain string.

This module is only invoked on the voice path.  The returned transcript becomes
`raw_input_text` and feeds into the SAME Call B parser used by the text path —
no code divergence after this point.

Inputs:  audio_path (str) — path to a WAV file from recorder.py.
Outputs: transcript (str) — plain text, as spoken.
"""

import logging

from core.timing import timed
from llm.gemini_client import generate_from_audio
from llm.prompts import TRANSCRIPTION_PROMPT

logger = logging.getLogger(__name__)


@timed("Gemini: audio transcription (Call A)")
def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe a WAV file to text using Gemini's audio understanding capability.

    Args:
        audio_path: Absolute path to the WAV file recorded by recorder.py.

    Returns:
        Transcript string exactly as spoken (Urdu/Roman Urdu words preserved).

    Raises:
        Exception from gemini_client if the API call fails.
    """
    logger.debug("Transcribing audio from: %s", audio_path)
    transcript = generate_from_audio(audio_path, TRANSCRIPTION_PROMPT)
    print(f"  📝  Transcript: \"{transcript}\"")
    return transcript
