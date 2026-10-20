"""Point-in-time checks for a file that is still being written.

A media probe only describes the bytes it could read. It does not prove the
writer has finished. These helpers compare size and modification time across
the probe, and, when the operating system will say so, notice a process that
still has the file open.

This is not a universal writer detector. A writer that stays quiet for the
whole check and does not appear in the open-file list can still be missed.
Callers recheck at the mutation boundary, immediately before a move.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

T = TypeVar("T")

# Files untouched for longer than this skip the process scan. A download that
# is still writing has a fresh modification time.
RECENT_SECONDS = 2.0
# Extra watch used when the probe itself returns faster than this.
WINDOW_SECONDS = 0.15


@dataclass(frozen=True)
class FileStamp:
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class Activity:
    """``settled`` may be moved. ``active`` and ``inconclusive`` stay put."""

    state: str
    reason: str
    stamp: FileStamp | None

    @property
    def held(self) -> bool:
        return self.state != "settled"


def file_stamp(path: Path) -> FileStamp | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
    return FileStamp(stat.st_size, int(mtime_ns))


def writer_visible(path: Path) -> bool | None:
    """True when a process has the file open, False when none of the processes we could inspect do.

    None means the check could not tell. That is inconclusive on its own and is
    not treated as proof that nobody is writing.

    Windows asks the kernel whether any handle already has the file (a sharing
    violation). That is one call. Other systems look through process open-file
    lists and stop if that takes longer than ``WRITER_SCAN_SECONDS``.
    """
    if sys.platform == "win32":
        return _windows_sharing_conflict(path)
    return _scan_open_files(path)


# A full process listing can take longer than a folder. Past this, the size
# check is the evidence we keep.
WRITER_SCAN_SECONDS = 0.35


def _windows_sharing_conflict(path: Path) -> bool | None:
    """True when CreateFile with no sharing fails because another handle exists.

    ``WinDLL`` and ``get_last_error`` exist only in the Windows stubs. Looking
    them up by name keeps Linux type-checking from failing on this function.
    """
    import ctypes

    windll_ctor = cast(Callable[..., Any] | None, getattr(ctypes, "WinDLL", None))
    last_error = cast(Callable[[], int] | None, getattr(ctypes, "get_last_error", None))
    types = cast(Any, getattr(ctypes, "wintypes", None))
    if windll_ctor is None or last_error is None or types is None:
        return None
    kernel = windll_ctor("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        types.LPCWSTR,
        types.DWORD,
        types.DWORD,
        types.LPVOID,
        types.DWORD,
        types.DWORD,
        types.HANDLE,
    ]
    create.restype = types.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [types.HANDLE]
    close.restype = types.BOOL
    handle = create(str(path), 0x80000000, 0, None, 3, 0x80, None)
    invalid = types.HANDLE(-1).value
    # 32 is ERROR_SHARING_VIOLATION: someone already has the file.
    if invalid is not None and int(handle) == int(invalid):
        if last_error() == 32:
            return True
        return None
    close(handle)
    return False


def _scan_open_files(path: Path, *, budget: float = WRITER_SCAN_SECONDS) -> bool | None:
    try:
        import psutil
    except ImportError:
        return None
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    target = str(path)
    inspected = False
    try:
        processes = psutil.process_iter(["pid"])
    except (psutil.Error, OSError):
        return None
    deadline = time.monotonic() + budget
    for proc in processes:
        if time.monotonic() >= deadline:
            return None
        try:
            opened = proc.open_files()
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
        inspected = True
        for item in opened:
            name = getattr(item, "path", "")
            if name in (target, resolved):
                return True
    if not inspected:
        return None
    return False


def _changed(path: Path, earlier: FileStamp) -> FileStamp | None:
    """Return the new stamp when the file changed or disappeared, else None."""
    later = file_stamp(path)
    if later is None or later != earlier:
        return later
    return None


def observe(
    path: Path,
    *,
    probe: Callable[[], T] | None = None,
    writers: Callable[[Path], bool | None] = writer_visible,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.monotonic,
    window: float = WINDOW_SECONDS,
    recent: float = RECENT_SECONDS,
) -> tuple[Activity, T | None]:
    """Watch ``path`` across ``probe`` (the media check) and report whether it is still changing."""
    first = file_stamp(path)
    if first is None:
        result = probe() if probe is not None else None
        return Activity("inconclusive", "unreadable", None), result

    age = clock() - (first.mtime_ns / 1_000_000_000)
    scan_writers = age <= recent
    if scan_writers and writers(path) is True:
        result = probe() if probe is not None else None
        return Activity("active", "writer", file_stamp(path) or first), result

    started = monotonic()
    result = probe() if probe is not None else None
    elapsed = monotonic() - started
    if scan_writers and elapsed < window:
        sleep(window - elapsed)

    later = _changed(path, first)
    if later is not None:
        return Activity("active", "growing", later), result
    if file_stamp(path) is None:
        return Activity("inconclusive", "unreadable", None), result
    reason = "mtime" if not scan_writers else "window"
    return Activity("settled", reason, first), result


def drifted(
    path: Path,
    earlier: FileStamp | None,
    *,
    writers: Callable[[Path], bool | None] = writer_visible,
    clock: Callable[[], float] = time.time,
    recent: float = RECENT_SECONDS,
) -> bool:
    """Recheck at the mutation boundary. True means the file must not be moved."""
    if earlier is None:
        return True
    current = file_stamp(path)
    if current is None or current != earlier:
        return True
    age = clock() - (current.mtime_ns / 1_000_000_000)
    return age <= recent and writers(path) is True
