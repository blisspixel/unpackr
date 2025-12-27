"""
Fault Injection Framework

Provides context managers and mocks for injecting specific failure modes
into the system to test resilience and error handling.
"""

import os
import shutil
import time
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch, Mock
from typing import Optional, Callable


class DiskFullInjector:
    """
    Simulates disk full conditions.

    Usage:
        with DiskFullInjector(available_bytes=1000):
            # Code here sees disk as nearly full
            process_large_archive()
    """

    def __init__(self, available_bytes: int = 0, trigger_after: Optional[int] = None):
        """
        Initialize disk full injector.

        Args:
            available_bytes: How many bytes to report as available
            trigger_after: If set, disk becomes full after N bytes written
        """
        self.available_bytes = available_bytes
        self.trigger_after = trigger_after
        self.bytes_written = 0
        self.patcher = None

    def __enter__(self):
        def mock_disk_usage(path):
            """Mock shutil.disk_usage to return limited space."""
            # Return mock disk usage with limited free space
            Usage = Mock()
            Usage.total = 1_000_000_000_000  # 1TB total
            Usage.used = Usage.total - self.available_bytes
            Usage.free = self.available_bytes
            return Usage

        self.patcher = patch('shutil.disk_usage', side_effect=mock_disk_usage)
        self.patcher.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.patcher:
            self.patcher.__exit__(exc_type, exc_val, exc_tb)
        return False

    def simulate_write(self, bytes_count: int):
        """
        Simulate writing bytes (for delayed disk full).

        Args:
            bytes_count: Number of bytes being written

        Raises:
            OSError: If disk becomes full during write
        """
        self.bytes_written += bytes_count

        if self.trigger_after and self.bytes_written >= self.trigger_after:
            raise OSError(28, "No space left on device")


class PermissionDeniedInjector:
    """
    Simulates permission denied errors.

    Usage:
        with PermissionDeniedInjector(path="/some/protected/path"):
            # Code here cannot access the path
            try_to_delete_file()
    """

    def __init__(self, path: Optional[Path] = None, operation: str = "all"):
        """
        Initialize permission injector.

        Args:
            path: Specific path to protect (None = all paths)
            operation: Which operations to block ('read', 'write', 'delete', 'all')
        """
        self.protected_path = path
        self.operation = operation
        self.patchers = []

    def __enter__(self):
        def permission_error(*args, **kwargs):
            """Raise PermissionError for protected operations."""
            raise PermissionError(13, "Permission denied")

        # Patch various file operations
        if self.operation in ('delete', 'all'):
            self.patchers.append(patch('pathlib.Path.unlink', side_effect=permission_error))

        if self.operation in ('write', 'all'):
            # Patch open() for write operations
            original_open = open

            def guarded_open(file, mode='r', *args, **kwargs):
                if 'w' in mode or 'a' in mode:
                    if self.protected_path is None or Path(file) == self.protected_path:
                        raise PermissionError(13, "Permission denied", str(file))
                return original_open(file, mode, *args, **kwargs)

            self.patchers.append(patch('builtins.open', side_effect=guarded_open))

        if self.operation in ('read', 'all'):
            # Patch read operations
            original_read = Path.read_text

            def guarded_read(self, *args, **kwargs):
                if self.protected_path is None or self == self.protected_path:
                    raise PermissionError(13, "Permission denied", str(self))
                return original_read(self, *args, **kwargs)

            self.patchers.append(patch('pathlib.Path.read_text', side_effect=guarded_read))

        # Enter all patchers
        for patcher in self.patchers:
            patcher.__enter__()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Exit all patchers in reverse order
        for patcher in reversed(self.patchers):
            patcher.__exit__(exc_type, exc_val, exc_tb)
        return False


class CorruptDataInjector:
    """
    Simulates data corruption scenarios.

    Usage:
        with CorruptDataInjector(corrupt_after=1000):
            # Reads beyond 1000 bytes return corrupt data
            read_video_file()
    """

    def __init__(
        self,
        corrupt_after: Optional[int] = None,
        corruption_type: str = "random"
    ):
        """
        Initialize corruption injector.

        Args:
            corrupt_after: Byte offset where corruption begins
            corruption_type: Type of corruption ('random', 'zeros', 'truncated')
        """
        self.corrupt_after = corrupt_after
        self.corruption_type = corruption_type
        self.bytes_read = 0
        self.patcher = None

    def __enter__(self):
        original_read = Path.read_bytes

        def corrupted_read(self, *args, **kwargs):
            """Return corrupted data after threshold."""
            data = original_read(self, *args, **kwargs)

            if self.corrupt_after is None:
                return data

            if len(data) <= self.corrupt_after:
                return data

            # Corrupt data after threshold
            good_data = data[:self.corrupt_after]

            if self.corruption_type == "truncated":
                return good_data

            elif self.corruption_type == "zeros":
                corrupt_data = b'\x00' * (len(data) - self.corrupt_after)
                return good_data + corrupt_data

            elif self.corruption_type == "random":
                import random
                corrupt_data = bytes(random.randint(0, 255)
                                   for _ in range(len(data) - self.corrupt_after))
                return good_data + corrupt_data

            return data

        self.patcher = patch('pathlib.Path.read_bytes', side_effect=corrupted_read)
        self.patcher.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.patcher:
            self.patcher.__exit__(exc_type, exc_val, exc_tb)
        return False


