"""
main.py
────────
CLI entrypoint for the Desi Calorie Tracker v1.

Single responsibility: Parse command-line arguments and delegate to the
appropriate flow.  All business logic lives in flows/.

Usage:
    python main.py --text "one plate karahi with 3 pieces of chicken"
    python main.py --voice

One command = one meal logged.  No persistent REPL in v1.
"""

import argparse
import logging
import sys
import warnings
from pathlib import Path

# Suppress library deprecation notice
warnings.filterwarnings("ignore", category=FutureWarning)

# Configure UTF-8 encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Ensure project root is on sys.path (handles running from any directory) ───
_PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ── Configure basic logging (DEBUG visible only if --debug flag is set) ────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s: %(message)s",
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="desi-calorie-tracker",
        description=(
            "Desi Calorie Tracker v1 — Log Pakistani meals from text or voice.\n"
            "One command = one meal logged."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py --text "one plate karahi with 3 pieces of chicken"\n'
            '  python main.py --text "bara plate biryani"\n'
            '  python main.py --voice\n'
            '  python main.py --text "2 chapli kebabs" --debug'
        ),
    )

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--text",
        metavar="MEAL_DESCRIPTION",
        help='Describe your meal as text, e.g. "one plate karahi with 3 pieces of chicken".',
    )
    mode.add_argument(
        "--voice",
        action="store_true",
        help="Record your meal description from the microphone (press Enter to stop).",
    )

    p.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging (verbose output from all modules).",
    )

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    from flows.log_meal_flow import run_log_meal_flow

    if args.voice:
        run_log_meal_flow(input_mode="voice")
    else:
        run_log_meal_flow(input_mode="text", text_input=args.text)


if __name__ == "__main__":
    main()
