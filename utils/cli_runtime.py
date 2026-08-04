"""CLI/runtime bootstrap helpers for unpackr commands."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
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
        os.system("chcp 65001 >nul 2>&1")  # nosec B605 - fixed command for Windows console codepage setup
    except Exception:
        # Terminal-dependent setup; safe fallback is default encoding.
        return


def existing_file_path(value: str) -> str:
    """Validate a CLI value as an existing regular file."""
    path = Path(value).expanduser()
    try:
        is_file = path.is_file()
    except OSError as exc:
        raise argparse.ArgumentTypeError(f"cannot access file: {value} ({exc})") from exc

    if not is_file:
        raise argparse.ArgumentTypeError(f"file does not exist: {value}")
    return str(path)


def resolve_unpackr_paths(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> tuple[str | None, str | None]:
    """Resolve named and positional paths without silently discarding values."""
    source = args.source
    destination = args.destination
    positional = [value for value in (args.source_pos, args.dest_pos) if value is not None]

    if source is None and destination is None:
        if not positional:
            return None, None
        if len(positional) != 2:
            parser.error("source and destination must be provided together")
        return positional[0], positional[1]

    if source is not None and destination is not None:
        if positional:
            parser.error("do not add positional paths when both --source and --destination are set")
        return source, destination

    if len(positional) > 1:
        parser.error("too many positional paths were provided with a named path option")
    if not positional:
        parser.error("source and destination must be provided together")

    if source is None:
        source = positional[0]
    else:
        destination = positional[0]
    return source, destination


def build_unpackr_arg_parser() -> argparse.ArgumentParser:
    """Create the unpackr CLI parser."""
    from utils.platform_support import example_destination_path, example_source_path

    source_example = example_source_path()
    destination_example = example_destination_path()
    parser = argparse.ArgumentParser(
        description="Automated video file processing and cleanup tool.",
        epilog="Examples:\n"
        f'  unpackr --source "{source_example}" --destination "{destination_example}"\n'
        f'  unpackr "{source_example}" "{destination_example}"\n'
        "  unpackr  (interactive mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source_pos", nargs="?", help="Source downloads directory (positional)")
    parser.add_argument("dest_pos", nargs="?", help="Destination directory (positional)")
    parser.add_argument("--source", "-s", help="Path to source downloads directory")
    parser.add_argument("--destination", "-d", help="Path to destination directory")
    parser.add_argument(
        "--destinantion",
        dest="destination",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--config", "-c", type=existing_file_path, help="Path to an existing config.json file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument(
        "--show-plan", action="store_true", help="Show detailed pre-flight plan and exit (no processing)"
    )
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable run summary JSON object after the run completes.",
    )
    return parser
