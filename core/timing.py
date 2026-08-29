"""
core/timing.py
──────────────
Single responsibility: Latency instrumentation for all external calls and
pipeline stages.  Every timed event is printed to stdout AND appended to a
persistent latency log file (LATENCY_LOG_PATH from settings).

Provides:
  @timed(label)     — decorator for synchronous functions
  timer(label)      — context manager for inline code blocks

Inputs:  Any callable or code block.
Outputs: Unchanged return value (decorator); side-effects: stdout print + log file append.
"""

import time
import functools
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator

from config.settings import LATENCY_LOG_PATH


# ── Internal logging helper ───────────────────────────────────────────────────

def _log(label: str, duration_s: float) -> None:
    """Print a timing line and append it to the latency log file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    message = f"[TIMING] {label}: {duration_s:.3f}s"
    try:
        print(f"  ⏱  {message}")
    except UnicodeEncodeError:
        print(f"  [TIME] {message}")
    try:
        with open(LATENCY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts}  {message}\n")
    except OSError:
        # Log file write failure is non-fatal — don't crash the pipeline.
        pass


# ── Decorator ─────────────────────────────────────────────────────────────────

def timed(label: str) -> Callable:
    """
    Decorator that measures and logs execution time of a synchronous function.

    Usage:
        @timed("Gemini parse")
        def parse_meal(raw_text: str) -> ParsedMeal: ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = func(*args, **kwargs)
            _log(label, time.perf_counter() - start)
            return result
        return wrapper
    return decorator


# ── Context manager ───────────────────────────────────────────────────────────

@contextmanager
def timer(label: str) -> Generator[None, None, None]:
    """
    Context manager that measures and logs execution time of an inline block.

    Usage:
        with timer("Supabase dish fetch"):
            dish = get_dish_with_ingredients(dish_id)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        _log(label, time.perf_counter() - start)
