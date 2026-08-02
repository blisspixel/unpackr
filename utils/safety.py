"""
Safety mechanisms for Unpackr.
Prevents infinite loops, deadlocks, and runaway processes.
"""

import logging
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, Protocol


class TimeoutException(Exception):
    """Exception raised when operation exceeds timeout."""

    pass


class ProcessTracker(Protocol):
    """Minimal protocol for cancellation-aware subprocess tracking."""

    active_process: Any | None


class SafetyLimits:
    """Centralized safety configuration."""

    # Process timeouts (seconds) - Defaults for small files
    RAR_EXTRACTION_TIMEOUT = 300  # 5 minutes per RAR (default, will be calculated dynamically)
    PAR2_REPAIR_TIMEOUT = 600  # 10 minutes per PAR2 (default, will be calculated dynamically)
    VIDEO_CHECK_TIMEOUT = 180  # 3 minutes per video (increased for large 4K files)
    FFMPEG_TIMEOUT = 45  # 45 seconds for ffmpeg

    # PERFORMANCE: Dynamic timeout calculation parameters
    # Assumes ~10MB/s extraction speed (conservative for HDDs)
    RAR_EXTRACTION_SPEED_MB_PER_SEC = 10
    PAR2_REPAIR_SPEED_MB_PER_SEC = 5  # PAR2 is slower due to checksums

    # Retry limits (defaults; runtime uses Config values when available)
    MAX_FILE_DELETE_RETRIES = 5
    MAX_FILE_RELEASE_WAIT = 10
    MAX_FOLDER_DELETE_RETRIES = 2

    # Process wait limits
    FILE_RELEASE_CHECK_DELAY = 1  # seconds
    DELETE_RETRY_DELAY = 1  # seconds
    FOLDER_CLEANUP_DELAY = 5  # seconds

    # Total operation limits (defaults; runtime uses Config values when available)
    MAX_VIDEOS_PER_FOLDER = 500  # Safety limit
    MAX_SUBFOLDERS_DEPTH = 20  # Prevent infinite recursion
    MAX_TOTAL_PROCESSING_TIME = 3600 * 48  # 48 hours total
    MAX_SUBPROCESS_CAPTURE_BYTES = 64 * 1024  # Bound stdout/stderr returned from temp files

    @staticmethod
    def calculate_rar_timeout(file_size_bytes: int) -> int:
        """
        Calculate dynamic timeout for RAR extraction based on file size.

        PERFORMANCE: Handles large archives (50GB+) that would timeout with fixed 5min limit.
        Uses conservative speed assumption (10MB/s) to allow for slower drives.

        Args:
            file_size_bytes: Size of archive file in bytes

        Returns:
            Timeout in seconds (minimum 300 = 5 minutes)
        """
        if file_size_bytes <= 0:
            return SafetyLimits.RAR_EXTRACTION_TIMEOUT

        size_mb = file_size_bytes / (1024 * 1024)
        # Calculate expected time + 50% buffer
        expected_seconds = size_mb / SafetyLimits.RAR_EXTRACTION_SPEED_MB_PER_SEC
        timeout = int(expected_seconds * 1.5)

        # Minimum 5 minutes, maximum 2 hours
        return max(300, min(timeout, 7200))

    @staticmethod
    def calculate_par2_timeout(total_par2_size_bytes: int) -> int:
        """
        Calculate dynamic timeout for PAR2 repair based on total PAR2 files size.

        PERFORMANCE: Handles large repair operations that would timeout with fixed 10min limit.
        PAR2 is slower than extraction due to checksum verification.

        Args:
            total_par2_size_bytes: Combined size of all PAR2 files in bytes

        Returns:
            Timeout in seconds (minimum 600 = 10 minutes)
        """
        if total_par2_size_bytes <= 0:
            return SafetyLimits.PAR2_REPAIR_TIMEOUT

        size_mb = total_par2_size_bytes / (1024 * 1024)
        # Calculate expected time + 100% buffer (PAR2 is unpredictable)
        expected_seconds = size_mb / SafetyLimits.PAR2_REPAIR_SPEED_MB_PER_SEC
        timeout = int(expected_seconds * 2.0)

        # Minimum 10 minutes, maximum 3 hours
        return max(600, min(timeout, 10800))


