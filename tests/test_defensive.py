"""
Defensive Programming Test Suite
Tests input validation, state checks, and error recovery mechanisms.
"""

import sys
import tempfile
from pathlib import Path
from colorama import init, Fore, Style

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.defensive import (
    InputValidator, StateValidator, ErrorRecovery, ValidationError
)


class DefensiveTestRunner:
    """Test runner for defensive mechanisms."""
    
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
        print(f"Defensive Tests: {total} | "
              f"{Fore.GREEN}Passed: {self.passed}{Style.RESET_ALL} | "
              f"{Fore.RED}Failed: {self.failed}{Style.RESET_ALL}")
        if self.failed == 0:
            print(f"{Fore.GREEN}ALL DEFENSIVE TESTS PASSED - S TIER!{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        return self.failed == 0


def test_path_validation(runner: DefensiveTestRunner):
    """Test path input validation."""
    print(f"\n{Fore.YELLOW}[Path Validation]{Style.RESET_ALL}")
    
    # Valid path
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        try:
            result = InputValidator.validate_path(tmp_path, must_exist=True)
            runner.test("PathValidation: Valid existing path", result is not None)
        except ValidationError:
            runner.test("PathValidation: Valid existing path", False)
    
    # None handling
    try:
        InputValidator.validate_path(None, allow_none=True)
        runner.test("PathValidation: Allow None when permitted", True)
    except ValidationError:
        runner.test("PathValidation: Allow None when permitted", False)
    
    # Reject None when not allowed
    try:
        InputValidator.validate_path(None, allow_none=False)
        runner.test("PathValidation: Reject None when not allowed", False)
    except ValidationError:
        runner.test("PathValidation: Reject None when not allowed", True)
    
    # Non-existent path with must_exist
    try:
        InputValidator.validate_path("/nonexistent/path/to/nowhere", must_exist=True)
        runner.test("PathValidation: Reject non-existent path", False)
    except ValidationError:
        runner.test("PathValidation: Reject non-existent path", True)
    
    # String to Path conversion
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = InputValidator.validate_path(tmpdir, must_exist=True)
            runner.test("PathValidation: Convert string to Path", isinstance(result, Path))
        except ValidationError:
            runner.test("PathValidation: Convert string to Path", False)
    
    # Invalid type
    try:
        InputValidator.validate_path(123, must_exist=False)
        runner.test("PathValidation: Reject invalid type", False)
    except ValidationError:
        runner.test("PathValidation: Reject invalid type", True)


def test_string_validation(runner: DefensiveTestRunner):
    """Test string input validation."""
    print(f"\n{Fore.YELLOW}[String Validation]{Style.RESET_ALL}")
    
    # Valid string
    try:
        result = InputValidator.validate_string("test")
        runner.test("StringValidation: Valid string", result == "test")
    except ValidationError:
        runner.test("StringValidation: Valid string", False)
    
    # Length constraints
    try:
        InputValidator.validate_string("ab", min_length=5)
        runner.test("StringValidation: Enforce min length", False)
    except ValidationError:
        runner.test("StringValidation: Enforce min length", True)
    
    try:
        InputValidator.validate_string("a" * 100, max_length=50)
        runner.test("StringValidation: Enforce max length", False)
    except ValidationError:
        runner.test("StringValidation: Enforce max length", True)
    
    # Empty string handling
    try:
        InputValidator.validate_string("", allow_empty=False)
        runner.test("StringValidation: Reject empty when not allowed", False)
    except ValidationError:
        runner.test("StringValidation: Reject empty when not allowed", True)
    
    # Null byte removal
    result = InputValidator.validate_string("test\x00string")
    runner.test("StringValidation: Remove null bytes", "\x00" not in result)


def test_int_validation(runner: DefensiveTestRunner):
    """Test integer input validation."""
    print(f"\n{Fore.YELLOW}[Integer Validation]{Style.RESET_ALL}")
    
    # Valid integer
    try:
        result = InputValidator.validate_int(42)
        runner.test("IntValidation: Valid integer", result == 42)
    except ValidationError:
        runner.test("IntValidation: Valid integer", False)
    
    # Range constraints
    try:
        InputValidator.validate_int(5, min_val=10)
        runner.test("IntValidation: Enforce min value", False)
    except ValidationError:
        runner.test("IntValidation: Enforce min value", True)
    
    try:
        InputValidator.validate_int(100, max_val=50)
        runner.test("IntValidation: Enforce max value", False)
    except ValidationError:
        runner.test("IntValidation: Enforce max value", True)
    
    # String to int conversion
    try:
        result = InputValidator.validate_int("42")
        runner.test("IntValidation: Convert string to int", result == 42)
    except ValidationError:
        runner.test("IntValidation: Convert string to int", False)


def test_state_validation(runner: DefensiveTestRunner):
    """Test state validation checks."""
    print(f"\n{Fore.YELLOW}[State Validation]{Style.RESET_ALL}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # File accessibility
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        runner.test("StateValidation: Check file accessible", 
                   StateValidator.check_file_accessible(test_file))
        
        # Directory writable
        runner.test("StateValidation: Check directory writable",
                   StateValidator.check_dir_writable(tmp_path))
        
        # Disk space check
        runner.test("StateValidation: Check disk space",
                   StateValidator.check_disk_space(tmp_path, required_mb=1))


def test_error_recovery(runner: DefensiveTestRunner):
    """Test error recovery mechanisms."""
    print(f"\n{Fore.YELLOW}[Error Recovery]{Style.RESET_ALL}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Safe delete
        test_file = tmp_path / "delete_me.txt"
        test_file.write_text("test")
        result = ErrorRecovery.safe_delete(test_file)
        runner.test("ErrorRecovery: Safe delete file", result and not test_file.exists())
        
        # Safe delete non-existent (should succeed)
        result = ErrorRecovery.safe_delete(tmp_path / "nonexistent.txt")
        runner.test("ErrorRecovery: Safe delete non-existent", result)
        
        # Safe move
        src = tmp_path / "source.txt"
        dst = tmp_path / "dest.txt"
        src.write_text("test")
        result = ErrorRecovery.safe_move(src, dst)
        runner.test("ErrorRecovery: Safe move file", result and dst.exists() and not src.exists())
        
        # Safe read text
        read_file = tmp_path / "read_me.txt"
        read_file.write_text("test content")
        content = ErrorRecovery.safe_read_text(read_file)
        runner.test("ErrorRecovery: Safe read text", content == "test content")
        
        # Safe read non-existent (should return default)
        content = ErrorRecovery.safe_read_text(tmp_path / "nonexistent.txt", default="default")
        runner.test("ErrorRecovery: Safe read non-existent returns default", content == "default")


def test_list_validation(runner: DefensiveTestRunner):
    """Test list input validation."""
    print(f"\n{Fore.YELLOW}[List Validation]{Style.RESET_ALL}")
    
    # Valid list
    try:
        result = InputValidator.validate_list([1, 2, 3])
        runner.test("ListValidation: Valid list", result == [1, 2, 3])
    except ValidationError:
        runner.test("ListValidation: Valid list", False)
    
    # Length constraints
    try:
        InputValidator.validate_list([1], min_length=5)
        runner.test("ListValidation: Enforce min length", False)
    except ValidationError:
        runner.test("ListValidation: Enforce min length", True)
    
    try:
        InputValidator.validate_list([1] * 100, max_length=50)
        runner.test("ListValidation: Enforce max length", False)
    except ValidationError:
        runner.test("ListValidation: Enforce max length", True)


def main():
    """Run all defensive tests."""
    print(f"\n{Fore.CYAN}{'='*70}")
    print("DEFENSIVE PROGRAMMING TEST SUITE")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    runner = DefensiveTestRunner()
    
    test_path_validation(runner)
    test_string_validation(runner)
    test_int_validation(runner)
    test_state_validation(runner)
    test_error_recovery(runner)
    test_list_validation(runner)
    
    success = runner.summary()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
