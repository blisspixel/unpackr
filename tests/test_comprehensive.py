"""
Comprehensive test suite for Unpackr.
Tests edge cases, error conditions, and integration scenarios.
Think like a CS PhD - cover all branches, boundaries, and failure modes.
"""

import sys
import tempfile
import shutil
from pathlib import Path
from colorama import init, Fore, Style

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import Config
from core.file_handler import FileHandler
from core.archive_processor import ArchiveProcessor
from core.video_processor import VideoProcessor
from utils.system_check import SystemCheck
from unpackr import WorkPlan, clean_path, UnpackrApp


class TestRunner:
    """Test runner with detailed reporting."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
        init()
    
    def test(self, name: str, condition: bool, error_msg: str = ""):
        """Run a single test."""
        if condition:
            print(f"{Fore.GREEN}✓{Style.RESET_ALL} {name}")
            self.passed += 1
            self.tests.append((name, True, ""))
        else:
            print(f"{Fore.RED}✗{Style.RESET_ALL} {name}")
            if error_msg:
                print(f"  {Fore.RED}Error: {error_msg}{Style.RESET_ALL}")
            self.failed += 1
            self.tests.append((name, False, error_msg))
    
    def summary(self):
        """Display test summary."""
        total = self.passed + self.failed
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"Total: {total} | "
              f"{Fore.GREEN}Passed: {self.passed}{Style.RESET_ALL} | "
              f"{Fore.RED}Failed: {self.failed}{Style.RESET_ALL}")
        
        if self.failed == 0:
            print(f"\n{Fore.GREEN}ALL TESTS PASSED{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}FAILURES DETECTED{Style.RESET_ALL}")
            for name, passed, error in self.tests:
                if not passed:
                    print(f"  - {name}: {error}")
        
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        return self.failed == 0


def test_path_cleaning(runner: TestRunner):
    """Test path cleaning edge cases."""
    print(f"\n{Fore.YELLOW}[Path Cleaning Tests]{Style.RESET_ALL}")
    
    # Basic cases
    runner.test("Clean path: no quotes", 
                clean_path("C:\\test") == "C:\\test")
    runner.test("Clean path: double quotes", 
                clean_path('"C:\\test"') == "C:\\test")
    runner.test("Clean path: single quotes", 
                clean_path("'C:\\test'") == "C:\\test")
    
    # Edge cases
    runner.test("Clean path: whitespace", 
                clean_path("  C:\\test  ") == "C:\\test")
    runner.test("Clean path: quotes + whitespace", 
                clean_path('  "C:\\test"  ') == "C:\\test")
    runner.test("Clean path: empty string", 
                clean_path("") == "")
    runner.test("Clean path: only quotes", 
                clean_path('""') == "")
    runner.test("Clean path: mixed quotes (invalid)", 
                clean_path('"C:\\test\'') == '"C:\\test\'')
    runner.test("Clean path: spaces in path", 
                clean_path('"C:\\Program Files\\test"') == "C:\\Program Files\\test")


def test_work_plan(runner: TestRunner):
    """Test WorkPlan functionality."""
    print(f"\n{Fore.YELLOW}[Work Plan Tests]{Style.RESET_ALL}")
    
    plan = WorkPlan()
    
    # Test empty plan
    runner.test("WorkPlan: Empty initialization", 
                len(plan.video_folders) == 0 and plan.total_videos == 0)
    
    # Add video folder
    test_path = Path("G:/test/video1")
    plan.add_video_folder(test_path, videos=2, rars=1, par2s=3)
    runner.test("WorkPlan: Add video folder - folder count", 
                len(plan.video_folders) == 1)
    runner.test("WorkPlan: Add video folder - video count", 
                plan.total_videos == 2)
    runner.test("WorkPlan: Add video folder - RAR count", 
                plan.total_rars == 1)
    runner.test("WorkPlan: Add video folder - PAR2 count", 
                plan.total_par2s == 3)
    
    # Add content folder
    content_path = Path("G:/test/music")
    plan.add_content_folder(content_path)
    runner.test("WorkPlan: Add content folder", 
                len(plan.content_folders) == 1)
    
    # Add loose video
    video_path = Path("G:/test/video.mp4")
    plan.add_loose_video(video_path)
    runner.test("WorkPlan: Add loose video - count increment", 
                len(plan.loose_videos) == 1 and plan.total_videos == 3)
    
    # Time estimate calculation
    estimate = plan.calculate_time_estimate()
    expected = (3 * 5) + (1 * 10) + (3 * 15) + (1 * 2)  # videos + rars + par2s + folders
    runner.test("WorkPlan: Time estimate calculation", 
                estimate == expected, 
                f"Expected {expected}, got {estimate}")


def test_config_edge_cases(runner: TestRunner):
    """Test configuration loading and defaults."""
    print(f"\n{Fore.YELLOW}[Configuration Tests]{Style.RESET_ALL}")
    
    # Test with no config file (should use defaults)
    config = Config(None)
    runner.test("Config: Default video extensions not empty", 
                len(config.video_extensions) > 0)
    runner.test("Config: Default log folder", 
                config.log_folder == "logs")
    runner.test("Config: Default max log files", 
                config.max_log_files == 5)
    
    # Test video extension access
    extensions = config.video_extensions
    runner.test("Config: Contains .mp4", 
                '.mp4' in extensions)
    runner.test("Config: Contains .avi", 
                '.avi' in extensions)
    runner.test("Config: Contains .mkv", 
                '.mkv' in extensions)


def test_file_handler_boundary_cases(runner: TestRunner):
    """Test FileHandler with boundary cases."""
    print(f"\n{Fore.YELLOW}[File Handler Tests]{Style.RESET_ALL}")
    
    config = Config(None)
    handler = FileHandler(config)
    
    # Test with empty list
    empty_result = handler.find_video_files(Path("."))
    runner.test("FileHandler: find_video_files returns list", 
                isinstance(empty_result, list))
    
    # Test removable file detection
    runner.test("FileHandler: .nfo is removable", 
                '.nfo' in config.removable_extensions)
    runner.test("FileHandler: .sfv is removable", 
                '.sfv' in config.removable_extensions)
    runner.test("FileHandler: .txt is removable", 
                '.txt' in config.removable_extensions)


def test_video_processor_edge_cases(runner: TestRunner):
    """Test VideoProcessor with edge cases."""
    print(f"\n{Fore.YELLOW}[Video Processor Tests]{Style.RESET_ALL}")
    
    processor = VideoProcessor()
    
    # Test sample file detection with actual files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create sample files (small size)
        sample1 = tmp_path / "video-sample.mp4"
        sample1.write_bytes(b'0' * 1000)  # 1KB - definitely a sample
        sample2 = tmp_path / "VIDEO-SAMPLE.avi"
        sample2.write_bytes(b'0' * 1000)  # 1KB
        
        # Create regular file (large enough to not be a sample)
        regular = tmp_path / "regular-video.mp4"
        regular.write_bytes(b'0' * (60 * 1024 * 1024))  # 60MB - not a sample
        
        # Test sample file detection
        runner.test("VideoProcessor: Detect 'sample' in filename", 
                    processor.is_sample_file(sample1))
        runner.test("VideoProcessor: Detect 'SAMPLE' (case insensitive)", 
                    processor.is_sample_file(sample2))
        runner.test("VideoProcessor: Regular file not sample", 
                    not processor.is_sample_file(regular))


def test_system_check_robustness(runner: TestRunner):
    """Test system check functionality."""
    print(f"\n{Fore.YELLOW}[System Check Tests]{Style.RESET_ALL}")
    
    # Test tool checking
    results = SystemCheck.check_all_tools()
    runner.test("SystemCheck: Returns dict", 
                isinstance(results, dict))
    runner.test("SystemCheck: Has 7z key", 
                '7z' in results)
    runner.test("SystemCheck: Has par2 key", 
                'par2' in results)
    runner.test("SystemCheck: Has ffmpeg key", 
                'ffmpeg' in results)
    runner.test("SystemCheck: Boolean values", 
                all(isinstance(v, bool) for v in results.values()))


def test_statistics_accuracy(runner: TestRunner):
    """Test that statistics are accurately tracked."""
    print(f"\n{Fore.YELLOW}[Statistics Tracking Tests]{Style.RESET_ALL}")
    
    config = Config(None)
    app = UnpackrApp(config)
    
    # Initial state
    runner.test("Stats: Initial folders_processed is 0", 
                app.stats['folders_processed'] == 0)
    runner.test("Stats: Initial videos_moved is 0", 
                app.stats['videos_moved'] == 0)
    runner.test("Stats: Initial folders_deleted is 0", 
                app.stats['folders_deleted'] == 0)
    runner.test("Stats: Initial rars_extracted is 0", 
                app.stats['rars_extracted'] == 0)
    runner.test("Stats: Initial par2s_repaired is 0", 
                app.stats['par2s_repaired'] == 0)
    runner.test("Stats: Initial videos_failed is 0", 
                app.stats['videos_failed'] == 0)


def test_glob_pattern_correctness(runner: TestRunner):
    """Test that glob patterns match expected files."""
    print(f"\n{Fore.YELLOW}[Glob Pattern Tests]{Style.RESET_ALL}")
    
    # Create temp directory with test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create test files
        (tmp_path / "video.mp4").touch()
        (tmp_path / "video.avi").touch()
        (tmp_path / "video.mkv").touch()
        (tmp_path / "archive.rar").touch()
        (tmp_path / "archive.r00").touch()
        (tmp_path / "archive.r01").touch()
        (tmp_path / "repair.par2").touch()
        (tmp_path / "document.txt").touch()
        
        # Test video detection
        videos = list(tmp_path.glob('*.mp4')) + list(tmp_path.glob('*.avi')) + list(tmp_path.glob('*.mkv'))
        runner.test("Glob: Finds 3 video files", 
                    len(videos) == 3)
        
        # Test RAR detection
        rars = list(tmp_path.glob('*.rar')) + list(tmp_path.glob('*.r[0-9][0-9]'))
        runner.test("Glob: Finds 3 RAR files (rar + r00 + r01)", 
                    len(rars) == 3)
        
        # Test PAR2 detection
        par2s = list(tmp_path.glob('*.par2'))
        runner.test("Glob: Finds 1 PAR2 file", 
                    len(par2s) == 1)


def test_error_handling(runner: TestRunner):
    """Test error handling and edge cases."""
    print(f"\n{Fore.YELLOW}[Error Handling Tests]{Style.RESET_ALL}")
    
    config = Config(None)
    app = UnpackrApp(config)
    
    # Test with no work plan
    runner.test("App: Handles missing work plan gracefully", 
                app.work_plan is None)
    
    # Test with empty source directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        plan = app.scan_and_plan(tmp_path)
        runner.test("App: Scan empty directory creates plan", 
                    plan is not None)
        runner.test("App: Scan empty directory - zero folders", 
                    len(plan.video_folders) == 0)


def test_folder_classification(runner: TestRunner):
    """Test that folders are correctly classified as video or content."""
    print(f"\n{Fore.YELLOW}[Folder Classification Tests]{Style.RESET_ALL}")
    
    config = Config(None)
    app = UnpackrApp(config)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create video folder
        video_folder = tmp_path / "video_release"
        video_folder.mkdir()
        (video_folder / "video.mp4").touch()
        (video_folder / "video.par2").touch()
        
        # Create content folder (music)
        music_folder = tmp_path / "music_collection"
        music_folder.mkdir()
        (music_folder / "song.mp3").touch()
        
        # Create RAR-only folder (should be video)
        rar_folder = tmp_path / "rar_release"
        rar_folder.mkdir()
        (rar_folder / "archive.rar").touch()
        (rar_folder / "archive.r00").touch()
        
        # Scan and classify
        plan = app.scan_and_plan(tmp_path)
        
        runner.test("Classification: Video folder detected", 
                    len([f for f in plan.video_folders if f['path'].name == 'video_release']) == 1)
        runner.test("Classification: RAR folder detected as video", 
                    len([f for f in plan.video_folders if f['path'].name == 'rar_release']) == 1)
        runner.test("Classification: Music folder detected as content", 
                    len([f for f in plan.content_folders if f.name == 'music_collection']) == 1)


def test_time_estimate_bounds(runner: TestRunner):
    """Test time estimation boundary conditions."""
    print(f"\n{Fore.YELLOW}[Time Estimation Tests]{Style.RESET_ALL}")
    
    # Zero items
    plan1 = WorkPlan()
    estimate1 = plan1.calculate_time_estimate()
    runner.test("Time estimate: Zero items = 0 seconds", 
                estimate1 == 0)
    
    # Single item of each type
    plan2 = WorkPlan()
    plan2.add_video_folder(Path("test"), videos=1, rars=1, par2s=1)
    estimate2 = plan2.calculate_time_estimate()
    expected2 = (1 * 5) + (1 * 10) + (1 * 15) + (1 * 2)  # 32 seconds
    runner.test("Time estimate: Single items calculation", 
                estimate2 == expected2,
                f"Expected {expected2}, got {estimate2}")
    
    # Large numbers
    plan3 = WorkPlan()
    for i in range(100):
        plan3.add_video_folder(Path(f"test{i}"), videos=2, rars=1, par2s=1)
    estimate3 = plan3.calculate_time_estimate()
    expected3 = (200 * 5) + (100 * 10) + (100 * 15) + (100 * 2)  # Should be consistent
    runner.test("Time estimate: Large numbers (100 folders)", 
                estimate3 == expected3,
                f"Expected {expected3}, got {estimate3}")


def test_path_edge_cases(runner: TestRunner):
    """Test path handling edge cases."""
    print(f"\n{Fore.YELLOW}[Path Edge Cases]{Style.RESET_ALL}")
    
    # Windows path variations
    runner.test("Path: Windows backslash preserved",
                "C:\\test" in clean_path("C:\\test"))
    runner.test("Path: UNC path support",
                clean_path('"\\\\server\\share"') == "\\\\server\\share")
    runner.test("Path: Drive letter only",
                clean_path('"C:"') == "C:")
    
    # Special characters
    runner.test("Path: Spaces preserved",
                "Program Files" in clean_path('"C:\\Program Files"'))
    runner.test("Path: Parentheses preserved",
                "(x86)" in clean_path('"C:\\Program Files (x86)"'))


def main():
    """Run all tests."""
    print(f"\n{Fore.CYAN}{'='*70}")
    print("COMPREHENSIVE TEST SUITE - CS PhD LEVEL")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    runner = TestRunner()
    
    # Run all test suites
    test_path_cleaning(runner)
    test_work_plan(runner)
    test_config_edge_cases(runner)
    test_file_handler_boundary_cases(runner)
    test_video_processor_edge_cases(runner)
    test_system_check_robustness(runner)
    test_statistics_accuracy(runner)
    test_glob_pattern_correctness(runner)
    test_error_handling(runner)
    test_folder_classification(runner)
    test_time_estimate_bounds(runner)
    test_path_edge_cases(runner)
    
    # Display summary
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
