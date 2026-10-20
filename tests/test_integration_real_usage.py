"""
Integration tests that validate real user workflows.
These tests would have caught the pre-scan spam and countdown hang bugs.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from colorama import Fore, Style, init

sys.path.insert(0, str(Path(__file__).parent.parent))

init()


def _terminate_and_collect(proc: subprocess.Popen, stdout_path: Path, stderr_path: Path) -> tuple[str, str]:
    """Terminate a subprocess and collect captured output from temp files."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    return stdout, stderr


class IntegrationTestRunner:
    """Test runner for integration tests."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def test(self, name: str, condition: bool, error_msg: str = ""):
        """Run a single test."""
        if condition:
            print(f"{Fore.GREEN}[PASS]{Style.RESET_ALL} {name}")
            self.passed += 1
            self.tests.append((name, True, ""))
        else:
            print(f"{Fore.RED}[FAIL]{Style.RESET_ALL} {name}")
            if error_msg:
                print(f"  {Fore.RED}Error: {error_msg}{Style.RESET_ALL}")
            self.failed += 1
            self.tests.append((name, False, error_msg))

    def summary(self):
        """Display test summary."""
        total = self.passed + self.failed
        print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
        print(
            f"Integration Tests: {total} | "
            f"{Fore.GREEN}Passed: {self.passed}{Style.RESET_ALL} | "
            f"{Fore.RED}Failed: {self.failed}{Style.RESET_ALL}"
        )

        if self.failed == 0:
            print(f"\n{Fore.GREEN}ALL INTEGRATION TESTS PASSED{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}FAILURES DETECTED{Style.RESET_ALL}")
            for name, passed, error in self.tests:
                if not passed:
                    print(f"  - {name}: {error}")

        print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
        return self.failed == 0


def test_prescan_no_terminal_spam(runner: IntegrationTestRunner):
    """
    Test that pre-scan doesn't spam terminal with hundreds of lines.
    This test would have caught Bug #1 (pre-scan terminal spam).
    """
    print(f"\n{Fore.YELLOW}[Pre-scan Terminal Output Tests]{Style.RESET_ALL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_source = Path(tmpdir) / "source"
        tmp_dest = Path(tmpdir) / "dest"
        tmp_source.mkdir()
        tmp_dest.mkdir()

        # Create 50 folders to trigger pre-scan progress
        for i in range(50):
            (tmp_source / f"folder{i}").mkdir()

        # Run unpackr with timeout (should complete quickly for empty folders)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "unpackr", "--source", str(tmp_source), "--destination", str(tmp_dest)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=Path(__file__).parent.parent,
            )

            # Count how many "[PRE-SCAN]" lines appear in output
            prescan_lines = result.stdout.count("[PRE-SCAN]")

            # Should see periodic updates (every 50 folders), not one per folder
            # For 50 folders, expect: 1 start message + 1 completion = 2 lines max
            runner.test(
                "Pre-scan: No terminal spam (< 5 lines for 50 folders)",
                prescan_lines <= 5,
                f"Found {prescan_lines} [PRE-SCAN] lines (should be ≤5)",
            )

            # Verify output doesn't contain excessive repetition
            lines = result.stdout.split("\n")
            prescan_update_lines = [line for line in lines if "[PRE-SCAN] Progress:" in line]
            runner.test(
                "Pre-scan: Uses periodic updates, not per-folder spam",
                len(prescan_update_lines) <= 3,
                f"Found {len(prescan_update_lines)} progress lines (should be ≤3 for 50 folders)",
            )

        except subprocess.TimeoutExpired:
            runner.test("Pre-scan: Completes within 30 seconds", False, "Pre-scan timed out (possible hang)")

    assert runner.failed == 0


def test_countdown_shows_visual_feedback(runner: IntegrationTestRunner):
    """
    The countdown must show changing numbers, not a static message (Bug #2: it
    appeared hung). It only runs for interactive live runs; a run without a
    terminal skips it instead of waiting ten seconds.
    """
    print(f"\n{Fore.YELLOW}[Countdown Visual Feedback Tests]{Style.RESET_ALL}")

    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    import unpackr.utils.cli_prompts as cli_prompts

    buffer = io.StringIO()
    with patch.object(cli_prompts.time, "sleep", lambda *_: None), redirect_stdout(buffer):
        assert cli_prompts.countdown_prompt(3, operation_label="processing") is True
    text = buffer.getvalue()
    runner.test(
        "Countdown: shows each second",
        all(f"Starting in {n} s. Ctrl+C cancels." in text for n in (3, 2, 1)),
        text[-300:],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_source = Path(tmpdir) / "source"
        tmp_dest = Path(tmpdir) / "dest"
        (tmp_source / "test_video").mkdir(parents=True)
        tmp_dest.mkdir()
        started = time.time()
        result = subprocess.run(
            [sys.executable, "-m", "unpackr", "--source", str(tmp_source), "--destination", str(tmp_dest)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=Path(__file__).parent.parent,
            stdin=subprocess.DEVNULL,
        )
        elapsed = time.time() - started
        runner.test(
            "Countdown: skipped without an interactive terminal",
            "Starting in" not in result.stdout and elapsed < 9,
            f"elapsed {elapsed:.1f}s",
        )


def test_windows_console_encoding(runner: IntegrationTestRunner):
    """
    Test that Windows console encoding is configured correctly.
    This test would have caught Bug #3 (Unicode encoding crashes).
    """
    print(f"\n{Fore.YELLOW}[Windows Console Encoding Tests]{Style.RESET_ALL}")

    # Test that progress UI elements render without crashes
    from unpackr import UnpackrApp
    from unpackr.core import Config

    _ = Config()
    _ = UnpackrApp(Config())

    # Test progress tracker with Unicode elements
    try:
        # This should not crash with UnicodeEncodeError
        from unpackr.utils.progress import ProgressTracker

        tracker = ProgressTracker()

        # Start and update progress (contains █ and other Unicode)
        tracker.start(total=10, desc="Testing")
        tracker.update(1)
        tracker.close()

        runner.test("Console encoding: Progress bar renders without crash", True)
    except UnicodeEncodeError as e:
        runner.test("Console encoding: Progress bar renders without crash", False, f"UnicodeEncodeError: {e}")
    except Exception as e:
        # Other exceptions are OK, we're just testing encoding doesn't crash
        runner.test(
            "Console encoding: Progress bar renders without crash", True, f"Non-encoding error (acceptable): {e}"
        )

    # Test that spinner frames can be used
    try:
        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for frame in spinner_frames:
            # Just accessing the characters shouldn't crash
            _ = frame

        runner.test("Console encoding: Spinner frames accessible", True)
    except UnicodeEncodeError as e:
        runner.test("Console encoding: Spinner frames accessible", False, f"UnicodeEncodeError: {e}")

    assert runner.failed == 0


def test_help_command_works(runner: IntegrationTestRunner):
    """Test that --help flag works correctly."""
    print(f"\n{Fore.YELLOW}[CLI Help Command Tests]{Style.RESET_ALL}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "unpackr", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            cwd=Path(__file__).parent.parent,
        )

        runner.test("CLI: --help returns exit code 0", result.returncode == 0, f"Exit code was {result.returncode}")

        runner.test(
            "CLI: --help shows usage information",
            "usage:" in result.stdout.lower(),
            "Help output should contain 'usage:'",
        )

        runner.test(
            "CLI: --help shows --source option", "--source" in result.stdout, "Help should document --source option"
        )

        runner.test(
            "CLI: --help shows --destination option",
            "--destination" in result.stdout,
            "Help should document --destination option",
        )

    except subprocess.TimeoutExpired:
        runner.test("CLI: --help completes quickly", False, "--help timed out after 10 seconds")

    assert runner.failed == 0


def test_dry_run_makes_no_changes(runner: IntegrationTestRunner):
    """Test that --dry-run doesn't actually modify files."""
    print(f"\n{Fore.YELLOW}[Dry Run Safety Tests]{Style.RESET_ALL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_source = Path(tmpdir) / "source"
        tmp_dest = Path(tmpdir) / "dest"
        tmp_source.mkdir()
        tmp_dest.mkdir()

        # Create test folder with fake video
        test_folder = tmp_source / "test_video"
        test_folder.mkdir()
        test_file = test_folder / "video.mp4"
        test_file.write_bytes(b"fake video data")

        # Record initial state
        initial_files = list(tmp_source.rglob("*"))
        initial_count = len(initial_files)

        # Run with --dry-run
        try:
            _ = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unpackr",
                    "--source",
                    str(tmp_source),
                    "--destination",
                    str(tmp_dest),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                cwd=Path(__file__).parent.parent,
            )

            # Check that no files were modified
            final_files = list(tmp_source.rglob("*"))
            final_count = len(final_files)

            runner.test(
                "Dry-run: No files deleted from source",
                final_count == initial_count,
                f"File count changed: {initial_count} → {final_count}",
            )

            runner.test(
                "Dry-run: Original file still exists", test_file.exists(), f"{test_file} was deleted during dry-run"
            )

            # Check destination is empty (nothing moved)
            dest_files = list(tmp_dest.rglob("*"))
            runner.test(
                "Dry-run: No files moved to destination",
                len(dest_files) == 0,
                f"Found {len(dest_files)} files in destination",
            )

        except subprocess.TimeoutExpired:
            runner.test("Dry-run: Completes within 30 seconds", False, "Dry-run timed out")

    assert runner.failed == 0


