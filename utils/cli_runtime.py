"""CLI/runtime bootstrap helpers for unpackr commands."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any


def configure_windows_console_utf8() -> None:
    """Best-effort UTF-8 console setup for Windows terminals."""
    if sys.platform != "win32":
        return

    try:
        if hasattr(sys.stdout, "reconfigure"):
            stdout: Any = sys.stdout
            stderr: Any = sys.stderr
            stdout.reconfigure(encoding="utf-8")
            stderr.reconfigure(encoding="utf-8")
        else:
            import codecs

            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        # Terminal-dependent setup; safe fallback is default encoding.
        pass


def build_unpackr_arg_parser() -> argparse.ArgumentParser:
    """Create the unpackr CLI parser."""
    parser = argparse.ArgumentParser(
        description="Automated video file processing and cleanup tool.",
        epilog="Examples:\n"
        "  unpackr --source C:\\Downloads --destination D:\\Videos\n"
        "  unpackr C:\\Downloads D:\\Videos\n"
        "  unpackr  (interactive mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source_pos", nargs="?", help="Source downloads directory (positional)")
    parser.add_argument("dest_pos", nargs="?", help="Destination directory (positional)")
    parser.add_argument("--source", "-s", help="Path to source downloads directory")
    parser.add_argument("--destination", "-d", help="Path to destination directory")
    parser.add_argument("--config", "-c", help="Path to config.json file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--show-plan", action="store_true", help="Show detailed pre-flight plan and exit (no processing)")
    parser.add_argument("--vhealth", action="store_true", help="Run video health check on destination after processing")
    parser.add_argument(
        "--animations",
        choices=["auto", "off", "light", "full"],
        default=None,
        help="CLI animation mode (default: auto; can also use UNPACKR_ANIMATIONS).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors and styled output (also respects NO_COLOR/UNPACKR_NO_COLOR).",
    )
    return parser
