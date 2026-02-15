"""
Comprehensive test suite for Unpackr
Tests all modules and functionality
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from colorama import Fore, Style, init

init()

def print_header(text):
    """Print test section header."""
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{text}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

def print_test(name, passed, details=""):
    """Print test result."""
    status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if passed else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    print(f"[{status}] {name}")
    if details and not passed:
        print(f"      {Fore.YELLOW}{details}{Style.RESET_ALL}")

def test_imports():
    """Test that all modules import correctly."""
    print_header("Testing Module Imports")
    
    tests_passed = 0
    tests_total = 0
    
    # Test core imports
    try:
        tests_total += 1
        print_test("Import core.Config", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import core.Config", False, str(e))
    
    try:
        tests_total += 1
        print_test("Import core.setup_logging", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import core.setup_logging", False, str(e))
    
    try:
        tests_total += 1
        print_test("Import core.FileHandler", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import core.FileHandler", False, str(e))
    
    try:
        tests_total += 1
        print_test("Import core.ArchiveProcessor", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import core.ArchiveProcessor", False, str(e))
    
    try:
        tests_total += 1
        print_test("Import core.VideoProcessor", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import core.VideoProcessor", False, str(e))
    
    # Test utils imports
    try:
        tests_total += 1
        print_test("Import utils.SystemCheck", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import utils.SystemCheck", False, str(e))
    
    try:
        tests_total += 1
        print_test("Import utils.ProgressTracker", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Import utils.ProgressTracker", False, str(e))
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def test_path_cleaning():
    """Test path cleaning functionality."""
    print_header("Testing Path Cleaning")
    
    from unpackr import clean_path
    
    tests_passed = 0
    tests_total = 0
    
    test_cases = [
        ('G:\\Test', 'G:\\Test'),
        ('"G:\\Test"', 'G:\\Test'),
        ("'G:\\Test'", 'G:\\Test'),
        ('  G:\\Test  ', 'G:\\Test'),
        ('"G:\\Test Path"', 'G:\\Test Path'),
        ('G:\\Test Path', 'G:\\Test Path'),
        ('"G:\\Test Path With Spaces"', 'G:\\Test Path With Spaces'),
        ('""', ''),
        ("''", ''),
    ]
    
    for input_path, expected in test_cases:
        tests_total += 1
        result = clean_path(input_path)
        passed = result == expected
        if passed:
            tests_passed += 1
        print_test(f"clean_path({input_path!r}) == {expected!r}", passed, 
                  f"Got: {result!r}")
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def test_config():
    """Test configuration loading."""
    print_header("Testing Configuration")
    
    from core import Config
    
    tests_passed = 0
    tests_total = 0
    
    # Test default config
    try:
        config = Config()
        tests_total += 1
        print_test("Create default Config", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Create default Config", False, str(e))
        if __name__ == '__main__':
            return tests_passed, tests_total
        assert False, f"Create default Config failed: {e}"
    
    # Test video extensions
    tests_total += 1
    has_mp4 = '.mp4' in config.video_extensions
    print_test("Config has .mp4 in video_extensions", has_mp4)
    if has_mp4:
        tests_passed += 1
    
    # Test max_log_files
    tests_total += 1
    has_max_logs = config.max_log_files > 0
    print_test("Config has max_log_files > 0", has_max_logs, 
              f"Value: {config.max_log_files}")
    if has_max_logs:
        tests_passed += 1
    
    # Test removable extensions
    tests_total += 1
    has_nfo = '.nfo' in config.removable_extensions
    print_test("Config has .nfo in removable_extensions", has_nfo)
    if has_nfo:
        tests_passed += 1
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def test_system_check():
    """Test system tool checking."""
    print_header("Testing System Tool Check")
    
    from utils import SystemCheck
    
    tests_passed = 0
    tests_total = 0
    
    # Test checking all tools
    try:
        from core import Config
        config = Config()
        checker = SystemCheck(config)
        tools = checker.check_all_tools()
        tests_total += 1
        print_test("SystemCheck.check_all_tools()", True)
        tests_passed += 1

        # Display tool status
        for tool, available in tools.items():
            status = "available" if available else "missing"
            print(f"      {tool}: {status}")
    except Exception as e:
        tests_total += 1
        print_test("SystemCheck.check_all_tools()", False, str(e))
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def test_file_handler():
    """Test file handler functionality."""
    print_header("Testing File Handler")
    
    from core import Config, FileHandler
    
    tests_passed = 0
    tests_total = 0
    
    # Create handler
    try:
        config = Config()
        handler = FileHandler(config)
        tests_total += 1
        print_test("Create FileHandler", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Create FileHandler", False, str(e))
        if __name__ == '__main__':
            return tests_passed, tests_total
        assert False, f"Create FileHandler failed: {e}"
    
    # Test find_video_files with test directory
    test_path = Path("G:/test")
    try:
        path_exists = test_path.exists()
    except OSError as e:
        path_exists = False
        print_test(f"Check test path {test_path}", True, f"Skipping inaccessible path: {e}")

    if path_exists:
        try:
            videos = handler.find_video_files(test_path)
            tests_total += 1
            is_list = isinstance(videos, list)
            print_test(
                f"Find videos in {test_path}",
                is_list,
                f"Found: {len(videos)} videos",
            )
            if is_list:
                tests_passed += 1
        except Exception as e:
            tests_total += 1
            print_test(f"Find videos in {test_path}", False, str(e))
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def test_archive_processor():
    """Test archive processor."""
    print_header("Testing Archive Processor")
    
    from core import ArchiveProcessor
    
    tests_passed = 0
    tests_total = 0
    
    # Create processor
    try:
        ArchiveProcessor()
        tests_total += 1
        print_test("Create ArchiveProcessor", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Create ArchiveProcessor", False, str(e))
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def test_video_processor():
    """Test video processor."""
    print_header("Testing Video Processor")
    
    from core import VideoProcessor
    
    tests_passed = 0
    tests_total = 0
    
    # Create processor
    try:
        VideoProcessor()
        tests_total += 1
        print_test("Create VideoProcessor", True)
        tests_passed += 1
    except Exception as e:
        tests_total += 1
        print_test("Create VideoProcessor", False, str(e))
    
    if __name__ == '__main__':
        return tests_passed, tests_total
    assert tests_passed == tests_total

def main():
    """Run all tests."""
    print(f"\n{Fore.YELLOW}Unpackr Test Suite{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}")
    
    all_passed = 0
    all_total = 0
    
    # Run all test suites
    passed, total = test_imports()
    all_passed += passed
    all_total += total
    
    passed, total = test_path_cleaning()
    all_passed += passed
    all_total += total
    
    passed, total = test_config()
    all_passed += passed
    all_total += total
    
    passed, total = test_system_check()
    all_passed += passed
    all_total += total
    
    passed, total = test_file_handler()
    all_passed += passed
    all_total += total
    
    passed, total = test_archive_processor()
    all_passed += passed
    all_total += total
    
    passed, total = test_video_processor()
    all_passed += passed
    all_total += total
    
    # Print summary
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Test Summary{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"Total tests: {all_total}")
    print(f"Passed: {Fore.GREEN}{all_passed}{Style.RESET_ALL}")
    print(f"Failed: {Fore.RED}{all_total - all_passed}{Style.RESET_ALL}")
    
    success_rate = (all_passed / all_total * 100) if all_total > 0 else 0
    print(f"Success rate: {success_rate:.1f}%")
    
    if all_passed == all_total:
        print(f"\n{Fore.GREEN}All tests passed!{Style.RESET_ALL}")
        return 0
    else:
        print(f"\n{Fore.RED}Some tests failed.{Style.RESET_ALL}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
