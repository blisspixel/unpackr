"""Terminal progress: a six-line dashboard, or nothing when the terminal cannot show it.

``light`` and ``full`` are the same dashboard. ``off``, a non-TTY, CI, NO_COLOR,
TERM=dumb and UNPACKR_NO_ANIM leave rendering to the one-line progress path.
The dashboard never clears the screen.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Literal, Protocol

from unpackr.utils.presentation import fit_line, paint, terminal_width

AnimationMode = Literal["auto", "off", "light", "full"]

_SPINNER = ("-", "\\", "|", "/")


class Renderer(Protocol):
    """Interface shared by progress renderers."""

    def start(self, _total: int) -> None: ...

    def update(
        self,
        *,
        current: int,
        total: int,
        action: str,
        verb: str,
        target: str,
        stats_line: str,
        time_line: str,
        comment_line: str,
    ) -> None: ...

    def stop(self) -> None: ...


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class DashboardRenderer:
    """Redraw six status lines in place. First paint is immediate; later paints are at most 10 per second."""

    lines = 6

    def __init__(self) -> None:
        self._started = False
        self._drawn = False
        self._last = 0.0
        self._spinner = 0
        self._pending: dict[str, object] | None = None

    def start(self, _total: int) -> None:
        self._started = True

    def update(
        self,
        *,
        current: int,
        total: int,
        action: str,
        verb: str,
        target: str,
        stats_line: str,
        time_line: str,
        comment_line: str,
    ) -> None:
        self._pending = {
            "current": current,
            "total": total,
            "action": action,
            "verb": verb,
            "target": target,
            "stats_line": stats_line,
            "time_line": time_line,
            "comment_line": comment_line,
        }
        if not self._started:
            self.start(total)
        now = time.monotonic()
        if self._last == 0.0 or now - self._last >= 0.1:
            self._paint()
            self._last = now

    def stop(self) -> None:
        if self._pending is not None:
            self._paint()
        if self._drawn:
            sys.stdout.write("\n")
            sys.stdout.flush()
        self._started = False

    def _paint(self) -> None:
        pending = self._pending
        if pending is None:
            return
        current_obj = pending["current"]
        total_obj = pending["total"]
        current = current_obj if isinstance(current_obj, int) else 0
        total = total_obj if isinstance(total_obj, int) else 0
        percent = int((current / total) * 100) if total > 0 else 0
        width = terminal_width()
        bar_len = max(8, min(36, width - 24))
        filled = int(bar_len * current / total) if total > 0 else 0
        bar = "#" * filled + "-" * (bar_len - filled)
        spinner = _SPINNER[self._spinner % len(_SPINNER)]
        self._spinner += 1
        verb = str(pending["verb"] or "working")
        target = str(pending["target"] or pending["action"] or "")
        rows = [
            paint("accent", f"{spinner} {verb}  {current}/{total}  {percent:>3}%"),
            f"[{bar}]",
            str(pending["stats_line"]).strip(),
            str(pending["time_line"]).strip(),
            paint("muted", str(pending["comment_line"]).strip()) if pending["comment_line"] else "",
            paint("muted", target),
        ]
        if self._drawn:
            sys.stdout.write(f"\x1b[{self.lines}A")
        for row in rows:
            sys.stdout.write(fit_line(row, width) + "\x1b[K\n")
        sys.stdout.flush()
        self._drawn = True


def create_renderer(mode: AnimationMode = "auto", no_color: bool = False) -> Renderer | None:
    """Return the dashboard on a capable TTY. Every other case is one line per folder."""
    if _is_truthy_env(os.getenv("UNPACKR_NO_ANIM")) or mode == "off" or no_color:
        return None
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM", "").strip().lower() == "dumb":
        return None
    if _is_truthy_env(os.getenv("CI")):
        return None
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    if not is_tty:
        return None
    return DashboardRenderer()
