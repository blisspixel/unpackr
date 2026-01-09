"""
Safety mechanism tests for Unpackr.
Tests timeout protection, loop guards, recursion limits, and runaway detection.
"""

import sys
import time
from pathlib import Path
from colorama import init, Fore, Style

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.safety import (
    SafetyLimits, TimeoutGuard, TimeoutException, SubprocessSafety,
    LoopSafety, RecursionSafety, OperationTimer, StuckDetector
)


class SafetyTestRunner:
    """Test runner for safety mechanisms."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        init()
    
    def test(self, name: str, condition: bool):
        """Run a single test."""
        if condition:
            print(f"{Fore.GREEN}✓{Style.RESET_ALL} {name}")
            self.passed += 1
        else:
            print(f"{Fore.RED}✗{Style.RESET_ALL} {name}")
            self.failed += 1
    
    def summary(self):
        """Display summary."""
        total = self.passed + self.failed
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"Safety Tests: {total} | "
              f"{Fore.GREEN}Passed: {self.passed}{Style.RESET_ALL} | "
              f"{Fore.RED}Failed: {self.failed}{Style.RESET_ALL}")
        if self.failed == 0:
            print(f"{Fore.GREEN}ALL SAFETY TESTS PASSED{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        return self.failed == 0


def test_timeout_guard(runner: SafetyTestRunner):
    """Test timeout guard mechanism."""
    print(f"\n{Fore.YELLOW}[Timeout Guard Tests]{Style.RESET_ALL}")
    
    # Test successful operation
    try:
        with TimeoutGuard(2, "Quick operation"):
            time.sleep(0.1)
        runner.test("TimeoutGuard: Allows quick operation", True)
    except TimeoutException:
        runner.test("TimeoutGuard: Allows quick operation", False)
    
    # Test timeout trigger (this will actually timeout)
    timed_out = False
    try:
        with TimeoutGuard(1, "Slow operation"):
            time.sleep(2)
    except TimeoutException:
        timed_out = True
    runner.test("TimeoutGuard: Triggers on timeout", timed_out)


def test_subprocess_safety(runner: SafetyTestRunner):
    """Test safe subprocess execution."""
    print(f"\n{Fore.YELLOW}[Subprocess Safety Tests]{Style.RESET_ALL}")
    
    # Test successful command
    success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
        ['echo', 'test'],
        timeout=5,
        operation="Echo test"
    )
    runner.test("SubprocessSafety: Successful command", success and code == 0)
    
    # Test command with timeout (this should timeout)
    import platform
    if platform.system() == 'Windows':
        # Windows sleep command
        success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
            ['timeout', '/t', '10'],
            timeout=2,
            operation="Timeout test"
        )
        runner.test("SubprocessSafety: Timeout detection", not success)


def test_loop_safety(runner: SafetyTestRunner):
    """Test loop safety mechanism."""
    print(f"\n{Fore.YELLOW}[Loop Safety Tests]{Style.RESET_ALL}")
    
    # Test normal loop
    guard = LoopSafety(10, "Test loop")
    count = 0
    while guard.tick() and count < 5:
        count += 1
    runner.test("LoopSafety: Allows normal loop", count == 5)
    
    # Test loop limit
    guard2 = LoopSafety(10, "Limited loop")
    count2 = 0
    while guard2.tick():
        count2 += 1
        if count2 > 20:  # Safety
            break
    runner.test("LoopSafety: Enforces limit", count2 == 11)  # Stops at max_iterations + 1


def test_recursion_safety(runner: SafetyTestRunner):
    """Test recursion depth protection."""
    print(f"\n{Fore.YELLOW}[Recursion Safety Tests]{Style.RESET_ALL}")
    
    guard = RecursionSafety(5, "Test recursion")
    
    def recursive_func(depth):
        if not guard.enter():
            return depth
        try:
            if depth < 10:
                return recursive_func(depth + 1)
            return depth
        finally:
            guard.exit()
    
    max_depth = recursive_func(0)
    runner.test("RecursionSafety: Limits recursion depth", max_depth <= 5)


def test_operation_timer(runner: SafetyTestRunner):
    """Test operation timer."""
    print(f"\n{Fore.YELLOW}[Operation Timer Tests]{Style.RESET_ALL}")
    
    # Test within time limit
    timer = OperationTimer(5, "Quick test")
    time.sleep(0.1)
    runner.test("OperationTimer: Within limit", timer.check())
    
    # Test exceeded time limit
    timer2 = OperationTimer(1, "Slow test")
    time.sleep(1.5)
    runner.test("OperationTimer: Detects exceeded", not timer2.check())
    
    # Test elapsed time
    timer3 = OperationTimer(10, "Elapsed test")
    time.sleep(0.5)
    elapsed = timer3.elapsed()
    runner.test("OperationTimer: Tracks elapsed time", 0.4 < elapsed < 0.7)


def test_stuck_detector(runner: SafetyTestRunner):
    """Test stuck process detection."""
    print(f"\n{Fore.YELLOW}[Stuck Detector Tests]{Style.RESET_ALL}")
    
    # Test with progress
    detector = StuckDetector(timeout=2, check_interval=1)
    time.sleep(0.5)
    detector.mark_progress()
    time.sleep(0.5)
    runner.test("StuckDetector: Healthy with progress", detector.check())
    
    # Test stuck detection
    detector2 = StuckDetector(timeout=1, check_interval=0.5)
    time.sleep(1.5)
    runner.test("StuckDetector: Detects stuck state", not detector2.check())


def test_safety_limits_config(runner: SafetyTestRunner):
    """Test safety limits configuration."""
    print(f"\n{Fore.YELLOW}[Safety Limits Configuration]{Style.RESET_ALL}")
    
    runner.test("SafetyLimits: RAR timeout defined", SafetyLimits.RAR_EXTRACTION_TIMEOUT > 0)
    runner.test("SafetyLimits: PAR2 timeout defined", SafetyLimits.PAR2_REPAIR_TIMEOUT > 0)
    runner.test("SafetyLimits: Video check timeout defined", SafetyLimits.VIDEO_CHECK_TIMEOUT > 0)
    runner.test("SafetyLimits: Max retries defined", SafetyLimits.MAX_FILE_DELETE_RETRIES > 0)
    runner.test("SafetyLimits: Recursion depth defined", SafetyLimits.MAX_SUBFOLDERS_DEPTH > 0)
    runner.test("SafetyLimits: Total time limit defined", SafetyLimits.MAX_TOTAL_PROCESSING_TIME > 0)


def test_process_tracker(runner: SafetyTestRunner):
    """Test subprocess process tracking for cancellation."""
    print(f"\n{Fore.YELLOW}[Process Tracker Tests]{Style.RESET_ALL}")
    
    # Create a mock process tracker
    class MockTracker:
        def __init__(self):
            self.active_process = None
    
    tracker = MockTracker()
    
    # Test that process is tracked during execution
    import platform
    if platform.system() == 'Windows':
        # Run a quick command with tracker
        success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
            ['cmd', '/c', 'echo test'],
            timeout=5,
            operation="Tracked command",
            process_tracker=tracker
        )
        # After completion, active_process should be None
        runner.test("ProcessTracker: Clears after completion", tracker.active_process is None)
        runner.test("ProcessTracker: Command succeeded", success)
    else:
        runner.test("ProcessTracker: Skipped (non-Windows)", True)


def test_cancellation_flag(runner: SafetyTestRunner):
    """Test cancellation flag behavior in UnpackrApp."""
    print(f"\n{Fore.YELLOW}[Cancellation Flag Tests]{Style.RESET_ALL}")
    
    from core import Config
    from unpackr import UnpackrApp
    
    # Create app with default config
    config = Config(None)
    app = UnpackrApp(config)
    
    # Test initial state
    runner.test("Cancellation: Initial flag is False", app.cancellation_requested == False)
    runner.test("Cancellation: Initial active_process is None", app.active_process is None)
    
    # Test flag can be set
    app.cancellation_requested = True
    runner.test("Cancellation: Flag can be set", app.cancellation_requested == True)
    
    # Test archive_processor has tracker reference
    runner.test("Cancellation: ArchiveProcessor has tracker", 
                app.archive_processor.process_tracker is app)
    
    # Test video_processor has tracker reference
    runner.test("Cancellation: VideoProcessor has tracker", 
                app.video_processor.process_tracker is app)


def main():
    """Run all safety tests."""
    print(f"\n{Fore.CYAN}{'='*70}")
    print("SAFETY MECHANISM TESTS")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    runner = SafetyTestRunner()
    
    test_timeout_guard(runner)
    test_subprocess_safety(runner)
    test_loop_safety(runner)
    test_recursion_safety(runner)
    test_operation_timer(runner)
    test_stuck_detector(runner)
    test_safety_limits_config(runner)
    test_process_tracker(runner)
    test_cancellation_flag(runner)
    
    success = runner.summary()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
