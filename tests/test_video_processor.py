"""
Test suite for video_processor module.

Tests cover:
- Video health checking (corruption, truncation)
- Metadata parsing (duration, bitrate, resolution)
- Quality checking (resolution, bitrate)
- Sample file detection
- Error handling (missing ffmpeg, corrupted files)
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video_processor import VideoProcessor
from core.config import Config


class TestVideoHealthBasics:
    """Tests for basic video health checking."""

    @pytest.fixture
    def processor(self):
        """Create VideoProcessor instance."""
        config = Config()
        return VideoProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    def test_file_too_small(self, processor, temp_dir):
        """Test rejection of very small files (<1MB)."""
        tiny_file = temp_dir / "tiny.mp4"
        tiny_file.write_bytes(b"x" * 100)  # 100 bytes

        result = processor.check_video_health(tiny_file)
        assert result is False

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_healthy_video(self, mock_subprocess, processor, temp_dir):
        """Test successful health check for healthy video."""
        video = temp_dir / "healthy.mp4"
        # Expected size: 2500 kb/s * 630s / 8 / 1024 = ~192MB
        video.write_bytes(b"x" * (200 * 1024 * 1024))  # 200MB matches expectations

        # Mock metadata check
        metadata_stderr = """
        Duration: 00:10:30.50, start: 0.000000, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080, 24 fps
        """
        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),  # Metadata check (ffmpeg returns 1 for -i without output)
            (True, '', '', 0)  # Decode test
        ]

        result = processor.check_video_health(video)
        assert result is True

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_missing_duration(self, mock_subprocess, processor, temp_dir):
        """Test rejection of video with missing/invalid duration."""
        video = temp_dir / "no_duration.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        # Mock metadata with missing duration
        metadata_stderr = "Stream #0:0: Video: h264"
        mock_subprocess.return_value = (True, '', metadata_stderr, 1)

        result = processor.check_video_health(video)
        assert result is False

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_truncated_video(self, mock_subprocess, processor, temp_dir):
        """Test detection of truncated video (size too small for duration/bitrate)."""
        video = temp_dir / "truncated.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))  # 10MB actual

        # Mock metadata indicating file should be much larger
        metadata_stderr = """
        Duration: 01:00:00.00, bitrate: 5000 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """
        # Expected size: 5000 kb/s * 3600s / 8 / 1024 = ~2197 MB
        # Actual: 10 MB (ratio ~0.005, much less than 0.70 threshold)

        mock_subprocess.return_value = (True, '', metadata_stderr, 1)

        result = processor.check_video_health(video)
        assert result is False

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_corrupted_video(self, mock_subprocess, processor, temp_dir):
        """Test detection of corrupted video with decode errors."""
        video = temp_dir / "corrupt.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        decode_stderr = "Error while decoding stream #0:0: Invalid data found"

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),  # Metadata OK
            (True, '', decode_stderr, 0)  # Decode has errors
        ]

        result = processor.check_video_health(video)
        assert result is False

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_decode_timeout(self, mock_subprocess, processor, temp_dir):
        """Test handling of decode timeout."""
        video = temp_dir / "timeout.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),  # Metadata OK
            (False, '', 'Timeout', -1)  # Decode timeout
        ]

        result = processor.check_video_health(video)
        assert result is False


class TestQualityChecking:
    """Tests for video quality checking."""

    @pytest.fixture
    def processor(self):
        """Create VideoProcessor instance."""
        config = Config()
        return VideoProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_low_resolution_detected(self, mock_subprocess, processor, temp_dir):
        """Test detection of low resolution video."""
        video = temp_dir / "low_res.mp4"
        # Expected: 2500 kb/s * 600s / 8 / 1024 = ~183MB
        video.write_bytes(b"x" * (190 * 1024 * 1024))

        # 480p or lower is considered low quality
        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 640x480
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),  # Metadata
            (True, '', '', 0)  # Decode OK
        ]

        is_healthy, is_low_quality, reason, resolution = processor.check_video_health(video, check_quality=True)

        assert is_healthy is True
        assert is_low_quality is True
        assert "Low resolution" in reason
        assert resolution == (640, 480)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_low_bitrate_detected(self, mock_subprocess, processor, temp_dir):
        """Test detection of low bitrate video."""
        video = temp_dir / "low_bitrate.mp4"
        # Expected: 500 kb/s * 600s / 8 / 1024 = ~37MB
        video.write_bytes(b"x" * (40 * 1024 * 1024))

        # Very low bitrate for any video
        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', '', 0)
        ]

        is_healthy, is_low_quality, reason, resolution = processor.check_video_health(video, check_quality=True)

        assert is_healthy is True
        assert is_low_quality is True
        assert "Low bitrate" in reason

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_low_bitrate_for_1080p(self, mock_subprocess, processor, temp_dir):
        """Test detection of insufficient bitrate for 1080p."""
        video = temp_dir / "1080p_low_bitrate.mp4"
        # Expected: 2000 kb/s * 600s / 8 / 1024 = ~147MB
        video.write_bytes(b"x" * (150 * 1024 * 1024))

        # 1080p with low bitrate (<3000 kb/s)
        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2000 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', '', 0)
        ]

        is_healthy, is_low_quality, reason, resolution = processor.check_video_health(video, check_quality=True)

        assert is_healthy is True
        assert is_low_quality is True
        assert "1080p" in reason

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_high_quality_video(self, mock_subprocess, processor, temp_dir):
        """Test high quality video not flagged as low quality."""
        video = temp_dir / "hq.mp4"
        # Expected: 5000 kb/s * 600s / 8 / 1024 = ~367MB
        video.write_bytes(b"x" * (370 * 1024 * 1024))

        # 1080p with appropriate bitrate
        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 5000 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', '', 0)
        ]

        is_healthy, is_low_quality, reason, resolution = processor.check_video_health(video, check_quality=True)

        assert is_healthy is True
        assert is_low_quality is False
        assert reason is None


class TestMetadataParsing:
    """Tests for metadata parsing from ffmpeg output."""

    @pytest.fixture
    def processor(self):
        """Create VideoProcessor instance."""
        config = Config()
        return VideoProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_parse_duration(self, mock_subprocess, processor, temp_dir):
        """Test parsing duration from ffmpeg output."""
        video = temp_dir / "video.mp4"
        # Expected: 2500 kb/s * 5025.67s / 8 / 1024 = ~1533MB
        # Create smaller file to save memory - the validation threshold is 0.70
        # So we need at least 70% of expected: 1533 * 0.7 = 1073MB
        video.write_bytes(b"x" * (1100 * 1024 * 1024))  # 1.1GB

        metadata_stderr = """
        Duration: 01:23:45.67, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', '', 0)
        ]

        # Duration should be parsed as: 1h * 3600 + 23m * 60 + 45.67s = 5025.67s
        result = processor.check_video_health(video)
        assert result is True

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_parse_resolution(self, mock_subprocess, processor, temp_dir):
        """Test parsing resolution from ffmpeg output."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 3840x2160, 30 fps
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', '', 0)
        ]

        is_healthy, is_low_quality, reason, resolution = processor.check_video_health(video, check_quality=True)

        assert resolution == (3840, 2160)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_parse_bitrate(self, mock_subprocess, processor, temp_dir):
        """Test parsing bitrate from ffmpeg output."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (1000 * 1024 * 1024))  # 1GB for high bitrate 4K video

        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 15000 kb/s
        Stream #0:0: Video: h264, yuv420p, 3840x2160
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', '', 0)
        ]

        # Bitrate parsing is verified indirectly through size validation
        result = processor.check_video_health(video)
        assert result is True


