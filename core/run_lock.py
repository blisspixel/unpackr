"""
A per-source lock so two runs never process the same downloads folder at once.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import TextIO

LOCK_NAME = ".unpackr-lock"
# Windows byte-range locks block reads of the locked bytes; lock one far past the PID text.
_WIN_LOCK_OFFSET = 1 << 20


class RunLock:
    """Exclusive lock on ``<source>/.unpackr-lock`` so overlapping runs exit cleanly.

    The lock is held through an open file handle (flock on POSIX, msvcrt on Windows),
    so it is released by the OS if the process dies; a stale file never blocks a run.
    """

    def __init__(self, source: Path) -> None:
        self.path = Path(source) / LOCK_NAME
        self._handle: TextIO | None = None

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

    def holder(self) -> str | None:
        """PID written by the current holder, for messages."""
        try:
            return self.path.read_text().strip() or None
        except OSError:
            return None

    def __enter__(self) -> RunLock:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
