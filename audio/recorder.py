"""
audio/recorder.py
──────────────────
Single responsibility: Record audio from the system microphone into a WAV file.
Recording starts immediately on call and stops when the user presses Enter.

Inputs:  Optional output_path (defaults to audio/_temp/recording.wav).
Outputs: Path string to the saved WAV file.

Dependencies: sounddevice, soundfile, numpy.
"""

import threading
import time
import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from config.settings import AUDIO_TEMP_DIR

logger = logging.getLogger(__name__)

# ── Audio recording constants ─────────────────────────────────────────────────
SAMPLE_RATE: int = 16_000   # 16 kHz — standard for speech recognition
CHANNELS: int = 1            # Mono
DTYPE: str = "int16"         # 16-bit PCM WAV
DEFAULT_OUTPUT_FILENAME: str = "recording.wav"


def record_audio(output_path: str | Path | None = None) -> str:
    """
    Record mic audio until the user presses Enter, then save as WAV.

    The recording happens in a background thread while the main thread
    waits for an Enter keypress.

    Args:
        output_path: Where to save the WAV file.  Defaults to
                     audio/_temp/recording.wav in the project root.

    Returns:
        Absolute path string to the saved WAV file.
    """
    if output_path is None:
        output_path = AUDIO_TEMP_DIR / DEFAULT_OUTPUT_FILENAME
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frames: list[np.ndarray] = []
    stop_event = threading.Event()

    def _audio_callback(
        indata: np.ndarray,
        frames_count: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Called by sounddevice for each audio chunk — append to buffer."""
        if status:
            logger.warning("sounddevice status: %s", status)
        frames.append(indata.copy())

    print("\n  🎙  Recording... Press [Enter] to stop.")
    start_ts = time.perf_counter()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        callback=_audio_callback,
    ):
        input()  # Block main thread — user presses Enter to stop
        stop_event.set()

    duration = time.perf_counter() - start_ts
    print(f"  ✓  Recording stopped ({duration:.1f}s captured).")

    if not frames:
        raise RuntimeError("No audio frames captured — check your microphone.")

    audio_data = np.concatenate(frames, axis=0)
    sf.write(str(output_path), audio_data, SAMPLE_RATE)
    logger.debug("Audio saved to %s (%d samples)", output_path, len(audio_data))

    return str(output_path)