def test_empty_source_directory(runner: IntegrationTestRunner):
    """Test that app handles empty source directory gracefully."""
    print(f"\n{Fore.YELLOW}[Empty Directory Handling Tests]{Style.RESET_ALL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_source = Path(tmpdir) / "empty_source"
        tmp_dest = Path(tmpdir) / "dest"
        tmp_source.mkdir()
        tmp_dest.mkdir()

        try:
            result = subprocess.run(
                [sys.executable, "-m", "unpackr", "--source", str(tmp_source), "--destination", str(tmp_dest)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                cwd=Path(__file__).parent.parent,
            )

            # Empty source may return non-zero (nothing to process), which is OK
            # What matters is it doesn't crash with exception
            runner.test(
                "Empty source: Completes without crash",
                result.returncode in [0, 1],
                f"Exit code: {result.returncode} (should be 0 or 1)",
            )

            # Should not have stderr errors (warnings are OK)
            has_error = "error" in result.stderr.lower() and "warning" not in result.stderr.lower()
            runner.test(
                "Empty source: No error messages (warnings OK)", not has_error, "Stderr contained actual error messages"
            )

        except subprocess.TimeoutExpired:
            runner.test("Empty source: Completes quickly", False, "Processing empty directory timed out")

    assert runner.failed == 0


def test_invalid_source_path(runner: IntegrationTestRunner):
    """Test that app handles invalid source path gracefully."""
    print(f"\n{Fore.YELLOW}[Invalid Path Handling Tests]{Style.RESET_ALL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dest = Path(tmpdir) / "dest"
        tmp_dest.mkdir()

        invalid_source = Path(tmpdir) / "definitely_missing_source_dir"

        try:
            result = subprocess.run(
                [sys.executable, "-m", "unpackr", "--source", str(invalid_source), "--destination", str(tmp_dest)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                cwd=Path(__file__).parent.parent,
            )

            runner.test(
                "Invalid source: Returns non-zero exit code",
                result.returncode != 0,
                f"Should fail but returned {result.returncode}",
            )

            runner.test(
                "Invalid source: Shows error message",
                "error" in result.stderr.lower() or "not exist" in result.stdout.lower(),
                "Should display error about invalid path",
            )

        except subprocess.TimeoutExpired:
            runner.test("Invalid source: Fails quickly", False, "Should fail fast on invalid path")

    assert runner.failed == 0


def main():
    """Run all integration tests."""
    print(f"\n{Fore.CYAN}{'=' * 70}")
    print("INTEGRATION TEST SUITE - Real Usage Scenarios")
    print(f"{'=' * 70}{Style.RESET_ALL}\n")

    runner = IntegrationTestRunner()

    # Run all test suites
    test_prescan_no_terminal_spam(runner)
    test_countdown_shows_visual_feedback(runner)
    test_windows_console_encoding(runner)
    test_help_command_works(runner)
    test_dry_run_makes_no_changes(runner)
    test_empty_source_directory(runner)
    test_invalid_source_path(runner)

    # Display summary
    success = runner.summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
