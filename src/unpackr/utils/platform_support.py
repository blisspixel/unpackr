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
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, cast


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


LINUX_INSTALL_COMMANDS = {
    "arch": "Arch/Manjaro/Omarchy: sudo pacman -S 7zip par2cmdline ffmpeg",
    "debian": "Debian 12+/Ubuntu 24.04+: sudo apt install 7zip par2 ffmpeg",
    "fedora": "Fedora/RHEL: sudo dnf install 7zip par2cmdline ffmpeg",
    "suse": "openSUSE: sudo zypper install 7zip par2cmdline ffmpeg",
}
NO_ROOT_7Z_HINT = "Without root: download the static 7zz from https://www.7-zip.org/ and set tool_paths.7z to its path."


def linux_distro_family(os_release: Path = Path("/etc/os-release")) -> str | None:
    """Return "arch", "debian", "fedora" or "suse" from os-release ID/ID_LIKE, else None."""
    try:
        text = os_release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    ids: list[str] = []
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids.extend(value.strip().strip('"').lower().split())
    for family, members in (
        ("arch", {"arch", "manjaro", "endeavouros", "omarchy", "garuda", "cachyos"}),
        ("debian", {"debian", "ubuntu", "linuxmint", "pop", "raspbian"}),
        ("fedora", {"fedora", "rhel", "centos", "rocky", "almalinux"}),
        ("suse", {"suse", "opensuse", "opensuse-leap", "opensuse-tumbleweed", "sles"}),
    ):
        if members.intersection(ids):
            return family
    return None


def user_state_dir(app: str = "unpackr") -> Path:
    """Per-user directory for logs and state: XDG state dir, ~/Library/Logs, or %LOCALAPPDATA%."""
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / app
    if is_macos():
        return Path.home() / "Library" / "Logs" / app
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / app


def package_manager_install_hint() -> str:
    """Return a short install recipe for required/recommended external tools."""
    if is_windows():
        return (
            "Install 7-Zip from https://www.7-zip.org/ and put par2/ffmpeg on PATH "
            "(or set absolute paths in config tool_paths)."
        )
    if is_macos():
        return "brew install sevenzip par2 ffmpeg"
    if is_linux():
        family = linux_distro_family()
        if family in LINUX_INSTALL_COMMANDS:
            return f"{LINUX_INSTALL_COMMANDS[family]}. {NO_ROOT_7Z_HINT}"
        return " | ".join(LINUX_INSTALL_COMMANDS.values()) + f". {NO_ROOT_7Z_HINT}"
    return "Install 7z/7zz, par2, and ffmpeg via your platform package manager and ensure they are on PATH."


def tool_missing_hint(tool_key: str, include_recipe: bool = True) -> str:
    """Return a platform-specific remediation line for a missing tool."""
    key = (tool_key or "").strip().lower()
    names = {
        "7z": "7-Zip / p7zip (`7z` or `7zz`)",
        "par2": "par2cmdline (`par2`)",
        "ffmpeg": "ffmpeg",
    }
    label = names.get(key, key or "the required tool")
    if not include_recipe:
        return f"Install {label}."
    return f"Install {label}. {package_manager_install_hint()}"


def default_tool_candidates(tool_key: str) -> list[str]:
    """
    Return ordered executable candidates for a tool on the current platform.

    PATH command names come first so package-manager installs win on Linux/macOS.
    Windows absolute paths are appended only on Windows.
    """
    key = (tool_key or "").strip().lower()
    # 7zz is the official 7-Zip binary and always current; an old p7zip `7z` (16.02)
    # is below the 22.0 minimum, so 7zz wins when both are installed.
    path_first: dict[str, list[str]] = {
        "7z": ["7zz", "7z", "7za"],
        "par2": ["par2"],
        "ffmpeg": ["ffmpeg"],
    }
    candidates = list(path_first.get(key, [key] if key else []))

    if is_windows():
        windows_paths: dict[str, list[str]] = {
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


def merge_tool_candidates(configured: object, tool_key: str) -> list[str]:
    """
    Merge user-configured tool paths with platform defaults.

    Configured entries keep priority; platform defaults fill gaps.
    """
    if isinstance(configured, str):
        configured_list = [configured]
    elif isinstance(configured, Sequence):
        # Config values come from JSON, so entries are validated individually.
        entries = cast(Sequence[object], configured)
        configured_list = [item for item in entries if isinstance(item, str) and item.strip()]
    else:
        configured_list = []

    merged: list[str] = []
    for item in [*configured_list, *default_tool_candidates(tool_key)]:
        if item not in merged:
            merged.append(item)
    return merged


def resolve_first_available_tool(tool_key: str, configured: object = None) -> str:
    """
    Resolve the first usable executable for a tool key.

    Returns an empty string when nothing is found.
    """
    for candidate in merge_tool_candidates(configured, tool_key):
        candidate = (candidate or "").strip()
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_absolute():
            if path.is_file():
                return str(path)
            continue
        # Reject relative filesystem paths for safety (same policy as SystemCheck).
        if os.sep in candidate or "/" in candidate or candidate.startswith("."):
            continue
        found = shutil.which(candidate)
        if found:
            return found
    return ""


def helper_process_names() -> dict[str, list[str]]:
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


def detect_running_helpers(labels: Iterable[str] | None = None) -> list[str]:
    """
    Detect running helper processes that may conflict with Unpackr work.

    Returns logical labels such as ``7-Zip`` / ``par2`` / ``ffmpeg``.
    """
    wanted = set(labels) if labels is not None else set(helper_process_names())
    mapping = {label: names for label, names in helper_process_names().items() if label in wanted}
    if not mapping:
        return []

    running: list[str] = []
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
    POSIX retries with shutil.rmtree(onerror=...) without following symlinks at the root.
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


def build_powershell_delete_command(folder: Path) -> list[str]:
    """
    Build a PowerShell command that treats the folder path as data rather
    than command text. Windows-only force-delete helper.
    """
    folder_text = str(folder)
    if "\n" in folder_text or "\r" in folder_text or "\x00" in folder_text:
        raise ValueError("refusing a force-delete path that contains a newline or NUL")
    folder_literal = folder_text.replace("'", "''")
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
        if any(char in str(folder) for char in ("\n", "\r", "\x00")):
            logging.error(f"Refusing force-delete of a path with a newline or NUL: {folder!r}")
            return False
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
    def _onexc(func: Callable[..., object], path: str, _exc: BaseException) -> None:
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
        remover: Any = shutil.rmtree
        if sys.version_info >= (3, 12):
            remover(folder, onexc=_onexc)
        else:
            remover(folder, onerror=_onexc)
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
