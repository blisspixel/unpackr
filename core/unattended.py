"""
Support for unattended runs (timers, path units, cron): a per-source lock,
detection of downloads that are still being written, and desktop notifications.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess  # nosec B404 - fixed argument list, no shell
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from core.remover import is_internal

LOCK_NAME = ".unpackr-lock"
# Windows byte-range locks block reads of the locked bytes; lock one far past the PID text.
_WIN_LOCK_OFFSET = 1 << 20


class RunLock:
    """Exclusive lock on ``<source>/.unpackr-lock`` so overlapping runs exit cleanly.

    The lock is held through an open file handle (flock on POSIX, msvcrt on Windows),
    so it is released by the OS if the process dies; a stale file never blocks a run.
    """

    def __init__(self, source: Path):
        self.path = Path(source) / LOCK_NAME
        self._handle: Optional[Any] = None

    def acquire(self) -> bool:
        handle = open(self.path, "a+")  # noqa: SIM115 - kept open while the lock is held
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(_WIN_LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(_WIN_LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()
        with contextlib.suppress(OSError):
            self.path.unlink()

    def holder(self) -> Optional[str]:
        """PID written by the current holder, for messages."""
        try:
            return self.path.read_text().strip() or None
        except OSError:
            return None

    def __enter__(self) -> "RunLock":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _newest_mtime(entry: Path) -> float:
    try:
        newest = entry.stat().st_mtime
    except OSError:
        return 0.0
    if entry.is_dir() and not entry.is_symlink():
        for root, dirs, files in os.walk(entry):
            dirs[:] = [d for d in dirs if not d.startswith(".unpackr-")]
            for name in (*files, *dirs):
                try:
                    newest = max(newest, (Path(root) / name).stat().st_mtime)
                except OSError:
                    continue
    return newest


def settling_entries(source: Path, quiet_seconds: float, now: Optional[float] = None) -> Set[Path]:
    """Top-level entries of ``source`` with any file or folder changed in the last ``quiet_seconds``.

    A download that is still being written keeps updating modification times, so these
    are skipped this run and picked up by a later one.
    """
    if quiet_seconds <= 0:
        return set()
    now = time.time() if now is None else now
    settling: Set[Path] = set()
    try:
        entries = list(Path(source).iterdir())
    except OSError:
        return settling
    for entry in entries:
        if is_internal(Path(entry.name)):
            continue
        if now - _newest_mtime(entry) < quiet_seconds:
            settling.add(entry)
    return settling


def notification_text(stats: Dict[str, Any], errors: Iterable[str], dry_run: bool = False) -> Optional[Tuple[str, str]]:
    """(title, body) for a run worth telling the user about, or None for a run that did nothing."""
    errors = list(errors)
    moved = int(stats.get("videos_moved", 0) or 0)
    extracted = int(stats.get("archives_extracted", 0) or 0)
    cleaned = int(stats.get("folders_deleted", 0) or 0)
    if not (moved or extracted or cleaned or errors):
        return None
    parts: List[str] = []
    if moved:
        parts.append(f"{moved} video{'s' if moved != 1 else ''} moved")
    if extracted:
        parts.append(f"{extracted} archive{'s' if extracted != 1 else ''} extracted")
    if cleaned and not moved:
        parts.append(f"{cleaned} folder{'s' if cleaned != 1 else ''} cleaned")
    if errors:
        parts.append(
            f"{len(errors)} item{'s' if len(errors) != 1 else ''} need{'s' if len(errors) == 1 else ''} attention"
        )
    title = "unpackr" + (" (dry run)" if dry_run else "")
    body = ", ".join(parts)
    if errors:
        body += "\n" + errors[0]
    return title, body


def send_notification(
    title: str,
    body: str,
    urgency: str = "normal",
    runner: Callable[..., Any] = subprocess.run,
) -> bool:
    """Show a desktop notification with notify-send when it is available."""
    notify_send = shutil.which("notify-send")
    if not notify_send:
        return False
    try:
        runner(
            [notify_send, "--app-name=unpackr", f"--urgency={urgency}", title, body],
            check=False,
            timeout=10,
            capture_output=True,
        )  # nosec B603 - fixed argument list
    except (OSError, subprocess.SubprocessError):
        return False
    return True
