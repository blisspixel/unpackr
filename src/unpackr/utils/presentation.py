"""Terminal presentation: width, colour roles, the opening line and the end-of-run receipt.

Colour follows the terminal theme. Roles are ANSI only: cyan accent, green
success, yellow warning, red error, blue info, dim labels. Neutral numbers use
the default foreground. There is no magenta and no forced white.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import TYPE_CHECKING, Any

from colorama import Fore, Style

if TYPE_CHECKING:
    from pathlib import Path

DELETE_VERBS = {
    "quarantine": "Quarantine",
    "trash": "Trash",
    "permanent": "Delete",
}


def argument_parser_kwargs() -> dict[str, Any]:
    """argparse colours its own errors from 3.14. Unpackr paints its own output, so that stays off."""
    if sys.version_info >= (3, 14):
        return {"color": False}
    return {}


def terminal_width(default: int = 80) -> int:
    try:
        columns = shutil.get_terminal_size((default, 24)).columns
    except OSError:
        columns = default
    return max(20, int(columns))


def color_enabled() -> bool:
    """False when the user, the terminal, or stdout cannot show styled text."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✓".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def ascii_marks() -> bool:
    """Doctor glyphs fall back to words when colour is off or the glyphs will not encode."""
    if not color_enabled():
        return True
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✓⚠✗".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return True
    return False


def paint(role: str, text: str, *, enabled: bool | None = None) -> str:
    if enabled is None:
        enabled = color_enabled()
    if not enabled or not text:
        return text
    colour = {
        "accent": Fore.CYAN,
        "success": Fore.GREEN,
        "warning": Fore.YELLOW,
        "error": Fore.RED,
        "info": Fore.BLUE,
        "muted": Style.DIM,
    }.get(role, "")
    if not colour:
        return text
    return f"{colour}{text}{Style.RESET_ALL}"


def removal_verb(mode: str) -> str:
    """Imperative name of the configured removal mode. Default is Quarantine, not Delete."""
    return DELETE_VERBS.get(mode, "Quarantine")


def removal_past(mode: str) -> str:
    """Past tense of the removal, used in 'will be quarantined'."""
    return {"quarantine": "quarantined", "trash": "trashed", "permanent": "deleted"}.get(mode, "quarantined")


def visible_len(text: str) -> int:
    """Length of ``text`` once ANSI colour sequences are ignored."""
    width = 0
    index = 0
    while index < len(text):
        if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "[":
            index += 2
            while index < len(text) and text[index] not in "mK":
                index += 1
            index += 1
            continue
        width += 1
        index += 1
    return width


def truncate_visible(text: str, width: int) -> str:
    """Cut ``text`` so its visible width is at most ``width``."""
    if width < 1:
        return ""
    if visible_len(text) <= width:
        return text
    kept: list[str] = []
    seen = 0
    index = 0
    limit = width
    while index < len(text) and seen < limit:
        if text[index] == "\x1b" and index + 1 < len(text) and text[index + 1] == "[":
            end = index + 2
            while end < len(text) and text[end] not in "mK":
                end += 1
            kept.append(text[index : end + 1])
            index = end + 1
            continue
        kept.append(text[index])
        seen += 1
        index += 1
    return "".join(kept)


def fit_line(text: str, width: int | None = None) -> str:
    columns = terminal_width() if width is None else width
    return truncate_visible(text, max(1, columns - 1))


def rule(char: str = "=", width: int | None = None, cap: int = 80) -> str:
    columns = terminal_width() if width is None else width
    return char * max(1, min(cap, columns))


def shorten_path(path: Path | str) -> str:
    text = str(path)
    home = os.path.expanduser("~")
    if home and (text == home or text.startswith(home + os.sep)):
        return "~" + text[len(home) :].replace("\\", "/")
    return text.replace("\\", "/")


def wrap_field(label: str, value: str, width: int) -> list[str]:
    """``label`` plus ``value``, wrapped with a hanging indent. Every line fits ``width``."""
    width = max(len(label) + 2, width)
    prefix = f"{label:<8}"
    indent = " " * len(prefix)
    words = value.split()
    lines: list[str] = []
    current = prefix.rstrip()
    for word in words:
        piece = word if not current.strip() else current + " " + word
        if visible_len(piece) <= width:
            current = piece
            continue
        if current.strip():
            lines.append(current)
        current = indent + word if lines else prefix + word
        while visible_len(current) > width and len(word) > 8:
            lines.append(current[:width])
            current = indent + current[width:]
    if current.strip():
        lines.append(current)
    return [truncate_visible(line, width) for line in lines] or [prefix.rstrip()]


def opening_banner(version: str, *, is_tty: bool, width: int, art: str) -> str:
    """The wordmark once, or a single version line when the window is too narrow."""
    if is_tty and width >= 44:
        return art.rstrip("\n")
    return f"unpackr {version}"


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def receipt_lines(
    *,
    folders: int,
    freed_bytes: int,
    source: str,
    videos_moved: int,
    destination: str,
    redownload: int,
    mode: str,
    restore_command: str,
    retention_days: int,
    dry_run: bool,
    width: int,
) -> list[tuple[str, str, str]]:
    """Three receipt rows: (label, text, role). ``role`` colours the value, not the label."""
    freed = format_bytes(freed_bytes)
    source_short = shorten_path(source)
    dest_short = shorten_path(destination)
    video_word = "video" if videos_moved == 1 else "videos"
    folder_word = "folder" if folders == 1 else "folders"
    if dry_run:
        cleaned = f"{folders} {folder_word}, {freed} would be freed in {source_short}"
        kept = f"{videos_moved} {video_word} would be moved to {dest_short}"
    else:
        cleaned = f"{folders} {folder_word}, {freed} freed in {source_short}"
        kept = f"{videos_moved} {video_word} moved to {dest_short}"
    if redownload:
        noun = "needs" if redownload == 1 else "need"
        kept += f", {redownload} {noun} a re-download"
    if mode == "permanent":
        undo = "removed permanently (delete_mode)"
        undo_role = "warning"
    elif mode == "trash":
        undo = "restore from the system trash"
        undo_role = "info"
    else:
        days = f"  ({retention_days} days)" if retention_days else ""
        undo = f"{restore_command}{days}"
        undo_role = "info"
    return [("cleaned", cleaned, "success"), ("kept", kept, "muted"), ("undo", undo, undo_role)]