class TimeoutGuard:
    """Context manager for timeout protection."""

    def __init__(self, timeout: int, operation: str = "Operation"):
        """
        Initialize timeout guard.

        Args:
            timeout: Timeout in seconds
            operation: Description of operation for logging
        """
        self.timeout = timeout
        self.operation = operation
        self.timer: threading.Timer | None = None
        self.timed_out = False

    def _timeout_handler(self):
        """Handle timeout event."""
        self.timed_out = True
        logging.error(f"{self.operation} exceeded timeout of {self.timeout} seconds")

    def __enter__(self):
        """Start timeout timer."""
        self.timer = threading.Timer(self.timeout, self._timeout_handler)
        self.timer.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cancel timeout timer."""
        if self.timer:
            self.timer.cancel()

        if self.timed_out:
            raise TimeoutException(f"{self.operation} timed out after {self.timeout} seconds")

        return False


def timeout_decorator(seconds: int, operation: str = "Operation") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to add timeout to functions.

    Args:
        seconds: Timeout in seconds
        operation: Description for logging
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with TimeoutGuard(seconds, operation):
                return func(*args, **kwargs)

        return wrapper

    return decorator


class SubprocessSafety:
    """Safe subprocess execution with timeout and monitoring."""

    @staticmethod
    def _read_bounded_text(path: Path, max_bytes: int | None = None) -> str:
        """
        Read a bounded sample from subprocess output.

        Large archive tools can produce one line per file. Keep enough context for
        diagnostics without loading attacker-controlled output fully into memory.
        """
        if max_bytes is None:
            max_bytes = SafetyLimits.MAX_SUBPROCESS_CAPTURE_BYTES

        size = path.stat().st_size
        if size <= max_bytes:
            return path.read_text(encoding="utf-8", errors="replace")

        head_bytes = max_bytes // 2
        tail_bytes = max_bytes - head_bytes
        with path.open("rb") as output_file:
            head = output_file.read(head_bytes)
            output_file.seek(max(0, size - tail_bytes))
            tail = output_file.read(tail_bytes)

        omitted = max(0, size - len(head) - len(tail))
        head_text = head.decode("utf-8", errors="replace")
        tail_text = tail.decode("utf-8", errors="replace")
        return f"{head_text}\n... [truncated {omitted} bytes of subprocess output] ...\n{tail_text}"

    @staticmethod
    def run_with_timeout(
        cmd: list[str],
        timeout: int,
        cwd: Optional[Path] = None,
        operation: str = "Subprocess",
        expected_codes: Optional[list[int]] = None,
        use_temp_files: bool = False,
        process_tracker: Optional[ProcessTracker] = None,
    ) -> tuple[bool, str, str, int]:
        """
        Run subprocess with guaranteed timeout and buffer overflow protection.

        Args:
            cmd: Command and arguments
            timeout: Timeout in seconds
            cwd: Working directory
            operation: Operation description for logging
            expected_codes: List of expected exit codes (suppresses warnings for these codes)
            use_temp_files: Use temp files for stdout/stderr instead of PIPE (prevents buffer overflow on large outputs)
            process_tracker: Object with 'active_process' attribute to track subprocess for cancellation

        Returns:
            Tuple of (success: bool, stdout: str, stderr: str, returncode: int)
        """
        try:
            logging.debug(f"[SAFETY] Starting {operation} with {timeout}s timeout")

            if use_temp_files:
                # SECURITY FIX: Use temp files for large operations to prevent buffer overflow/deadlock
                # Large archive listings (multi-GB) can exceed PIPE buffer (64KB on Windows, 1MB on Linux)
                with (
                    tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as stdout_file,
                    tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as stderr_file,
                ):
                    stdout_path = Path(stdout_file.name)
                    stderr_path = Path(stderr_file.name)

                    try:
                        process = subprocess.Popen(
                            cmd,
                            stdout=stdout_file,
                            stderr=stderr_file,
                            cwd=cwd,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                        )

                        # Track process for cancellation
                        if process_tracker:
                            process_tracker.active_process = process

                        try:
                            process.wait(timeout=timeout)
                            success = process.returncode == 0

                            # Read bounded output samples from temp files.
                            stdout = SubprocessSafety._read_bounded_text(stdout_path)
                            stderr = SubprocessSafety._read_bounded_text(stderr_path)

                            # Only log warning if code is unexpected
                            if not success and (expected_codes is None or process.returncode not in expected_codes):
                                logging.warning(f"[SAFETY] {operation} failed with code {process.returncode}")

                            return success, stdout, stderr, process.returncode

                        except subprocess.TimeoutExpired:
                            logging.warning(f"[SAFETY] {operation} TIMEOUT - killing process")
                            process.kill()
                            with suppress(subprocess.TimeoutExpired, OSError):
                                process.wait(timeout=5)

                            # Read partial output
                            try:
                                stdout = SubprocessSafety._read_bounded_text(stdout_path)
                                stderr = SubprocessSafety._read_bounded_text(stderr_path)
                            except OSError:
                                stdout, stderr = "", "Process killed after timeout"
                            return False, stdout, stderr, -1

                        finally:
                            # Clear process tracker
                            if process_tracker:
                                process_tracker.active_process = None

                    finally:
                        # Cleanup temp files
                        try:
                            stdout_path.unlink(missing_ok=True)
                            stderr_path.unlink(missing_ok=True)
                        except OSError:
                            pass

            else:
                # Standard PIPE mode for small/normal operations
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=cwd,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                # Track process for cancellation
                if process_tracker:
                    process_tracker.active_process = process

                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    success = process.returncode == 0

                    # Only log warning if code is unexpected
                    if not success and (expected_codes is None or process.returncode not in expected_codes):
                        logging.warning(f"[SAFETY] {operation} failed with code {process.returncode}")

                    return success, stdout, stderr, process.returncode

                except subprocess.TimeoutExpired:
                    logging.warning(f"[SAFETY] {operation} TIMEOUT - killing process")
                    process.kill()
                    try:
                        stdout, stderr = process.communicate(timeout=5)
                    except (subprocess.TimeoutExpired, OSError):
                        stdout, stderr = "", "Process killed after timeout"
                    return False, stdout, stderr, -1

                finally:
                    # Clear process tracker
                    if process_tracker:
                        process_tracker.active_process = None

        except Exception as e:
            logging.error(f"[SAFETY] {operation} exception: {e}")
            return False, "", str(e), -1

    @staticmethod
    def run_with_line_handler(
        cmd: list[str],
        timeout: int,
        line_handler: Callable[[str], bool],
        cwd: Optional[Path] = None,
        operation: str = "Subprocess",
        expected_codes: Optional[list[int]] = None,
        process_tracker: Optional[ProcessTracker] = None,
    ) -> tuple[bool, str, int]:
        """
        Run subprocess and stream the full stdout line-by-line through ``line_handler``.

        SECURITY: Unlike ``run_with_timeout(use_temp_files=True)``, this method does
        NOT truncate stdout. Security-sensitive consumers (e.g. archive path
        validation) must see every line, so we iterate the temp file directly
        rather than returning a bounded head/tail sample.

        Args:
            cmd: Command and arguments.
            timeout: Timeout in seconds.
            line_handler: Callable invoked for each stdout line (without trailing
                newline). Return ``False`` to stop iteration early; the call still
                returns ``success=True`` when the process itself succeeded.
            cwd: Working directory.
            operation: Operation description for logging.
            expected_codes: Exit codes that should not log a warning.
            process_tracker: Object with ``active_process`` attribute for cancellation.

        Returns:
            Tuple ``(success, stderr_sample, returncode)``. ``stderr_sample`` is a
            bounded sample suitable for diagnostics only.
        """
        try:
            logging.debug(f"[SAFETY] Starting streaming {operation} with {timeout}s timeout")

            with (
                tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as stdout_file,
                tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as stderr_file,
            ):
                stdout_path = Path(stdout_file.name)
                stderr_path = Path(stderr_file.name)

                try:
                    process = subprocess.Popen(
                        cmd,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        cwd=cwd,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )

                    if process_tracker:
                        process_tracker.active_process = process

                    try:
                        try:
                            process.wait(timeout=timeout)
                            timed_out = False
                        except subprocess.TimeoutExpired:
                            logging.warning(f"[SAFETY] {operation} TIMEOUT - killing process")
                            process.kill()
                            with suppress(subprocess.TimeoutExpired, OSError):
                                process.wait(timeout=5)
                            timed_out = True

                        returncode = -1 if timed_out else process.returncode
                        success = (not timed_out) and returncode == 0

                        if (
                            not success
                            and not timed_out
                            and (expected_codes is None or returncode not in expected_codes)
                        ):
                            logging.warning(f"[SAFETY] {operation} failed with code {returncode}")

                        # Stream the full stdout file (no truncation) through the handler.
                        try:
                            with stdout_path.open("r", encoding="utf-8", errors="replace") as stdout_stream:
                                for raw_line in stdout_stream:
                                    if line_handler(raw_line.rstrip("\n")) is False:
                                        break
                        except OSError as read_err:
                            logging.warning(f"[SAFETY] {operation} could not read stdout: {read_err}")
                            return False, "", -1

                        try:
                            stderr_sample = SubprocessSafety._read_bounded_text(stderr_path)
                        except OSError:
                            stderr_sample = ""

                        if timed_out:
                            return False, stderr_sample, -1
                        return success, stderr_sample, returncode

                    finally:
                        if process_tracker:
                            process_tracker.active_process = None

                finally:
                    try:
                        stdout_path.unlink(missing_ok=True)
                        stderr_path.unlink(missing_ok=True)
                    except OSError:
                        pass

        except Exception as e:
            logging.error(f"[SAFETY] {operation} exception: {e}")
            return False, str(e), -1


class LoopSafety:
    """Prevent infinite loops with iteration tracking."""

    def __init__(self, max_iterations: int, loop_name: str = "Loop"):
        """
        Initialize loop safety tracker.

        Args:
            max_iterations: Maximum allowed iterations
            loop_name: Name for logging
        """
        self.max_iterations = max_iterations
        self.loop_name = loop_name
        self.iteration_count = 0
        self.start_time = time.time()

    def tick(self) -> bool:
        """
        Increment iteration counter and check limit.

        Returns:
            True if should continue, False if limit exceeded
        """
        self.iteration_count += 1

        if self.iteration_count > self.max_iterations:
            elapsed = time.time() - self.start_time
            logging.error(
                f"[SAFETY] {self.loop_name} exceeded {self.max_iterations} iterations in {elapsed:.1f}s - BREAKING"
            )
            return False

        if self.iteration_count % 10 == 0:
            elapsed = time.time() - self.start_time
            logging.debug(f"[SAFETY] {self.loop_name} iteration {self.iteration_count} ({elapsed:.1f}s elapsed)")

        return True

    def reset(self):
        """Reset iteration counter."""
        self.iteration_count = 0
        self.start_time = time.time()


class RecursionSafety:
    """Prevent stack overflow from deep recursion."""

    def __init__(self, max_depth: int, operation: str = "Recursion"):
        """
        Initialize recursion depth tracker.

        Args:
            max_depth: Maximum recursion depth
            operation: Operation name for logging
        """
        self.max_depth = max_depth
        self.operation = operation
        self.current_depth = 0

    def enter(self) -> bool:
        """
        Enter recursion level.

        Returns:
            True if safe to continue, False if depth exceeded
        """
        self.current_depth += 1

        if self.current_depth > self.max_depth:
            logging.error(f"[SAFETY] {self.operation} exceeded max depth {self.max_depth}")
            return False

        return True

    def exit(self):
        """Exit recursion level."""
        self.current_depth = max(0, self.current_depth - 1)


class OperationTimer:
    """Track total operation time with hard limit."""

    def __init__(self, max_time: int, operation: str = "Operation"):
        """
        Initialize operation timer.

        Args:
            max_time: Maximum time in seconds
            operation: Operation name
        """
        self.max_time = max_time
        self.operation = operation
        self.start_time = time.time()

    def check(self) -> bool:
        """
        Check if operation has exceeded time limit.

        Returns:
            True if time remaining, False if exceeded
        """
        elapsed = time.time() - self.start_time

        if elapsed > self.max_time:
            logging.error(
                f"[SAFETY] {self.operation} exceeded total time limit ({elapsed:.1f}s / {self.max_time}s) - STOPPING"
            )
            return False

        return True

    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time


class StuckDetector:
    """Detect when process appears stuck with no progress."""

    def __init__(self, timeout: int, check_interval: int = 10):
        """
        Initialize stuck detector.

        Args:
            timeout: Seconds without progress before declaring stuck
            check_interval: How often to check (seconds)
        """
        self.timeout = timeout
        self.check_interval = check_interval
        self.last_progress = time.time()
        self.last_check = time.time()

    def mark_progress(self):
        """Mark that progress has been made."""
        self.last_progress = time.time()

    def check(self) -> bool:
        """
        Check if process appears stuck.

        Returns:
            True if healthy, False if stuck
        """
        now = time.time()

        # Only check periodically
        if now - self.last_check < self.check_interval:
            return True

        self.last_check = now

        time_since_progress = now - self.last_progress

        if time_since_progress > self.timeout:
            logging.error(
                f"[SAFETY] Process appears STUCK - no progress for "
                f"{time_since_progress:.1f}s (timeout: {self.timeout}s)"
            )
            return False

        return True


# Global instance for total runtime tracking
GLOBAL_RUNTIME_LIMIT = OperationTimer(SafetyLimits.MAX_TOTAL_PROCESSING_TIME, "Total Unpackr Runtime")