class TestSampleDetection:
    """Tests for sample file detection."""

    @pytest.fixture
    def processor(self):
        """Create VideoProcessor instance."""
        config = Config()
        return VideoProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    def test_sample_by_filename(self, processor, temp_dir):
        """Test detection of sample files by 'sample' in filename."""
        sample = temp_dir / "movie-sample.mp4"
        sample.write_bytes(b"x" * (100 * 1024 * 1024))  # Large, but named 'sample'

        assert processor.is_sample_file(sample) is True

    def test_sample_by_size(self, processor, temp_dir):
        """Test detection of sample files by small size (<50MB)."""
        small = temp_dir / "small_video.mp4"
        small.write_bytes(b"x" * (10 * 1024 * 1024))  # 10MB

        assert processor.is_sample_file(small) is True

    def test_not_sample_large_file(self, processor, temp_dir):
        """Test that large files are not detected as samples."""
        large = temp_dir / "full_movie.mp4"
        large.write_bytes(b"x" * (100 * 1024 * 1024))  # 100MB

        assert processor.is_sample_file(large) is False

    def test_sample_custom_threshold(self, processor, temp_dir):
        """Test sample detection with custom size threshold."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (70 * 1024 * 1024))  # 70MB

        # Default threshold (50MB) - not a sample
        assert processor.is_sample_file(video) is False

        # Custom threshold (100MB) - is a sample
        assert processor.is_sample_file(video, min_size_mb=100) is True

    def test_nonexistent_file(self, processor, temp_dir):
        """Test handling of nonexistent file."""
        fake_file = temp_dir / "nonexistent.mp4"

        assert processor.is_sample_file(fake_file) is False


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.fixture
    def processor(self):
        """Create VideoProcessor instance."""
        config = Config()
        return VideoProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_ffmpeg_not_installed(self, mock_subprocess, processor, temp_dir):
        """Test graceful handling when ffmpeg not installed."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        mock_subprocess.side_effect = FileNotFoundError("ffmpeg not found")

        # Should assume healthy if can't check
        result = processor.check_video_health(video)
        assert result is True

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_unexpected_exception(self, mock_subprocess, processor, temp_dir):
        """Test handling of unexpected exceptions."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        mock_subprocess.side_effect = Exception("Unexpected error")

        result = processor.check_video_health(video)
        assert result is False

    def test_file_stat_error(self, processor, temp_dir):
        """Test handling of file stat errors."""
        video = temp_dir / "video.mp4"

        # Create file then make it inaccessible by mocking stat
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        with patch.object(Path, 'stat', side_effect=OSError("Access denied")):
            # Should raise exception or handle gracefully
            with pytest.raises(Exception):
                processor.check_video_health(video)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_malformed_metadata(self, mock_subprocess, processor, temp_dir):
        """Test handling of malformed ffmpeg metadata output."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        # Malformed metadata (corrupted format)
        metadata_stderr = "Some random text without proper format"

        mock_subprocess.return_value = (True, '', metadata_stderr, 1)

        # Should fail due to missing duration
        result = processor.check_video_health(video)
        assert result is False


