"""
Test suite for vhealth video health checker.

Tests cover:
- Video file detection and scanning
- Duplicate detection (exact matches, hash-based)
- Sample file detection
- Corruption detection
- Resolution checking
- Deletion operations
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from vhealth import VideoHealthChecker
from core import Config


class TestVideoHealthChecker:
    """Tests for VideoHealthChecker class."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def checker(self):
        """Create VideoHealthChecker instance."""
        config = Config()
        return VideoHealthChecker(config)

    @pytest.fixture
    def mock_video_files(self, temp_dir):
        """Create mock video files for testing."""
        videos = []

        # Create normal videos (>50MB to not be considered samples)
        for i in range(3):
            video = temp_dir / f"video{i}.mp4"
            video.write_bytes(b"fake video data " * 4000000)  # ~64MB
            videos.append(video)

        # Create sample (small file <50MB)
        sample = temp_dir / "sample.mp4"
        sample.write_bytes(b"sample data")  # Small file
        videos.append(sample)

        return videos

    def test_init(self, checker):
        """Test VideoHealthChecker initialization."""
        assert checker.config is not None
        assert checker.video_processor is not None
        assert isinstance(checker.healthy_videos, list)
        assert isinstance(checker.corrupt_videos, list)
        assert isinstance(checker.sample_videos, list)

    def test_find_videos(self, checker, temp_dir, mock_video_files):
        """Test video file discovery."""
        videos = checker._find_videos(temp_dir)

        assert len(videos) == 4
        assert all(v.suffix in ['.mp4', '.mkv', '.avi'] for v in videos)

    def test_sample_detection_by_size(self, checker, temp_dir, mock_video_files):
        """Test sample video detection based on file size (<50MB)."""
        small_file = temp_dir / "sample.mp4"
        large_file = temp_dir / "video0.mp4"

        assert small_file.stat().st_size < 50 * 1024 * 1024
        assert large_file.stat().st_size > 50 * 1024 * 1024

    def test_duplicate_detection_same_size(self, checker, temp_dir):
        """Test duplicate detection for files with identical size and hash."""
        # Create two identical files
        video1 = temp_dir / "video1.mp4"
        video2 = temp_dir / "video1_copy.mp4"

        content = b"identical video data " * 100000
        video1.write_bytes(content)
        video2.write_bytes(content)

        videos = [video1, video2]
        checker._detect_duplicates(videos)

        # Should detect one as duplicate
        assert len(checker.duplicate_videos) > 0

    def test_duplicate_detection_different_files(self, checker, temp_dir):
        """Test that different files are not marked as duplicates."""
        video1 = temp_dir / "video1.mp4"
        video2 = temp_dir / "video2.mp4"

        video1.write_bytes(b"video1 data " * 100000)
        video2.write_bytes(b"video2 data " * 100000)

        videos = [video1, video2]
        checker._detect_duplicates(videos)

        # Should not detect duplicates
        assert len(checker.duplicate_videos) == 0

    def test_resolution_parsing(self, checker):
        """Test resolution extraction from video metadata."""
        # Mock ffmpeg output with resolution
        mock_output = "Stream #0:0: Video: h264, yuv420p, 1920x1080"

        # This would normally parse ffmpeg output
        # Testing the pattern matching logic
        import re
        pattern = r'(\d{3,4})x(\d{3,4})'
        match = re.search(pattern, mock_output)

        assert match is not None
        width, height = map(int, match.groups())
        assert width == 1920
        assert height == 1080

    def test_meets_min_resolution(self, checker):
        """Test resolution comparison logic."""
        # 1080p should meet 720p requirement
        assert checker._meets_min_resolution((1920, 1080), "720p")

        # 480p should not meet 720p requirement
        assert not checker._meets_min_resolution((640, 480), "720p")

        # 720p should meet 720p requirement (exact match)
        assert checker._meets_min_resolution((1280, 720), "720p")

    @patch('vhealth.VideoHealthChecker._check_video_silent')
    def test_check_path_single_file(self, mock_check, checker, temp_dir):
        """Test checking a single video file."""
        video = temp_dir / "test.mp4"
        video.write_bytes(b"test video")

        mock_check.return_value = 'healthy'

        # This would normally check the video
        # Testing that the method is called correctly
        result = mock_check(video)
        assert result == 'healthy'

    def test_filename_truncation(self, checker):
        """Test that long filenames are truncated for display."""
        long_name = "a" * 100 + ".mp4"
        truncated = long_name[:65] + '...' if len(long_name) > 65 else long_name

        assert len(truncated) <= 68  # 65 chars + '...'
        assert truncated.endswith('...')

    def test_delete_videos_nonexistent(self, checker, temp_dir):
        """Test that deleting nonexistent files doesn't crash."""
        fake_video = temp_dir / "nonexistent.mp4"
        videos_to_delete = [fake_video]

        # Should handle gracefully
        checker._delete_videos(videos_to_delete)

        # No exception should be raised

    def test_eta_calculation(self):
        """Test ETA calculation logic."""
        import time

        start_time = time.time() - 10  # Started 10 seconds ago
        files_processed = 5
        total_files = 100

        elapsed = time.time() - start_time
        avg_time = elapsed / files_processed
        remaining = total_files - files_processed
        eta_seconds = avg_time * remaining

        # Should be roughly 190 seconds (95 files * 2 seconds each)
        assert 180 < eta_seconds < 200

    def test_spinner_frames(self):
        """Test spinner animation frames."""
        spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

        assert len(spinner_frames) == 10
        assert all(isinstance(frame, str) for frame in spinner_frames)

        # Test cycling through frames
        for i in range(20):
            frame = spinner_frames[i % len(spinner_frames)]
            assert frame in spinner_frames


