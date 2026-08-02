"""
Cross-platform helpers for Unpackr.

Centralizes OS detection, default external-tool candidates, helper-process
discovery/termination, and platform-specific force-delete fallbacks so the rest
of the codebase can stay policy-focused instead of sprinkling win32 checks.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence


def is_windows() -> bool:
    """Return True when running on Windows."""
    return sys.platform == "win32"


def is_macos() -> bool:
    """Return True when running on macOS."""
    return sys.platform == "darwin"


def is_linux() -> bool:
    """Return True when running on Linux."""
    return sys.platform.startswith("linux")


def is_posix() -> bool:
    """Return True for POSIX-like platforms (Linux, macOS, BSD, ...)."""
    return os.name == "posix"


def platform_label() -> str:
    """Short human-readable platform label for docs and doctor output."""
    if is_windows():
        return "Windows"
    if is_macos():
        return "macOS"
    if is_linux():
        return "Linux"
    return sys.platform


def default_tool_candidates(tool_key: str) -> List[str]:
    """
    Return ordered executable candidates for a tool on the current platform.

    PATH command names come first so package-manager installs win on Linux/macOS.
    Windows absolute paths are appended only on Windows.
    """
    key = (tool_key or "").strip().lower()
    path_first: dict[str, List[str]] = {
        "7z": ["7z", "7zz", "7za"],
        "par2": ["par2"],
        "ffmpeg": ["ffmpeg"],
    }
    candidates = list(path_first.get(key, [key] if key else []))

    if is_windows():
        windows_paths: dict[str, List[str]] = {
            "7z": [
                r"C:\Program Files\7-Zip\7z.exe",
                r"C:\Program Files (x86)\7-Zip\7z.exe",
            ],
            "par2": [
                r"C:\Program Files\par2cmdline\par2.exe",
            ],
            "ffmpeg": [
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files\FFmpeg\bin\ffmpeg.exe",
            ],
        }
        for path in windows_paths.get(key, []):
            if path not in candidates:
                candidates.append(path)
    elif is_macos():
        # Common Homebrew prefixes (Apple Silicon and Intel).
        homebrew_roots = [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
        for root in homebrew_roots:
            for name in list(candidates):
                full = str(root / name)
                if full not in candidates:
                    candidates.append(full)

    return candidates


def merge_tool_candidates(configured: Sequence[str] | str | None, tool_key: str) -> List[str]:
    """
    Merge user-configured tool paths with platform defaults.

    Configured entries keep priority; platform defaults fill gaps.
    """
    if isinstance(configured, str):
        configured_list = [configured]
    elif isinstance(configured, Sequence):
        configured_list = [item for item in configured if isinstance(item, str) and item.strip()]
    else:
        configured_list = []

    merged: List[str] = []
    for item in [*configured_list, *default_tool_candidates(tool_key)]:
        if item not in merged:
            merged.append(item)
    return merged


def helper_process_names() -> dict[str, List[str]]:
    """Map logical helper labels to process name fragments used for detection."""
    if is_windows():
        return {
            "7-Zip": ["7z.exe", "7zfm.exe", "7zg.exe"],
            "par2": ["par2.exe", "par2cmdline"],
            "ffmpeg": ["ffmpeg.exe"],
        }
    return {
        "7-Zip": ["7z", "7zz", "7za"],
        "par2": ["par2"],
        "ffmpeg": ["ffmpeg"],
    }


def detect_running_helpers(labels: Iterable[str] | None = None) -> List[str]:
    """
    Detect running helper processes that may conflict with Unpackr work.

    Returns logical labels such as ``7-Zip`` / ``par2`` / ``ffmpeg``.
    """
    wanted = set(labels) if labels is not None else set(helper_process_names())
    mapping = {label: names for label, names in helper_process_names().items() if label in wanted}
    if not mapping:
        return []

    running: List[str] = []
    try:
        if is_windows():
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (result.stdout or "").lower()
            for label, names in mapping.items():
                if any(name.lower() in output for name in names):
                    running.append(label)
            return running

        # Prefer psutil when available; fall back to `ps`.
        try:
            import psutil

            process_names = {proc.name().lower() for proc in psutil.process_iter(["name"])}
            for label, names in mapping.items():
                if any(any(token in proc_name for token in names) for proc_name in process_names):
                    running.append(label)
            return running
        except Exception:
            result = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=5)
            output = (result.stdout or "").lower()
            for label, names in mapping.items():
                if any(name.lower() in output for name in names):
                    running.append(label)
            return running
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return []


def kill_helper_processes(labels: Sequence[str]) -> bool:
    """
    Terminate known helper process labels.

    Uses taskkill on Windows and pkill on POSIX. Returns True when commands were
    issued without raising; individual process absence is not treated as failure.
    """
    try:
        if is_windows():
            for label in labels:
                if label == "7-Zip":
                    for exe in ["7z.exe", "7zFM.exe", "7zG.exe"]:
                        subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True, timeout=5)
                elif label == "par2":
                    subprocess.run(["taskkill", "/F", "/IM", "par2.exe"], capture_output=True, timeout=5)
                elif label == "ffmpeg":
                    subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], capture_output=True, timeout=5)
            return True

        for label in labels:
            if label == "7-Zip":
                for name in ["7z", "7zz", "7za"]:
                    subprocess.run(["pkill", "-9", "-x", name], capture_output=True, timeout=5)
            elif label == "par2":
                subprocess.run(["pkill", "-9", "-x", "par2"], capture_output=True, timeout=5)
            elif label == "ffmpeg":
                subprocess.run(["pkill", "-9", "-x", "ffmpeg"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def force_delete_directory(folder: Path) -> bool:
    """
    Last-resort directory delete that stays platform-appropriate.

    Windows uses an encoded PowerShell Remove-Item that refuses reparse points.
    POSIX retries with shutil.rmtree(onexc=...) without following symlinks at the root.
    """
    folder = Path(folder)
    if not folder.exists():
        return True

    try:
        if folder.is_symlink():
            logging.warning(f"Refusing force-delete of symlink path: {folder}")
            return False
    except OSError:
        return False

    if is_windows():
        return _force_delete_windows(folder)
    return _force_delete_posix(folder)


def build_powershell_delete_command(folder: Path) -> List[str]:
    """
    Build a PowerShell command that treats the folder path as data rather
    than command text. Windows-only force-delete helper.
    """
    folder_literal = str(folder).replace("'", "''")
    script = (
        f"$target = '{folder_literal}'; "
        "$item = Get-Item -LiteralPath $target -Force -ErrorAction Stop; "
        "if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { exit 3 }; "
        "$reparse = Get-ChildItem -LiteralPath $target -Force -Recurse -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1; "
        "if ($reparse) { exit 3 }; "
        "Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue"
    )
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return ["powershell", "-NoProfile", "-EncodedCommand", encoded_script]


def _force_delete_windows(folder: Path) -> bool:
    try:
        subprocess.run(
            build_powershell_delete_command(folder),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.error(f"Windows force delete failed for {folder}: {exc}")
        return False
    return not folder.exists()


def _force_delete_posix(folder: Path) -> bool:
    def _onerror(func, path, _exc_info):  # noqa: ANN001 - shutil signature
        del func
        path_obj = Path(path)
        try:
            if path_obj.is_symlink() or path_obj.is_file():
                path_obj.unlink(missing_ok=True)
            elif path_obj.is_dir():
                path_obj.rmdir()
        except OSError:
            pass

    try:
        # Use onerror for broad type-checker and runtime compatibility.
        shutil.rmtree(folder, onerror=_onerror)
    except OSError as exc:
        logging.error(f"POSIX force delete failed for {folder}: {exc}")
        return False
    return not folder.exists()


def example_source_path() -> str:
    """Example source path for help text on the current platform."""
    return r"G:\Downloads" if is_windows() else "~/Downloads"


def example_destination_path() -> str:
    """Example destination path for help text on the current platform."""
    return r"G:\Videos" if is_windows() else "~/Videos"