class TestCorruptionKeywords:
    """Tests for corruption keyword detection."""

    @pytest.fixture
    def processor(self):
        """Create VideoProcessor instance."""
        config = Config()
        return VideoProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_detect_invalid_data(self, mock_subprocess, processor, temp_dir):
        """Test detection of 'Invalid data' keyword."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', "Invalid data found when processing input", 0)
        ]

        result = processor.check_video_health(video)
        assert result is False

    @patch('core.video_processor.SubprocessSafety.run_with_timeout')
    def test_detect_moov_atom_missing(self, mock_subprocess, processor, temp_dir):
        """Test detection of 'moov atom not found' error."""
        video = temp_dir / "video.mp4"
        video.write_bytes(b"x" * (10 * 1024 * 1024))

        metadata_stderr = """
        Duration: 00:10:00.00, bitrate: 2500 kb/s
        Stream #0:0: Video: h264, yuv420p, 1920x1080
        """

        mock_subprocess.side_effect = [
            (True, '', metadata_stderr, 1),
            (True, '', "moov atom not found", 0)
        ]

        result = processor.check_video_health(video)
        assert result is False


class TestConfigIntegration:
    """Tests for config integration."""

    def test_init_with_none_config(self):
        """Test processor works with None config (uses defaults)."""
        processor = VideoProcessor(config=None)
        assert processor.config is not None

    def test_init_with_custom_config(self):
        """Test processor accepts custom config."""
        config = Config()
        processor = VideoProcessor(config=config)
        assert processor.config == config


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