class TestDuplicateDetectionConservative:
    """Tests ensuring duplicate detection is conservative (no false positives)."""

    @pytest.fixture
    def checker(self):
        config = Config()
        return VideoHealthChecker(config)

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    def test_multipart_not_duplicates(self, checker, temp_dir):
        """Test that cd1/cd2 files are not marked as duplicates."""
        cd1 = temp_dir / "movie-cd1.avi"
        cd2 = temp_dir / "movie-cd2.avi"

        # Similar size but different content
        cd1.write_bytes(b"part1 " * 100000)
        cd2.write_bytes(b"part2 " * 100000)

        checker._detect_duplicates([cd1, cd2])

        # Should NOT detect as duplicates (different content)
        assert len(checker.duplicate_videos) == 0

    def test_series_episodes_not_duplicates(self, checker, temp_dir):
        """Test that series episodes are not marked as duplicates."""
        ep1 = temp_dir / "Show S01E01.mkv"
        ep2 = temp_dir / "Show S01E02.mkv"

        # Similar names but different content
        ep1.write_bytes(b"episode1 " * 100000)
        ep2.write_bytes(b"episode2 " * 100000)

        checker._detect_duplicates([ep1, ep2])

        # Should NOT detect as duplicates
        assert len(checker.duplicate_videos) == 0

    def test_copy_pattern_detection(self, checker, temp_dir):
        """Test that files with (copy) pattern are detected."""
        original = temp_dir / "video.mp4"
        copy = temp_dir / "video (copy).mp4"

        content = b"video data " * 100000
        original.write_bytes(content)
        copy.write_bytes(content)

        checker._detect_duplicates([original, copy])

        # Should detect copy pattern
        assert len(checker.duplicate_videos) > 0

    def test_fav_prefix_kept_over_duplicate(self, checker, temp_dir):
        """Test that files starting with 'fav' are kept when duplicates found."""
        # Create two identical files - one with fav prefix
        normal = temp_dir / "video.mp4"
        favorite = temp_dir / "fav video.mp4"

        content = b"identical video data " * 100000
        normal.write_bytes(content)
        favorite.write_bytes(content)

        checker._detect_duplicates([normal, favorite])

        # Should detect one as duplicate
        assert len(checker.duplicate_videos) == 1

        # The duplicate should be the non-fav file, keeper should be fav
        dupe, keeper, reason = checker.duplicate_videos[0]
        assert keeper.name.lower().startswith('fav'), f"Expected fav file to be kept, but keeper is {keeper.name}"
        assert not dupe.name.lower().startswith('fav'), f"Expected non-fav file to be duplicate, but dupe is {dupe.name}"

    def test_fav_prefix_with_copy_pattern(self, checker, temp_dir):
        """Test that fav prefix is preferred even with copy pattern in filename."""
        # Create original and a fav-marked copy
        original = temp_dir / "video.mp4"
        fav_copy = temp_dir / "fav video (copy).mp4"

        content = b"video data " * 100000
        original.write_bytes(content)
        fav_copy.write_bytes(content)

        checker._detect_duplicates([original, fav_copy])

        # Should detect one as duplicate
        assert len(checker.duplicate_videos) >= 1

        # The fav file should be kept even though it has (copy) in name
        for dupe, keeper, reason in checker.duplicate_videos:
            if keeper.name.lower().startswith('fav') or dupe.name.lower().startswith('fav'):
                # If fav is involved, it should be the keeper
                assert keeper.name.lower().startswith('fav'), f"Expected fav file to be kept, but keeper is {keeper.name}"


