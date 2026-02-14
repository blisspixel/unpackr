"""Cross-platform CLI rendering helpers with optional Rich support."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Literal, Optional

AnimationMode = Literal["auto", "off", "light", "full"]


def _is_truthy_env(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class PlainRenderer:
    """Minimal carriage-return renderer used when Rich is unavailable."""

    def __init__(self) -> None:
        self._started = False

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
        percent = int((current / total) * 100) if total > 0 else 0
        line = f"[{percent:>3}%] {current}/{total} {verb}: {target or action}"
        sys.stdout.write("\r" + line[:140] + " " * max(0, 140 - len(line)))
        sys.stdout.flush()

    def stop(self) -> None:
        if self._started:
            sys.stdout.write("\n")
            sys.stdout.flush()
        self._started = False


class RichRenderer:  # pragma: no cover - optional path when Rich is installed in interactive terminals
    """Rich Live renderer for smooth status/progress updates."""

    def __init__(self, no_color: bool = False, mode: AnimationMode = "light") -> None:
        from rich.console import Console, Group
        from rich.live import Live
        from rich.text import Text

        self._Console = Console
        self._Group = Group
        self._Text = Text
        self.console = Console(no_color=no_color)
        self.live = Live(console=self.console, refresh_per_second=10, transient=False, auto_refresh=True)
        self._started = False
        self._spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx = 0
        self._last_render = 0.0
        self._frame = 0
        self.mode = mode
        self._tte_highlighter = self._build_tte_highlighter() if mode == "full" else None

    def _build_tte_highlighter(self):
        """
        Optional TTE integration.
        The implementation is intentionally defensive so missing/changed APIs fall back safely.
        """
        try:
            # Optional dependency; may not exist in runtime environments.
            import terminaltexteffects  # type: ignore # noqa: F401
        except Exception:
            return None
        return None

    def _shimmer_text(self, value: str):
        """
        Create a subtle monochrome shimmer sweep for full animation mode.
        Uses pure Rich styling by default; TTE can be integrated later via _tte_highlighter.
        """
        text = self._Text()
        if not value:
            return text

        # Base style for calm status lines.
        base_style = "rgb(110,110,110)"
        for ch in value:
            text.append(ch, style=base_style)

        width = max(4, min(14, len(value) // 4))
        center = self._frame % (len(value) + width)
        self._frame += 1

        start = max(0, center - width)
        end = min(len(value), center)
        for idx in range(start, end):
            text.stylize("rgb(225,225,245)", idx, idx + 1)
        return text

    def start(self, _total: int) -> None:
        if self._started:
            return
        self.live.start()
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
        if not self._started:
            self.start(total)

        now = time.time()
        if now - self._last_render < 0.07:
            return
        self._last_render = now

        percent = int((current / total) * 100) if total > 0 else 0
        bar_len = 36
        filled = int(bar_len * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        spinner = self._spinner[self._spinner_idx]
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner)

        header = self._Text(f"{spinner} {verb}  {current}/{total} folders  {percent:>3}%", style="bold cyan")
        progress = self._Text(f"[{bar}]", style="green")
        line_action_text = target or action
        if self.mode == "full":
            line_action = self._shimmer_text(line_action_text)
        else:
            line_action = self._Text(line_action_text, style="bold white")
        line_stats = self._Text(stats_line, style="dim")
        line_time = self._Text(time_line, style="dim")
        line_comment = self._Text(comment_line, style="yellow") if comment_line else self._Text("")

        self.live.update(self._Group(header, progress, line_action, line_stats, line_time, line_comment))

    def stop(self) -> None:
        if self._started:
            self.live.stop()
        self._started = False


def create_renderer(mode: AnimationMode = "auto", no_color: bool = False) -> Optional[Any]:
    """
    Return a renderer instance suitable for this terminal.

    Uses Rich only in interactive terminals unless forced by environment.
    """
    if _is_truthy_env(os.getenv("UNPACKR_NO_ANIM")):
        return None

    if mode == "off":
        return None

    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    in_ci = _is_truthy_env(os.getenv("CI"))

    if mode == "auto":
        if not is_tty or in_ci:
            return None
    else:
        # Even explicit light/full should degrade gracefully in CI/non-interactive contexts.
        if not is_tty or in_ci:
            return None

    try:
        rich_mode: AnimationMode = "light" if mode == "auto" else mode
        return RichRenderer(no_color=no_color, mode=rich_mode)
    except Exception:
        return PlainRenderer()
