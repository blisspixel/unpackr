"""
Send files to the desktop trash without third-party dependencies.

- Linux and other freedesktop systems: the XDG Trash specification
  (https://specifications.freedesktop.org/trash-spec/latest/), home trash when
  the file is on the same device, otherwise ``$topdir/.Trash-$uid``.
- macOS: ``~/.Trash`` on the boot volume, ``<volume>/.Trashes/<uid>`` elsewhere.
- Windows: the Recycle Bin through ``SHFileOperationW`` with ``FOF_ALLOWUNDO``.

Every function moves the path (file or directory) and returns where it went.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote


class TrashError(OSError):
    """Raised when a path could not be moved to the trash."""


def _mount_point(path: Path) -> Path:
    path = path.resolve()
    device = path.stat().st_dev
    while path.parent != path and path.parent.stat().st_dev == device:
        path = path.parent
    return path


def _unique_name(directory: Path, name: str) -> str:
    candidate = name
    stem, dot, suffix = name.partition(".")
    counter = 2
    while (directory / candidate).exists() or (directory.parent / "info" / f"{candidate}.trashinfo").exists():
        candidate = f"{stem}.{counter}{dot}{suffix}" if dot else f"{name}.{counter}"
        counter += 1
    return candidate


def _freedesktop_trash(path: Path) -> Path:
    path = path.absolute()
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    home_trash = data_home / "Trash"
    home_trash.mkdir(parents=True, exist_ok=True, mode=0o700)
    use_home = os.stat(path, follow_symlinks=False).st_dev == home_trash.stat().st_dev
    if use_home:
        trash_root = home_trash
        info_path_value = str(path)
    else:
        topdir = _mount_point(path.parent)
        trash_root = topdir / f".Trash-{os.getuid()}"
        trash_root.mkdir(exist_ok=True, mode=0o700)
        info_path_value = str(path.relative_to(topdir))
    files_dir = trash_root / "files"
    info_dir = trash_root / "info"
    files_dir.mkdir(exist_ok=True, mode=0o700)
    info_dir.mkdir(exist_ok=True, mode=0o700)

    name = _unique_name(files_dir, path.name)
    info_file = info_dir / f"{name}.trashinfo"
    deletion_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    content = f"[Trash Info]\nPath={quote(info_path_value)}\nDeletionDate={deletion_date}\n"
    # The spec requires the info file to be created atomically before the move.
    fd = os.open(info_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    target = files_dir / name
    try:
        os.rename(path, target)
    except OSError:
        info_file.unlink(missing_ok=True)
        raise
    return target


def _macos_trash(path: Path) -> Path:
    path = path.absolute()
    home_trash = Path.home() / ".Trash"
    if home_trash.exists() and os.stat(path, follow_symlinks=False).st_dev == home_trash.stat().st_dev:
        trash_dir = home_trash
    else:
        trash_dir = _mount_point(path.parent) / ".Trashes" / str(os.getuid())
        trash_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = trash_dir / path.name
    counter = 2
    while target.exists():
        target = trash_dir / f"{path.stem} {counter}{path.suffix}"
        counter += 1
    os.rename(path, target)
    return target


def _windows_recycle(path: Path) -> Path:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    fo_delete = 0x0003
    flags = 0x0040 | 0x0010 | 0x0400 | 0x0004  # ALLOWUNDO | NOCONFIRMATION | NOERRORUI | SILENT
    operation = SHFILEOPSTRUCTW(
        hwnd=None,
        wFunc=fo_delete,
        pFrom=str(path.absolute()) + "\0\0",
        pTo=None,
        fFlags=flags,
        fAnyOperationsAborted=False,
        hNameMappings=None,
        lpszProgressTitle=None,
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))  # type: ignore[attr-defined]
    if result != 0 or operation.fAnyOperationsAborted or path.exists():
        raise TrashError(f"Recycle Bin refused {path} (code {result})")
    return Path("$Recycle.Bin") / path.name


def send_to_trash(path: Path, platform: Optional[str] = None) -> Path:
    """Move ``path`` to the desktop trash and return its new location."""
    platform = platform or sys.platform
    if not os.path.lexists(path):
        raise FileNotFoundError(str(path))
    try:
        if platform.startswith("win"):
            return _windows_recycle(path)
        if platform == "darwin":
            return _macos_trash(path)
        return _freedesktop_trash(path)
    except TrashError:
        raise
    except OSError as e:
        raise TrashError(f"Could not move {path} to the trash: {e}") from e
