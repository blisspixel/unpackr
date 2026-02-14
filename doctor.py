"""
Unpackr Doctor - Diagnostic tool to check system health and configuration.
Run this to verify everything is set up correctly before processing.
"""

import sys
import json
import argparse
import io
import subprocess
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from colorama import init, Fore, Style

init(autoreset=True)

class UnpackrDoctor:
    """Diagnostic tool for Unpackr setup."""

    def __init__(self):
        self.issues = []
        self.warnings = []
        self.passed = []

    def print_header(self):
        """Print diagnostic header."""
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Unpackr Doctor - System Diagnostic{Style.RESET_ALL}")
        print(f"{Style.DIM}Checks runtime, tools, config, and safety prerequisites{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

    def _build_recommended_actions(self):
        """Generate actionable remediation steps from current findings."""
        actions = []
        issue_text = " ".join(self.issues).lower()
        warning_text = " ".join(self.warnings).lower()

        if "python version too old" in issue_text:
            actions.append("Install Python 3.11+ and run doctor again.")
        if "7-zip not found" in issue_text:
            actions.append("Install 7-Zip and ensure `7z` is on PATH (or set tool path in config).")
        if "par2cmdline not found" in issue_text:
            actions.append("Install par2cmdline and ensure `par2` is on PATH (or set tool path in config).")
        if "missing packages:" in issue_text:
            actions.append("Install required Python packages with `pip install -e .`.")
        if "config" in issue_text and "json" in issue_text:
            actions.append("Fix JSON syntax in `config_files/config.json`.")
        if "write permissions" in issue_text:
            actions.append("Run from a writable directory or adjust folder permissions.")
        if "disk space" in issue_text or "gb free" in issue_text:
            actions.append("Free disk space before processing large archives.")
        if "ffmpeg not found" in warning_text:
            actions.append("Install ffmpeg if you want full video health validation.")

        # Always include a deterministic final step
        actions.append("Re-run `unpackr-doctor` and confirm zero issues before live run.")
        return actions

    def check_python_version(self):
        """Check Python version."""
        print(f"{Fore.YELLOW}[1/10]{Style.RESET_ALL} Checking Python version...", end=" ")
        version = sys.version_info
        if version.major == 3 and version.minor >= 11:
            print(f"{Fore.GREEN}✓ Python {version.major}.{version.minor}.{version.micro}{Style.RESET_ALL}")
            self.passed.append("Python version")
        else:
            print(f"{Fore.RED}✗ Python {version.major}.{version.minor} (need 3.11+){Style.RESET_ALL}")
            self.issues.append("Python version too old")

    def check_dependencies(self):
        """Check required Python packages."""
        print(f"{Fore.YELLOW}[2/10]{Style.RESET_ALL} Checking Python dependencies...", end=" ")
        required = ['tqdm', 'psutil', 'colorama']
        missing = []

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
            print(f"  {Style.DIM}Fix: pip install {' '.join(missing)}{Style.RESET_ALL}")

    def check_config_file(self):
        """Check config file exists and is valid."""
        print(f"{Fore.YELLOW}[3/10]{Style.RESET_ALL} Checking configuration file...", end=" ")
        config_path = Path(__file__).parent / 'config_files' / 'config.json'

        if not config_path.exists():
            print(f"{Fore.RED}✗ Config file not found{Style.RESET_ALL}")
            self.issues.append("Missing config.json")
            return

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Check for required keys
            required_keys = ['tool_paths', 'video_extensions', 'removable_extensions']
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

    def check_tool(self, tool_name, commands, critical=True):
        """Check if external tool is available."""
        for cmd in commands:
            try:
                # Handle both string paths and command names
                if Path(cmd).exists():
                    # It's a file path
                    subprocess.run(
                        [cmd],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=2
                    )
                    return True, cmd
                else:
                    # It's a command name
                    test_cmd = [cmd] if tool_name != 'ffmpeg' else [cmd, '-version']
                    subprocess.run(
                        test_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=2
                    )
                    return True, cmd
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                continue

        return False, None

    def check_external_tools(self):
        """Check external tools (7z, par2, ffmpeg)."""
        print(f"{Fore.YELLOW}[4/10]{Style.RESET_ALL} Checking external tools...")

        # Load config to get tool paths
        config_path = Path(__file__).parent / 'config_files' / 'config.json'
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            tool_paths = config.get('tool_paths', {})
        except (OSError, json.JSONDecodeError):
            tool_paths = {}

        # Check 7-Zip
        print(f"  {Style.DIM}7-Zip:{Style.RESET_ALL} ", end="")
        commands = tool_paths.get('7z', [])
        if isinstance(commands, str):
            commands = [commands]
        commands.extend(['7z', 'C:\\Program Files\\7-Zip\\7z.exe'])

        found, path = self.check_tool('7z', commands, critical=True)
        if found:
            print(f"{Fore.GREEN}✓ Found at: {path}{Style.RESET_ALL}")
            self.passed.append("7-Zip")
        else:
            print(f"{Fore.RED}✗ Not found (CRITICAL){Style.RESET_ALL}")
            self.issues.append("7-Zip not found - required for RAR extraction")
            print(f"    {Style.DIM}Download: https://www.7-zip.org/{Style.RESET_ALL}")

        # Check par2
        print(f"  {Style.DIM}par2cmdline:{Style.RESET_ALL} ", end="")
        commands = tool_paths.get('par2', [])
        if isinstance(commands, str):
            commands = [commands]
        commands.extend(['par2', 'bin\\par2.exe'])

        found, path = self.check_tool('par2', commands, critical=True)
        if found:
            print(f"{Fore.GREEN}✓ Found at: {path}{Style.RESET_ALL}")
            self.passed.append("par2cmdline")
        else:
            print(f"{Fore.RED}✗ Not found (CRITICAL){Style.RESET_ALL}")
            self.issues.append("par2cmdline not found - required for PAR2 repair")
            print(f"    {Style.DIM}Included in bin/ or download from GitHub{Style.RESET_ALL}")

        # Check ffmpeg
        print(f"  {Style.DIM}ffmpeg:{Style.RESET_ALL} ", end="")
        commands = tool_paths.get('ffmpeg', [])
        if isinstance(commands, str):
            commands = [commands]
        commands.extend(['ffmpeg'])

        found, path = self.check_tool('ffmpeg', commands, critical=False)
        if found:
            print(f"{Fore.GREEN}✓ Found at: {path}{Style.RESET_ALL}")
            self.passed.append("ffmpeg")
        else:
            print(f"{Fore.YELLOW}⚠ Not found (optional - video validation disabled){Style.RESET_ALL}")
            self.warnings.append("ffmpeg not found - video validation will be skipped")

    def check_write_permissions(self):
        """Check write permissions in current directory."""
        print(f"{Fore.YELLOW}[5/10]{Style.RESET_ALL} Checking write permissions...", end=" ")
        test_file = Path(__file__).parent / '.doctor_test'

        try:
            test_file.write_text('test')
            test_file.unlink()
            print(f"{Fore.GREEN}✓ Can write to current directory{Style.RESET_ALL}")
            self.passed.append("Write permissions")
        except Exception as e:
            print(f"{Fore.RED}✗ Cannot write: {e}{Style.RESET_ALL}")
            self.issues.append("No write permissions in current directory")

    def check_disk_space(self):
        """Check available disk space."""
        print(f"{Fore.YELLOW}[6/10]{Style.RESET_ALL} Checking disk space...", end=" ")
        try:
            import shutil
            total, used, free = shutil.disk_usage(Path.cwd())
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

    def check_comments_file(self):
        """Check easter egg comments file."""
        print(f"{Fore.YELLOW}[7/10]{Style.RESET_ALL} Checking easter egg comments...", end=" ")
        comments_path = Path(__file__).parent / 'config_files' / 'comments.json'

        if not comments_path.exists():
            print(f"{Fore.YELLOW}⚠ Comments file not found (easter eggs disabled){Style.RESET_ALL}")
            self.warnings.append("No comments.json - easter eggs disabled")
            return

        try:
            with open(comments_path, 'r') as f:
                data = json.load(f)

            comments = data.get('comments', [])
            if len(comments) > 0:
                print(f"{Fore.GREEN}✓ {len(comments)} comments loaded{Style.RESET_ALL}")
                self.passed.append("Easter egg comments")
            else:
                print(f"{Fore.YELLOW}⚠ Comments file empty{Style.RESET_ALL}")
                self.warnings.append("Empty comments file")
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Invalid JSON: {e}{Style.RESET_ALL}")
            self.warnings.append("Comments file has invalid JSON")

    def check_core_modules(self):
        """Check core Python modules are present."""
        print(f"{Fore.YELLOW}[8/10]{Style.RESET_ALL} Checking core modules...", end=" ")
        required_modules = [
            'core.config',
            'core.file_handler',
            'core.archive_processor',
            'core.video_processor',
            'utils.system_check',
            'utils.safety'
        ]

        missing = []
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

    def check_log_directory(self):
        """Check log directory can be created."""
        print(f"{Fore.YELLOW}[9/10]{Style.RESET_ALL} Checking log directory...", end=" ")
        log_dir = Path(__file__).parent / 'logs'

        try:
            log_dir.mkdir(exist_ok=True)
            print(f"{Fore.GREEN}✓ Log directory ready{Style.RESET_ALL}")
            self.passed.append("Log directory")
        except Exception as e:
            print(f"{Fore.RED}✗ Cannot create: {e}{Style.RESET_ALL}")
            self.issues.append("Cannot create log directory")

    def check_running_processes(self):
        """Check for conflicting processes."""
        print(f"{Fore.YELLOW}[10/10]{Style.RESET_ALL} Checking for process conflicts...", end=" ")

        try:
            if sys.platform == 'win32':
                result = subprocess.run(
                    ['tasklist', '/FO', 'CSV', '/NH'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                output = result.stdout.lower()

                conflicts = []
                if '7z.exe' in output or '7zfm.exe' in output:
                    conflicts.append('7-Zip')
                if 'par2.exe' in output:
                    conflicts.append('par2')

                if conflicts:
                    print(f"{Fore.YELLOW}⚠ Running: {', '.join(conflicts)}{Style.RESET_ALL}")
                    self.warnings.append(f"Processes running: {', '.join(conflicts)} (will auto-kill)")
                else:
                    print(f"{Fore.GREEN}✓ No conflicts{Style.RESET_ALL}")
                    self.passed.append("Process check")
            else:
                print(f"{Fore.GREEN}✓ Not Windows (skipped){Style.RESET_ALL}")
                self.passed.append("Process check")

        except Exception:
            print(f"{Fore.YELLOW}⚠ Could not check{Style.RESET_ALL}")

    def print_summary(self):
        """Print diagnostic summary."""
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Summary{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        print(f"{Fore.GREEN}✓ Passed:{Style.RESET_ALL} {len(self.passed)}")
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
            print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}All checks passed! Ready to run Unpackr.{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")

        actions = self._build_recommended_actions()
        if actions:
            print(f"\n{Fore.CYAN}Recommended Next Steps:{Style.RESET_ALL}")
            for idx, action in enumerate(actions, 1):
                print(f"  {idx}. {action}")

        print()

    def run(self):
        """Run all diagnostic checks."""
        self.print_header()

        self.check_python_version()
        self.check_dependencies()
        self.check_config_file()
        self.check_external_tools()
        self.check_write_permissions()
        self.check_disk_space()
        self.check_comments_file()
        self.check_core_modules()
        self.check_log_directory()
        self.check_running_processes()

        self.print_summary()

        # Return exit code
        return 0 if not self.issues else 1

    def to_dict(self, exit_code: int = None):
        """Return diagnostic results as structured data."""
        if exit_code is None:
            exit_code = 0 if not self.issues else 1

        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
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


def main():
    """Main entry point for unpackr-doctor command."""
    parser = argparse.ArgumentParser(
        description="Diagnose unpackr runtime requirements and setup.",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON results")
    args = parser.parse_args()

    doctor = UnpackrDoctor()
    if args.json:
        # Suppress human-readable output in JSON mode.
        with redirect_stdout(io.StringIO()):
            exit_code = doctor.run()
        print(json.dumps(doctor.to_dict(exit_code), indent=2))
        sys.exit(exit_code)

    exit_code = doctor.run()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