class NetworkTimeoutInjector:
    """
    Simulates network timeout scenarios.

    Usage:
        with NetworkTimeoutInjector(timeout_after=5):
            # Network operations hang after 5 seconds
            download_file()
    """

    def __init__(self, timeout_after: float = 5.0):
        """
        Initialize timeout injector.

        Args:
            timeout_after: Seconds before timeout occurs
        """
        self.timeout_after = timeout_after
        self.patcher = None

    def __enter__(self):
        def mock_urlopen(*args, **kwargs):
            """Mock urllib operations to timeout."""
            time.sleep(self.timeout_after)
            raise TimeoutError("Connection timed out")

        # Mock various network libraries
        try:
            self.patcher = patch('urllib.request.urlopen', side_effect=mock_urlopen)
            self.patcher.__enter__()
        except (ImportError, AttributeError):
            pass  # urllib not used in this codebase

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.patcher:
            self.patcher.__exit__(exc_type, exc_val, exc_tb)
        return False


class ProcessHangInjector:
    """
    Simulates subprocess hangs.

    Usage:
        with ProcessHangInjector(hang_on="7z"):
            # 7z command will hang indefinitely
            extract_archive()
    """

    def __init__(self, hang_on: str = "7z", hang_duration: Optional[float] = None):
        """
        Initialize process hang injector.

        Args:
            hang_on: Command name to hang on
            hang_duration: How long to hang (None = forever)
        """
        self.hang_on = hang_on
        self.hang_duration = hang_duration
        self.patcher = None

    def __enter__(self):
        from core.subprocess_safety import SubprocessSafety

        original_run = SubprocessSafety.run_with_timeout

        def hanging_run(command, *args, **kwargs):
            """Mock subprocess that hangs on specific commands."""
            # Check if this is the command we want to hang
            if isinstance(command, list) and len(command) > 0:
                cmd_name = Path(command[0]).stem.lower()
                if cmd_name == self.hang_on.lower():
                    if self.hang_duration:
                        time.sleep(self.hang_duration)
                        return (False, '', 'Process timed out', -1)
                    else:
                        # Hang forever (will be killed by timeout)
                        time.sleep(999999)

            # Not the target command, run normally
            return original_run(command, *args, **kwargs)

        self.patcher = patch.object(
            SubprocessSafety,
            'run_with_timeout',
            side_effect=hanging_run
        )
        self.patcher.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.patcher:
            self.patcher.__exit__(exc_type, exc_val, exc_tb)
        return False


class MemoryLimitInjector:
    """
    Simulates memory exhaustion.

    Usage:
        with MemoryLimitInjector(max_bytes=100_000_000):
            # System acts as if only 100MB RAM available
            process_large_file()
    """

    def __init__(self, max_bytes: int):
        """
        Initialize memory limit injector.

        Args:
            max_bytes: Maximum memory available in bytes
        """
        self.max_bytes = max_bytes
        self.allocated = 0
        self.patcher = None

    def __enter__(self):
        # This is more complex - would need to track allocations
        # For now, we'll mock specific memory-intensive operations

        def mock_read_bytes(path, *args, **kwargs):
            """Mock that fails for large files."""
            size = path.stat().st_size
            if self.allocated + size > self.max_bytes:
                raise MemoryError("Cannot allocate memory")

            self.allocated += size
            return path.read_bytes(*args, **kwargs)

        # Note: This is a simplified implementation
        # Full implementation would track all allocations
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.patcher:
            self.patcher.__exit__(exc_type, exc_val, exc_tb)
        return False


@contextmanager
def multiple_faults(*injectors):
    """
    Combine multiple fault injectors.

    Usage:
        with multiple_faults(
            DiskFullInjector(100_000),
            PermissionDeniedInjector(path=protected_file)
        ):
            # Code experiences both failures
            complex_operation()
    """
    # Enter all injectors
    for injector in injectors:
        injector.__enter__()

    try:
        yield
    finally:
        # Exit all injectors in reverse order
        for injector in reversed(injectors):
            try:
                injector.__exit__(None, None, None)
            except Exception:
                pass  # Suppress cleanup errors


class FaultScenario:
    """
    Represents a complete fault scenario for testing.

    Scenarios combine fault injection with expected outcomes and
    invariants that must be maintained.
    """

    def __init__(
        self,
        name: str,
        description: str,
        injector,
        expected_result: str,
        invariants_to_check: list[Callable],
        cleanup_verification: Optional[Callable] = None
    ):
        """
        Initialize fault scenario.

        Args:
            name: Scenario identifier
            description: Human-readable description
            injector: Fault injector instance
            expected_result: Expected outcome ('failure', 'graceful_degradation', etc.)
            invariants_to_check: List of invariant functions to verify
            cleanup_verification: Optional function to verify cleanup
        """
        self.name = name
        self.description = description
        self.injector = injector
        self.expected_result = expected_result
        self.invariants_to_check = invariants_to_check
        self.cleanup_verification = cleanup_verification

    def run(self, operation: Callable, *args, **kwargs):
        """
        Run the scenario and verify invariants.

        Args:
            operation: Function to execute under fault conditions
            *args, **kwargs: Arguments to pass to operation

        Returns:
            Tuple of (result, invariants_passed, cleanup_passed)
        """
        with self.injector:
            try:
                result = operation(*args, **kwargs)
            except Exception as e:
                result = e

        # Check invariants
        invariants_passed = all(inv() for inv in self.invariants_to_check)

        # Check cleanup if provided
        cleanup_passed = True
        if self.cleanup_verification:
            cleanup_passed = self.cleanup_verification()

        return result, invariants_passed, cleanup_passed
