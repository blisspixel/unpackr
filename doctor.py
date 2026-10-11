"""
Unpackr Doctor - Diagnostic tool to check system health and configuration.
Run this to verify everything is set up correctly before processing.
"""

import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal, TypedDict, cast

from colorama import Fore, Style, init

from utils.cli_runtime import existing_file_path
from utils.filesystem_policy import probe_filesystem
from utils.platform_support import (
    detect_running_helpers,
    merge_tool_candidates,
    package_manager_install_hint,
    platform_label,
    tool_missing_hint,
)

init(autoreset=True)

type Version = tuple[int, ...]


class DoctorCounts(TypedDict):
    passed: int
    warnings: int
    issues: int


class DoctorReport(TypedDict):
    """The `unpackr-doctor --json` contract (see docs/DOCTOR_JSON.md)."""

    timestamp_utc: str
    exit_code: int
    status: Literal["ready", "blocked"]
    counts: DoctorCounts
    passed: list[str]
    warnings: list[str]
    issues: list[str]
    recommended_actions: list[str]


class UnpackrDoctor:
    """Diagnostic tool for Unpackr setup."""

    MIN_TOOL_VERSIONS: ClassVar[dict[str, Version]] = {
        "7z": (22, 0),
        "par2": (0, 8, 1),
        "ffmpeg": (4, 4),
    }

    def __init__(self, config_path: Path | None = None, source: Path | None = None) -> None:
        self.config_path = config_path
        self.source = source
        self.issues: list[str] = []
        self.warnings: list[str] = []
        self.passed: list[str] = []

    def _config_file(self) -> Path:
        """Return the explicit config path or the bundled default."""
        return self.config_path or Path(__file__).parent / "config_files" / "config.json"

    def _step(self, number: int) -> str:
        total = 11 + (1 if self.source is not None else 0)
        return f"{Fore.YELLOW}[{number}/{total}]{Style.RESET_ALL}"

    def print_header(self) -> None:
        """Print diagnostic header."""
        print(f"\n{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Unpackr Doctor - System Diagnostic{Style.RESET_ALL}")
        print(f"{Style.DIM}Checks runtime, tools, config, and safety prerequisites{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

    def _build_recommended_actions(self) -> list[str]:
        """Generate actionable remediation steps from current findings."""
        actions: list[str] = []
        issue_text = " ".join(self.issues).lower()
        warning_text = " ".join(self.warnings).lower()

        if "python version too old" in issue_text:
            actions.append("Install Python 3.12+ and run doctor again.")
        if "7-zip not found" in issue_text:
            actions.append(tool_missing_hint("7z", include_recipe=False))
        if "7-zip version too old" in issue_text:
            actions.append("Upgrade 7-Zip/p7zip to a supported version (22.0+).")
        if "par2cmdline not found" in issue_text or "par2cmdline not found" in warning_text:
            actions.append(tool_missing_hint("par2", include_recipe=False))
        if "par2cmdline version too old" in warning_text:
            actions.append("Upgrade par2cmdline to 0.8.1+ for stable repair behavior.")
        if "missing packages:" in issue_text:
            actions.append("Install required Python packages with `python -m pip install .`.")
        if "config" in issue_text and "json" in issue_text:
            actions.append(f"Fix the active config file: `{self._config_file()}`.")
        if "write permissions" in issue_text:
            actions.append("Run from a writable directory or adjust folder permissions.")
        if "disk space" in issue_text or "gb free" in issue_text:
            actions.append("Free disk space before processing large archives.")
        if "ffmpeg not found" in warning_text:
            actions.append(tool_missing_hint("ffmpeg", include_recipe=False))
        if "ffmpeg version too old" in warning_text:
            actions.append("Upgrade ffmpeg to 4.4+ for expected validation support.")

        # Platform recipe once when any external tool is missing/outdated.
        if any(
            token in issue_text or token in warning_text
            for token in ("7-zip not found", "par2cmdline not found", "ffmpeg not found")
        ):
            actions.append(f"{platform_label()} package hint: {package_manager_install_hint()}")

        # Always include a deterministic final step
        actions.append("Re-run `unpackr-doctor` and confirm zero issues before live run.")
        return actions

    def check_python_version(self) -> None:
        """Check Python version."""
        print(f"{self._step(1)} Checking Python version...", end=" ")
        version = sys.version_info
        if (version.major, version.minor) >= (3, 12):
            print(f"{Fore.GREEN}✓ Python {version.major}.{version.minor}.{version.micro}{Style.RESET_ALL}")
            self.passed.append("Python version")
        else:
            print(f"{Fore.RED}✗ Python {version.major}.{version.minor} (need 3.12+){Style.RESET_ALL}")
            self.issues.append("Python version too old")

    def check_dependencies(self) -> None:
        """Check required Python packages."""
        print(f"{self._step(2)} Checking Python dependencies...", end=" ")
        required = ["tqdm", "psutil", "colorama"]
        missing: list[str] = []

        for package in required:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)

        if not missing:
            print(f"{Fore.GREEN}✓ All packages installed{Style.RESET_ALL}")
            self.passed.append("Python dependencies")
        else:
            print(f"{Fore.RED}✗ Missing: {', '.join(missing)}{Style.RESET_ALL}")
            self.issues.append(f"Missing packages: {', '.join(missing)}")
            print(f"  {Style.DIM}Fix: python -m pip install {' '.join(missing)}{Style.RESET_ALL}")

    def check_config_file(self) -> None:
        """Check config file exists and is valid."""
        print(f"{self._step(3)} Checking configuration file...", end=" ")
        config_path = self._config_file()

        if not config_path.exists():
            print(f"{Fore.RED}✗ Config file not found{Style.RESET_ALL}")
            self.issues.append("Missing config.json")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)

            if not isinstance(config, dict):
                print(f"{Fore.RED}✗ Config must contain a JSON object{Style.RESET_ALL}")
                self.issues.append("Config file must contain a JSON object")
                return

            # Check for required keys
            required_keys = ["tool_paths", "video_extensions", "removable_extensions"]
            missing_keys = [k for k in required_keys if k not in config]

            if missing_keys:
                print(f"{Fore.YELLOW}⚠ Missing keys: {', '.join(missing_keys)}{Style.RESET_ALL}")
                self.warnings.append(f"Config missing keys: {', '.join(missing_keys)}")
            else:
                print(f"{Fore.GREEN}✓ Valid configuration{Style.RESET_ALL}")
                self.passed.append("Configuration file")

        except json.JSONDecodeError as e:
            print(f"{Fore.RED}✗ Invalid JSON: {e}{Style.RESET_ALL}")
            self.issues.append("Config file has invalid JSON")
        except OSError as e:
            print(f"{Fore.RED}✗ Cannot read config: {e}{Style.RESET_ALL}")
            self.issues.append("Config file cannot be read")

    def check_tool(self, tool_name: str, commands: Sequence[str], critical: bool = True) -> tuple[bool, str | None]:
        """Check if external tool is available."""
        for cmd in commands:
            try:
                # Handle both string paths and command names
                if Path(cmd).exists():
                    # It's a file path
                    subprocess.run([cmd], capture_output=True, timeout=2)
                    return True, cmd
                else:
                    # It's a command name
                    test_cmd = [cmd] if tool_name != "ffmpeg" else [cmd, "-version"]
                    subprocess.run(test_cmd, capture_output=True, timeout=2)
                    return True, cmd
            except (OSError, ValueError, subprocess.TimeoutExpired):  # missing, not executable, malformed, or hung
                continue

        return False, None

    @staticmethod
    def _extract_version_tuple(text: str) -> Version | None:
        """Extract numeric version tuple from arbitrary tool output."""
        match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
        if not match:
            return None
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3)) if match.group(3) is not None else 0
        return (major, minor, patch)

    @staticmethod
    def _is_version_at_least(found: Version, minimum: Version) -> bool:
        """Compare versions using zero-padded tuple semantics."""
        max_len = max(len(found), len(minimum))
        found_norm = found + (0,) * (max_len - len(found))
        min_norm = minimum + (0,) * (max_len - len(minimum))
        return found_norm >= min_norm

    @staticmethod
    def _format_version(version: Version) -> str:
        """Format version tuple for display."""
        if len(version) >= 3 and version[2] == 0:
            return f"{version[0]}.{version[1]}"
        return ".".join(str(v) for v in version)

    def _get_tool_version(self, tool_name: str, tool_path: str) -> Version | None:
        """Best-effort runtime version check for external tools."""
        command = [tool_path]
        if tool_name == "ffmpeg":
            command.append("-version")
        elif tool_name == "par2":
            # par2cmdline 1.x prints only usage without -V.
            command.append("-V")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        combined = f"{result.stdout}\n{result.stderr}"
        return self._extract_version_tuple(combined)

    def _check_tool_min_version(self, tool_name: str, display_name: str, tool_path: str, critical: bool) -> None:
        """Enforce minimum supported version policy for a detected tool."""
        minimum = self.MIN_TOOL_VERSIONS.get(tool_name)
        if minimum is None:
            return

        found = self._get_tool_version(tool_name, tool_path)
        if found is None:
            self.warnings.append(f"{display_name} version could not be detected")
            return

        if self._is_version_at_least(found, minimum):
            # Fold the version into the tool's own entry so each check counts once.
            label = f"{display_name} {self._format_version(found)}"
            self.passed = [label if entry == display_name else entry for entry in self.passed]
            return

        found_text = self._format_version(found)
        min_text = self._format_version(minimum)
        if critical:
            self.issues.append(f"{display_name} version too old: {found_text} (need {min_text}+)")
        else:
            self.warnings.append(f"{display_name} version too old: {found_text} (need {min_text}+)")

    def check_external_tools(self) -> None:
        """Check external tools (7z, par2, ffmpeg)."""
        print(f"{self._step(4)} Checking external tools...")

        # Load config to get tool paths
        config_path = self._config_file()
        tool_paths: dict[str, object] = {}
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            if isinstance(config, dict):
                configured = cast(dict[str, object], config).get("tool_paths", {})
                if isinstance(configured, dict):
                    tool_paths = cast(dict[str, object], configured)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            pass

        # Check 7-Zip
        print(f"  {Style.DIM}7-Zip:{Style.RESET_ALL} ", end="")
        commands = merge_tool_candidates(tool_paths.get("7z"), "7z")

        found, path = self.check_tool("7z", commands, critical=True)
        if found and path:
            print(f"{Fore.GREEN}✓ Found at: {path}{Style.RESET_ALL}")
            self.passed.append("7-Zip")
            self._check_tool_min_version("7z", "7-Zip", path, critical=True)
        else:
            print(f"{Fore.RED}✗ Not found (CRITICAL){Style.RESET_ALL}")
            self.issues.append("7-Zip not found - required for archive extraction")
            print(f"    {Style.DIM}{tool_missing_hint('7z')}{Style.RESET_ALL}")

        # Check par2
        print(f"  {Style.DIM}par2cmdline:{Style.RESET_ALL} ", end="")
        commands = merge_tool_candidates(tool_paths.get("par2"), "par2")

        found, path = self.check_tool("par2", commands, critical=True)
        if found and path:
            print(f"{Fore.GREEN}✓ Found at: {path}{Style.RESET_ALL}")
            self.passed.append("par2cmdline")
            self._check_tool_min_version("par2", "par2cmdline", path, critical=False)
        else:
            print(
                f"{Fore.YELLOW}⚠ Not found (recommended - damaged or renamed volumes cannot be repaired; "
                f"archives still extract and 7-Zip checks every file's CRC){Style.RESET_ALL}"
            )
            self.warnings.append(
                "par2cmdline not found - damaged or renamed volumes cannot be repaired (archives still extract)"
            )
            print(f"    {Style.DIM}{tool_missing_hint('par2')}{Style.RESET_ALL}")

        # Check ffmpeg
        print(f"  {Style.DIM}ffmpeg:{Style.RESET_ALL} ", end="")
        commands = merge_tool_candidates(tool_paths.get("ffmpeg"), "ffmpeg")

        found, path = self.check_tool("ffmpeg", commands, critical=False)
        if found and path:
            print(f"{Fore.GREEN}✓ Found at: {path}{Style.RESET_ALL}")
            self.passed.append("ffmpeg")
            self._check_tool_min_version("ffmpeg", "ffmpeg", path, critical=False)
        else:
            print(f"{Fore.YELLOW}⚠ Not found (optional - video validation disabled){Style.RESET_ALL}")
            self.warnings.append("ffmpeg not found - video validation will be skipped")
            print(f"    {Style.DIM}{tool_missing_hint('ffmpeg')}{Style.RESET_ALL}")

    def check_write_permissions(self) -> None:
        """Check write permissions in current directory."""
        print(f"{self._step(5)} Checking write permissions...", end=" ")

        try:
            with tempfile.NamedTemporaryFile(prefix=".unpackr-doctor-", dir=Path.cwd()):
                pass
            print(f"{Fore.GREEN}✓ Can write to current directory{Style.RESET_ALL}")
            self.passed.append("Write permissions")
        except Exception as e:
            print(f"{Fore.RED}✗ Cannot write: {e}{Style.RESET_ALL}")
            self.issues.append("No write permissions in current directory")

    def check_filesystem_quirks(self) -> None:
        """Probe case sensitivity, symlink, and non-ASCII filename support."""
        print(f"{self._step(6)} Checking filesystem quirks...", end=" ")
        try:
            probe = probe_filesystem(Path.cwd())
            bits = [
                f"case_sensitive={probe.case_sensitive}",
                f"symlinks={probe.supports_symlinks}",
                f"non_ascii={probe.supports_non_ascii_names}",
            ]
            print(f"{Fore.GREEN}✓ {', '.join(bits)}{Style.RESET_ALL}")
            self.passed.append("Filesystem probe")
            if not probe.case_sensitive:
                self.warnings.append(
                    "Working directory is case-insensitive; names that differ only by case can collide"
                )
            if not probe.supports_symlinks:
                self.warnings.append(
                    "Symlink creation unavailable here; junction/symlink refusal still applies to existing links"
                )
            if not probe.supports_non_ascii_names:
                self.warnings.append("Filesystem rejected non-ASCII test names; prefer ASCII-safe filenames")
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Could not probe: {e}{Style.RESET_ALL}")
            self.warnings.append("Filesystem quirk probe failed")

    def check_disk_space(self) -> None:
        """Check available disk space."""
        print(f"{self._step(7)} Checking disk space...", end=" ")
        try:
            import shutil

            _total, _used, free = shutil.disk_usage(Path.cwd())
            free_gb = free // (2**30)

            if free_gb > 10:
                print(f"{Fore.GREEN}✓ {free_gb}GB available{Style.RESET_ALL}")
                self.passed.append("Disk space")
            elif free_gb > 5:
                print(f"{Fore.YELLOW}⚠ {free_gb}GB available (getting low){Style.RESET_ALL}")
                self.warnings.append(f"Only {free_gb}GB free")
            else:
                print(f"{Fore.RED}✗ {free_gb}GB available (very low!){Style.RESET_ALL}")
                self.issues.append(f"Only {free_gb}GB free - may not be enough")
        except Exception:
            print(f"{Fore.YELLOW}⚠ Could not check{Style.RESET_ALL}")

    def check_comments_file(self) -> None:
        """Check easter egg comments file."""
        print(f"{self._step(8)} Checking easter egg comments...", end=" ")
        config_dir = self._config_file().parent
        bundled_dir = Path(__file__).parent / "config_files"
        candidates = [
            config_dir / "comments.json",
            config_dir / "comments.sample.json",
            bundled_dir / "comments.sample.json",
        ]
        comments_path = next((path for path in candidates if path.is_file()), None)

        if comments_path is None:
            print(f"{Fore.YELLOW}⚠ Comments file not found (easter eggs disabled){Style.RESET_ALL}")
            self.warnings.append("No comments file - easter eggs disabled")
            return

        try:
            with open(comments_path) as f:
                data = json.load(f)

            comments = data.get("comments", [])
            if len(comments) > 0:
                print(f"{Fore.GREEN}✓ {len(comments)} comments loaded{Style.RESET_ALL}")
                self.passed.append("Easter egg comments")
            else:
                print(f"{Fore.YELLOW}⚠ Comments file empty{Style.RESET_ALL}")
                self.warnings.append("Empty comments file")
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Invalid JSON: {e}{Style.RESET_ALL}")
            self.warnings.append("Comments file has invalid JSON")

    def check_core_modules(self) -> None:
        """Check core Python modules are present."""
        print(f"{self._step(9)} Checking core modules...", end=" ")
        required_modules = [
            "core.config",
            "core.file_handler",
            "core.archive_processor",
            "core.video_processor",
            "utils.system_check",
            "utils.safety",
        ]

        missing: list[str] = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing.append(module)

        if not missing:
            print(f"{Fore.GREEN}✓ All core modules found{Style.RESET_ALL}")
            self.passed.append("Core modules")
        else:
            print(f"{Fore.RED}✗ Missing: {', '.join(missing)}{Style.RESET_ALL}")
            self.issues.append(f"Missing modules: {', '.join(missing)}")

    def check_log_directory(self) -> None:
        """Check log directory can be created."""
        print(f"{self._step(10)} Checking log directory...", end=" ")
        log_folder = "logs"
        try:
            with open(self._config_file(), encoding="utf-8") as config_file:
                payload = json.load(config_file)
            configured_log_folder: object = (
                cast(dict[str, object], payload).get("log_folder") if isinstance(payload, dict) else None
            )
            if (
                isinstance(configured_log_folder, str)
                and configured_log_folder.strip()
                and "\x00" not in configured_log_folder
            ):
                log_folder = configured_log_folder.strip()
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            pass

        from core.logger import resolve_log_dir

        log_dir = resolve_log_dir(log_folder).resolve()

        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            print(f"{Fore.GREEN}✓ Log directory ready: {log_dir}{Style.RESET_ALL}")
            self.passed.append("Log directory")
        except Exception as e:
            print(f"{Fore.RED}✗ Cannot create: {e}{Style.RESET_ALL}")
            self.issues.append("Cannot create log directory")

    def check_running_processes(self) -> None:
        """Check for conflicting helper processes on the current platform."""
        print(f"{self._step(11)} Checking for process conflicts...", end=" ")

        try:
            conflicts = detect_running_helpers(["7-Zip", "par2"])
            if conflicts:
                print(f"{Fore.YELLOW}⚠ Running on {platform_label()}: {', '.join(conflicts)}{Style.RESET_ALL}")
                self.warnings.append(f"Processes running: {', '.join(conflicts)} (will auto-kill)")
            else:
                print(f"{Fore.GREEN}✓ No conflicts ({platform_label()}){Style.RESET_ALL}")
                self.passed.append("Process check")
        except Exception:
            print(f"{Fore.YELLOW}⚠ Could not check{Style.RESET_ALL}")

    def check_quarantine(self) -> None:
        """Report quarantine size for --source and warn when it passes quarantine_warn_mb."""
        if self.source is None:
            return
        from core.config import Config
        from core.remover import list_runs

        config = Config(self.config_path) if self.config_path else Config()
        runs = list_runs(self.source)
        held_files = sum(r.quarantine_files for r in runs)
        held_mb = sum(r.quarantine_bytes for r in runs) / (1024 * 1024)
        limit_mb = config.quarantine_warn_mb
        print(f"{self._step(12)} Checking quarantine in {self.source}...")
        print(
            f"  mode: {config.delete_mode}, retention: {config.quarantine_retention_days} days, "
            f"held: {held_files} files, {held_mb:.1f} MB in {sum(1 for r in runs if r.quarantine_files)} run(s)"
        )
        if limit_mb and held_mb > limit_mb:
            self.warnings.append(
                f"Quarantine holds {held_mb:.0f} MB (over quarantine_warn_mb {limit_mb}); "
                "it is purged after quarantine_retention_days, or review with `unpackr runs`"
            )
        else:
            self.passed.append("Quarantine size")

    def print_summary(self) -> None:
        """Print diagnostic summary."""
        print(f"\n{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Summary{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

        steps = 11 + (1 if self.source is not None else 0)
        print(
            f"{Fore.GREEN}✓ Passed:{Style.RESET_ALL} {len(self.passed)} checks in {steps} steps "
            f"{Style.DIM}(the tools step checks 7-Zip, par2 and ffmpeg separately){Style.RESET_ALL}"
        )
        print(f"{Fore.YELLOW}⚠ Warnings:{Style.RESET_ALL} {len(self.warnings)}")
        print(f"{Fore.RED}✗ Issues:{Style.RESET_ALL} {len(self.issues)}")
        status = f"{Fore.GREEN}READY{Style.RESET_ALL}" if not self.issues else f"{Fore.RED}BLOCKED{Style.RESET_ALL}"
        print(f"Status: {status}")

        if self.warnings:
            print(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
            for w in self.warnings:
                print(f"  • {w}")

        if self.issues:
            print(f"\n{Fore.RED}Critical Issues:{Style.RESET_ALL}")
            for i in self.issues:
                print(f"  • {i}")
            print(f"\n{Fore.RED}Fix blocking issues before running Unpackr.{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}All checks passed! Ready to run Unpackr.{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")

        actions = self._build_recommended_actions()
        if actions:
            print(f"\n{Fore.CYAN}Recommended Next Steps:{Style.RESET_ALL}")
            for idx, action in enumerate(actions, 1):
                print(f"  {idx}. {action}")

        print()

    def run(self) -> int:
        """Run all diagnostic checks."""
        self.print_header()

        self.check_python_version()
        self.check_dependencies()
        self.check_config_file()
        self.check_external_tools()
        self.check_write_permissions()
        self.check_filesystem_quirks()
        self.check_disk_space()
        self.check_comments_file()
        self.check_core_modules()
        self.check_log_directory()
        self.check_running_processes()
        self.check_quarantine()

        self.print_summary()

        # Return exit code
        return 0 if not self.issues else 1

    def to_dict(self, exit_code: int | None = None) -> DoctorReport:
        """Return diagnostic results as structured data."""
        if exit_code is None:
            exit_code = 0 if not self.issues else 1

        return {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "exit_code": exit_code,
            "status": "ready" if not self.issues else "blocked",
            "counts": {
                "passed": len(self.passed),
                "warnings": len(self.warnings),
                "issues": len(self.issues),
            },
            "passed": self.passed,
            "warnings": self.warnings,
            "issues": self.issues,
            "recommended_actions": self._build_recommended_actions(),
        }


def main() -> None:
    """Main entry point for unpackr-doctor command."""
    parser = argparse.ArgumentParser(
        description="Diagnose unpackr runtime requirements and setup.",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON results")
    parser.add_argument("--config", type=existing_file_path, help="Path to an existing custom config file")
    parser.add_argument("--source", help="Also report the quarantine held in this source directory")
    args = parser.parse_args()

    source = Path(args.source).expanduser() if args.source else None
    config_path = Path(args.config) if args.config else None
    doctor = UnpackrDoctor(config_path) if source is None else UnpackrDoctor(config_path, source=source)
    if args.json:
        # Suppress human-readable output in JSON mode.
        with redirect_stdout(io.StringIO()):
            exit_code = doctor.run()
        print(json.dumps(doctor.to_dict(exit_code), indent=2))
        sys.exit(exit_code)

    exit_code = doctor.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
