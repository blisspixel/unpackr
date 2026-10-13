"""
System tools validation for Unpackr.
Checks availability of required external tools.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast

from colorama import Fore, Style

from unpackr.utils.platform_support import detect_running_helpers, kill_helper_processes, merge_tool_candidates

if TYPE_CHECKING:
    import psutil

    # Type-only: importing core at runtime would cycle back through core/__init__.py.
    from unpackr.core.config import ConfigSource


type Version = tuple[int, ...]


class ToolInfo(TypedDict):
    """Static description of an external tool Unpackr can use."""

    name: str
    command: list[str]
    critical: bool
    purpose: str


def _configured_tool_paths(config: ConfigSource) -> dict[str, object]:
    """The ``tool_paths`` mapping from config, or {} when it is missing or malformed."""
    tool_paths = config.get("tool_paths", {})
    if not isinstance(tool_paths, dict):
        return {}
    return cast(dict[str, object], tool_paths)


class SystemCheck:
    """Validates system requirements and external tools."""

    MIN_TOOL_VERSIONS: ClassVar[dict[str, Version]] = {
        "7z": (22, 0),
        "par2": (0, 8, 1),
        "ffmpeg": (4, 4),
    }

    REQUIRED_TOOLS: ClassVar[dict[str, ToolInfo]] = {
        "7z": {"name": "7-Zip", "command": ["7z"], "critical": True, "purpose": "RAR/7z extraction"},
        "par2": {
            "name": "par2cmdline",
            "command": ["par2"],
            "critical": False,
            "purpose": "PAR2 repair (recommended for reliability)",
        },
        "ffmpeg": {
            "name": "FFmpeg",
            "command": ["ffmpeg", "-version"],
            "critical": False,
            "purpose": "video health checks",
        },
    }

    def __init__(self, config: ConfigSource | None = None) -> None:
        """Initialize SystemCheck with optional config containing tool paths."""
        self.config: ConfigSource = config or {}
        self._version_status: dict[str, tuple[bool, str]] = {}
        # Tool key -> executable that answered during check_tool().
        self._working_paths: dict[str, str] = {}
        # Set by the CLI so conflict handling only touches helpers working on this source.
        self.source_dir: Path | None = None
        self.dry_run = False

    def check_tool(self, tool_key: str) -> bool:
        """
        Check if a specific tool is available.

        Args:
            tool_key: Key from REQUIRED_TOOLS dict

        Returns:
            True if tool is available, False otherwise
        """
        tool_info = self.REQUIRED_TOOLS.get(tool_key)
        if not tool_info:
            return False

        # Get tool path from config if available, then merge platform defaults.
        custom_paths = merge_tool_candidates(_configured_tool_paths(self.config).get(tool_key), tool_key)

        # Try each path until one works
        for custom_path in custom_paths:
            resolved_path = self._resolve_tool_path(custom_path)
            if not resolved_path:
                continue

            try:
                command = [resolved_path]
                if tool_key == "ffmpeg":
                    command.append("-version")

                subprocess.run(command, capture_output=True, timeout=2)
                # If we get here, it worked - store the working path
                self._working_paths[tool_key] = resolved_path
                return True
            except (OSError, subprocess.TimeoutExpired):
                # OSError covers a missing file and one that exists but cannot be executed.
                continue

        return False

    @staticmethod
    def _looks_like_relative_filesystem_path(path_str: str) -> bool:
        """Return True for relative filesystem paths such as .\bin\tool.exe."""
        return not os.path.isabs(path_str) and (os.sep in path_str or "/" in path_str or path_str.startswith("."))

    def _resolve_tool_path(self, tool_path: str) -> str:
        """Resolve a configured tool entry to an absolute executable path."""
        candidate = (tool_path or "").strip()
        if not candidate:
            return ""

        if os.path.isabs(candidate):
            return candidate if os.path.isfile(candidate) else ""

        if self._looks_like_relative_filesystem_path(candidate):
            return ""

        return shutil.which(candidate) or ""

    @staticmethod
    def _extract_version_tuple(text: str) -> Version | None:
        """Extract first semantic-like version tuple from command output."""
        match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
        if not match:
            return None
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3)) if match.group(3) is not None else 0
        return (major, minor, patch)

    @staticmethod
    def _is_version_at_least(found: Version, minimum: Version) -> bool:
        """Compare versions with zero-padding semantics."""
        max_len = max(len(found), len(minimum))
        found_norm = found + (0,) * (max_len - len(found))
        min_norm = minimum + (0,) * (max_len - len(minimum))
        return found_norm >= min_norm

    @staticmethod
    def _format_version(version: Version) -> str:
        """Format version tuple for status output."""
        if len(version) >= 3 and version[2] == 0:
            return f"{version[0]}.{version[1]}"
        return ".".join(str(v) for v in version)

    def _get_tool_version(self, tool_key: str) -> Version | None:
        """Best-effort version detection for an available tool."""
        command = self.get_tool_command(tool_key)
        if not command:
            return None

        if tool_key == "ffmpeg":
            command = [command[0], "-version"]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3,
            )
            combined = f"{result.stdout}\n{result.stderr}"
            return self._extract_version_tuple(combined)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _evaluate_tool_version(self, tool_key: str) -> tuple[bool, str]:
        """
        Evaluate tool version policy.

        Returns:
            tuple(is_supported, message)
        """
        minimum = self.MIN_TOOL_VERSIONS.get(tool_key)
        if minimum is None:
            return True, "version policy not configured"

        found = self._get_tool_version(tool_key)
        if found is None:
            return True, "version unknown"

        found_text = self._format_version(found)
        min_text = self._format_version(minimum)
        if self._is_version_at_least(found, minimum):
            return True, f"{found_text}"
        return False, f"{found_text} (need {min_text}+)"

    def check_all_tools(self) -> dict[str, bool]:
        """
        Check all required tools.

        Returns:
            Dictionary mapping tool keys to availability status
        """
        results: dict[str, bool] = {}
        self._version_status = {}
        for tool_key in self.REQUIRED_TOOLS:
            is_available = self.check_tool(tool_key)
            results[tool_key] = is_available

            # Evaluate version policy only for discovered tools.
            if is_available:
                version_ok, version_msg = self._evaluate_tool_version(tool_key)
                self._version_status[tool_key] = (version_ok, version_msg)
                # Critical tools with unsupported versions are blocking.
                if not version_ok and self.REQUIRED_TOOLS[tool_key]["critical"]:
                    results[tool_key] = False
        return results

    def display_tool_status(self, tools_status: dict[str, bool]) -> bool:
        """
        Display status of all tools and check if we can proceed.

        Args:
            tools_status: Dictionary from check_all_tools()

        Returns:
            True if we can proceed, False if critical tools missing
        """
        can_proceed = True
        status_parts: list[str] = []

        for tool_key, is_available in tools_status.items():
            tool_info = self.REQUIRED_TOOLS[tool_key]
            version_status = self._version_status.get(tool_key)

            if is_available:
                if version_status is not None and not version_status[0]:
                    # Unsupported version: block only when tool is marked critical.
                    if tool_info["critical"]:
                        status_parts.append(
                            f"{Fore.RED}{tool_info['name']}: OLD ({version_status[1]}){Style.RESET_ALL}"
                        )
                        can_proceed = False
                    else:
                        status_parts.append(
                            f"{Fore.YELLOW}{tool_info['name']}: OLD ({version_status[1]}){Style.RESET_ALL}"
                        )
                else:
                    status_parts.append(f"{Fore.GREEN}{tool_info['name']}: OK{Style.RESET_ALL}")
            else:
                if tool_info["critical"]:
                    status_parts.append(f"{Fore.RED}{tool_info['name']}: MISSING{Style.RESET_ALL}")
                    can_proceed = False
                else:
                    status_parts.append(f"{Fore.YELLOW}{tool_info['name']}: SKIP{Style.RESET_ALL}")

        print(" | ".join(status_parts))

        if not can_proceed:
            print(Fore.RED + "ERROR: Critical tools missing! Cannot continue." + Style.RESET_ALL)
            print(
                f"{Fore.YELLOW}TIP: Update 'tool_paths' in the active config and pass it with --config{Style.RESET_ALL}"
            )

        return can_proceed

    def get_tool_command(self, tool_key: str) -> list[str]:
        """
        Get the command to run for a specific tool.

        Args:
            tool_key: Key from REQUIRED_TOOLS dict

        Returns:
            List of command parts to execute
        """
        tool_info = self.REQUIRED_TOOLS.get(tool_key)
        if not tool_info:
            return []

        # Use working path if we found one during check
        if tool_key in self._working_paths:
            return [self._working_paths[tool_key]]

        # Get tool path from config if available, then merge platform defaults.
        custom_paths = merge_tool_candidates(_configured_tool_paths(self.config).get(tool_key), tool_key)

        for custom_path in custom_paths:
            resolved_path = self._resolve_tool_path(custom_path)
            if resolved_path:
                return [resolved_path]

        return []

    def check_running_processes(self) -> tuple[bool, list[str]]:
        """
        Check if 7z or par2 processes are already running.

        Returns:
            Tuple of (has_conflicts, list of running process names)
        """
        try:
            running = detect_running_helpers(["7-Zip", "par2"])
        except Exception:
            return False, []
        return len(running) > 0, running

    def kill_processes(self, process_names: list[str]) -> bool:
        """
        Kill specific processes.

        Args:
            process_names: List of process names to kill (e.g., ['7-Zip', 'par2'])

        Returns:
            True if successful, False otherwise
        """
        return kill_helper_processes(process_names)

    HELPER_NAMES: ClassVar[set[str]] = {
        "7z",
        "7zz",
        "7za",
        "7z.exe",
        "7zz.exe",
        "par2",
        "par2.exe",
        "ffmpeg",
        "ffmpeg.exe",
    }

    def find_source_processes(self, source_dir: Path) -> list[psutil.Process]:
        """Helper processes (7-Zip, par2, ffmpeg) whose command line points into source_dir."""
        import psutil  # imported lazily so doctor can report a missing psutil

        source = str(Path(source_dir).absolute())
        found: list[psutil.Process] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                cmdline: list[str] = proc.info.get("cmdline") or []
            except (psutil.Error, OSError):
                continue
            if name in self.HELPER_NAMES and any(source in str(arg) for arg in cmdline):
                found.append(proc)
        return found

    def _handle_processes_for_source(self, source_dir: Path, dry_run: bool) -> bool:
        """Stop only helpers left over from a run on this source; never touch other work."""
        import psutil

        leftovers = self.find_source_processes(source_dir)
        _has_any, running = self.check_running_processes()
        if running and not leftovers:
            print(
                f"{Fore.CYAN}Note: {', '.join(running)} running for other work; Unpackr leaves it alone.{Style.RESET_ALL}"
            )
            return True
        if not leftovers:
            return True
        names = ", ".join(sorted({f"{p.info.get('name')} (pid {p.pid})" for p in leftovers}))
        if dry_run:
            print(f"{Fore.YELLOW}Leftover processes on this source (not stopped in dry-run): {names}{Style.RESET_ALL}")
            return True
        print(f"{Fore.YELLOW}Stopping leftover processes from a previous run on this source: {names}{Style.RESET_ALL}")
        for proc in leftovers:
            with contextlib.suppress(psutil.Error, OSError):
                proc.terminate()
        _gone, alive = psutil.wait_procs(leftovers, timeout=3)
        for proc in alive:
            with contextlib.suppress(psutil.Error, OSError):
                proc.kill()
        return True

    def warn_running_processes(self) -> bool:
        """
        Check for running processes and kill them automatically.

        When ``source_dir`` is set on this object, only helpers working inside that
        source are stopped (never during ``dry_run``); unrelated 7-Zip, par2 or
        ffmpeg processes are left running.

        Returns:
            True if should continue, False if user wants to abort
        """
        source_dir = getattr(self, "source_dir", None)
        if source_dir is not None:
            return self._handle_processes_for_source(Path(source_dir), bool(getattr(self, "dry_run", False)))

        has_conflicts, running = self.check_running_processes()

        if has_conflicts:
            print(f"\n{Fore.YELLOW}WARNING: Found orphaned processes from previous session:{Style.RESET_ALL}")
            for proc in running:
                print(f"  - {Fore.YELLOW}{proc}{Style.RESET_ALL}")

            print(
                f"\n{Fore.CYAN}Auto-killing in 3 seconds...{Style.RESET_ALL} {Style.DIM}(Ctrl+C to abort){Style.RESET_ALL}"
            )

            try:
                import time

                for i in range(3, 0, -1):
                    print(f"  {i}...", end="\r", flush=True)
                    time.sleep(1)
                print("      ", end="\r")  # Clear countdown

                # Kill the processes
                if self.kill_processes(running):
                    print(f"{Fore.GREEN}OK: Killed orphaned processes{Style.RESET_ALL}")
                else:
                    print(
                        f"{Fore.YELLOW}WARNING: Could not kill some processes - you may need admin rights{Style.RESET_ALL}"
                    )

                # Verify they're gone
                time.sleep(0.5)
                still_running = self.check_running_processes()[1]
                if still_running:
                    print(
                        f"{Fore.YELLOW}WARNING: Some processes still running: {', '.join(still_running)}{Style.RESET_ALL}"
                    )
                    print(
                        f"{Fore.YELLOW}  File locks may cause issues. Continue anyway? (Enter to continue, Ctrl+C to abort){Style.RESET_ALL}"
                    )
                    input()

            except KeyboardInterrupt:
                print(f"\n{Fore.RED}ERROR: Aborted by user{Style.RESET_ALL}")
                return False

        return True