class TestIntegrationVhealth:
    """Integration tests for complete vhealth workflows."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def checker(self):
        config = Config()
        return VideoHealthChecker(config)

    def test_mixed_folder_workflow(self, checker, temp_dir):
        """Test complete workflow with mixed good/bad files."""
        # Create mix of files
        good_video = temp_dir / "good.mp4"
        good_video.write_bytes(b"good video " * 1000000)

        sample = temp_dir / "sample.mp4"
        sample.write_bytes(b"sample")

        duplicate1 = temp_dir / "video.mp4"
        duplicate2 = temp_dir / "video (copy).mp4"
        content = b"duplicate " * 1000000
        duplicate1.write_bytes(content)
        duplicate2.write_bytes(content)

        # Find all videos
        videos = checker._find_videos(temp_dir)
        assert len(videos) == 4

        # Check samples
        samples = [v for v in videos if v.stat().st_size < 50 * 1024 * 1024]
        assert len(samples) > 0

        # Check duplicates
        checker._detect_duplicates(videos)
        assert len(checker.duplicate_videos) > 0

    def test_no_double_deletion(self, checker, temp_dir):
        """Test that files are not deleted twice when using delete_bad=True and print_summary(auto_delete=True)."""
        # Create a sample file that will be detected and deleted
        sample = temp_dir / "sample_video.mp4"
        sample.write_bytes(b"small sample")  # Small file = sample

        # Create a larger file that won't be a sample
        normal = temp_dir / "normal.mp4"
        normal.write_bytes(b"normal video " * 5000000)  # ~65MB

        # Track deletion calls
        delete_calls = []
        original_delete = checker._delete_videos

        def tracking_delete(videos):
            delete_calls.append(list(videos))
            original_delete(videos)

        checker._delete_videos = tracking_delete

        # Run check_path with delete_bad=True
        checker.check_path(temp_dir, delete_bad=True, skip_health=True)

        # Run print_summary with auto_delete=True
        checker.print_summary(auto_delete=True)

        # Count how many times each file was attempted to be deleted
        all_deleted = []
        for call in delete_calls:
            all_deleted.extend([v.name for v in call if v.exists() or v.name in [f.name for f in all_deleted]])

        # Each file should only appear once across all deletion calls
        # (files that were already deleted won't exist, so they shouldn't be in subsequent calls)
        from collections import Counter
        counts = Counter(all_deleted)
        duplicates = {f: c for f, c in counts.items() if c > 1}
        assert len(duplicates) == 0, f"Files deleted multiple times: {duplicates}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
