"""
Test suite for file_handler module.

Tests cover:
- Filename sanitization (forbidden chars, Unicode, reserved names)
- Video file detection and searching
- Folder cleanup and removal logic
- Image collection detection
- File classification (video, removable, unwanted)
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.file_handler import FileHandler
from core.config import Config


class TestFilenameSanitization:
    """Tests for filename sanitization functionality."""

    @pytest.fixture
    def handler(self):
        """Create FileHandler instance."""
        config = Config()
        return FileHandler(config)

    def test_sanitize_forbidden_windows_chars(self, handler):
        """Test replacement of Windows forbidden characters."""
        test_cases = [
            ('file<name>.mp4', 'file(name).mp4'),
            ('file>name.mp4', 'file)name.mp4'),
            ('file:name.mp4', 'file-name.mp4'),
            ('file"name.mp4', "file'name.mp4"),
            # Note: / and \ are path separators, so Path() splits them
            # 'file/name.mp4' becomes 'name.mp4' (only filename after split)
            ('file|name.mp4', 'file-name.mp4'),
            ('file?name.mp4', 'filename.mp4'),
            ('file*name.mp4', 'filename.mp4'),
        ]

        for input_name, expected in test_cases:
            result = handler.sanitize_filename(input_name)
            assert result == expected, f"Failed for {input_name}: got {result}, expected {expected}"

    def test_sanitize_misnamed_video_extensions(self, handler):
        """Test fixing misnamed video files like .mp4.1, .mkv.bak."""
        test_cases = [
            ('video.mp4.1', 'video.mp4'),
            ('video.mkv.bak', 'video.mkv'),
            ('video.avi.tmp', 'video.avi'),
            ('movie.MP4.001', 'movie.mp4'),  # Case insensitive
        ]

        for input_name, expected in test_cases:
            result = handler.sanitize_filename(input_name)
            assert result == expected, f"Failed for {input_name}: got {result}"

    def test_sanitize_unicode_transliteration(self, handler):
        """Test transliteration of Unicode characters to ASCII."""
        test_cases = [
            ('файл.mp4', 'fayl.mp4'),  # Cyrillic
            ('café.mp4', 'cafe.mp4'),  # Accented
            ('naïve.mp4', 'naive.mp4'),
            ('Москва.mp4', 'Moskva.mp4'),  # Russian city name
        ]

        for input_name, expected in test_cases:
            result = handler.sanitize_filename(input_name)
            assert result == expected, f"Failed for {input_name}: got {result}"

    def test_sanitize_reserved_windows_names(self, handler):
        """Test handling of Windows reserved names."""
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1']

        for reserved in reserved_names:
            result = handler.sanitize_filename(f'{reserved}.mp4')
            assert result == f'{reserved}_.mp4', f"Failed for reserved name {reserved}"

    def test_sanitize_multiple_separators(self, handler):
        """Test normalization of multiple dots, dashes, spaces."""
        test_cases = [
            ('file..name.mp4', 'file.name.mp4'),
            ('file--name.mp4', 'file-name.mp4'),
            ('file__name.mp4', 'file_name.mp4'),
            ('file  name.mp4', 'file name.mp4'),
        ]

        for input_name, expected in test_cases:
            result = handler.sanitize_filename(input_name)
            assert result == expected

    def test_sanitize_leading_trailing_chars(self, handler):
        """Test removal of leading/trailing problematic characters."""
        test_cases = [
            ('.file.mp4', 'file.mp4'),
            ('file_.mp4', 'file.mp4'),
            ('_file.mp4', 'file.mp4'),
            (' file .mp4', 'file.mp4'),
            ('..file...mp4', 'file.mp4'),
        ]

        for input_name, expected in test_cases:
            result = handler.sanitize_filename(input_name)
            assert result == expected

    def test_sanitize_empty_name_fallback(self, handler):
        """Test that empty names after sanitization get timestamp fallback."""
        result = handler.sanitize_filename('?.mp4')  # All chars removed
        assert result.startswith('file_')
        assert result.endswith('.mp4')

    def test_sanitize_length_limit(self, handler):
        """Test filename length limiting."""
        long_name = 'a' * 250 + '.mp4'
        result = handler.sanitize_filename(long_name)
        assert len(result) <= 204  # 200 chars + '.mp4'


class TestVideoFileDetection:
    """Tests for video file detection and searching."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def handler(self):
        """Create FileHandler instance."""
        config = Config()
        return FileHandler(config)

    def test_find_video_files_basic(self, handler, temp_dir):
        """Test finding video files in a directory."""
        # Create test videos
        (temp_dir / "video1.mp4").write_text("test")
        (temp_dir / "video2.mkv").write_text("test")
        (temp_dir / "video3.avi").write_text("test")
        (temp_dir / "not_video.txt").write_text("test")

        videos = handler.find_video_files(temp_dir)

        assert len(videos) == 3
        assert all(v.suffix in ['.mp4', '.mkv', '.avi'] for v in videos)

    def test_find_video_files_non_recursive(self, handler, temp_dir):
        """Test that find_video_files doesn't recurse into subdirectories."""
        # Create video in subdirectory
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "video.mp4").write_text("test")
        (temp_dir / "video.mp4").write_text("test")

        videos = handler.find_video_files(temp_dir)

        # Should only find video in root, not in subdir
        assert len(videos) == 1
        assert videos[0].parent == temp_dir

    def test_find_video_files_empty_directory(self, handler, temp_dir):
        """Test finding videos in empty directory."""
        videos = handler.find_video_files(temp_dir)
        assert videos == []

    def test_find_video_files_nonexistent_path(self, handler):
        """Test handling of nonexistent path."""
        fake_path = Path("C:/nonexistent/path")
        videos = handler.find_video_files(fake_path)
        assert videos == []

    def test_find_video_files_case_insensitive(self, handler, temp_dir):
        """Test case-insensitive extension matching."""
        (temp_dir / "video.MP4").write_text("test")
        (temp_dir / "video.MKV").write_text("test")

        videos = handler.find_video_files(temp_dir)
        assert len(videos) == 2


class TestFolderCleanup:
    """Tests for folder cleanup and removal logic."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def handler(self):
        """Create FileHandler instance."""
        config = Config()
        return FileHandler(config)

    def test_is_folder_empty(self, handler, temp_dir):
        """Test detection of empty folder."""
        assert handler.is_folder_empty_or_removable(temp_dir)

    def test_is_folder_removable_only_junk(self, handler, temp_dir):
        """Test folder with only removable junk files."""
        (temp_dir / "file.nfo").write_text("test")
        (temp_dir / "file.txt").write_text("test")
        (temp_dir / "file.jpg").write_text("test")  # Single image

        assert handler.is_folder_empty_or_removable(temp_dir)

    def test_folder_not_removable_has_video(self, handler, temp_dir):
        """Test folder with video file is not removable."""
        (temp_dir / "video.mp4").write_text("test")
        (temp_dir / "file.nfo").write_text("test")

        assert not handler.is_folder_empty_or_removable(temp_dir)

    def test_folder_not_removable_image_collection(self, handler, temp_dir):
        """Test folder with image collection is not removable."""
        # Create 11 images (more than min threshold) totaling >10MB
        for i in range(11):
            img = temp_dir / f"image{i}.jpg"
            img.write_bytes(b"x" * (1024 * 1024))  # 1MB each

        assert not handler.is_folder_empty_or_removable(temp_dir)

    def test_folder_removable_few_images(self, handler, temp_dir):
        """Test folder with few small images (cover art) is removable."""
        # Create 3 small images (likely cover art, not collection)
        for i in range(3):
            img = temp_dir / f"cover{i}.jpg"
            img.write_bytes(b"x" * (100 * 1024))  # 100KB each

        assert handler.is_folder_empty_or_removable(temp_dir)

    def test_folder_removable_incomplete_rar(self, handler, temp_dir):
        """Test folder with incomplete RAR parts is removable after error."""
        (temp_dir / "file.part001.rar").write_text("test")
        (temp_dir / "file.part002.rar.1").write_text("test")

        # The logic treats .rar.1 (incomplete part) as removable by default
        # because '.rar.' in filename triggers removable condition
        # This is correct behavior - incomplete parts are junk
        assert handler.is_folder_empty_or_removable(temp_dir)

        # With archive_error flag, also removable
        assert handler.is_folder_empty_or_removable(temp_dir, archive_error=True)

    def test_folder_removable_par2_error(self, handler, temp_dir):
        """Test PAR2 files treated as removable after PAR2 error."""
        (temp_dir / "file.par2").write_text("test")
        (temp_dir / "file.vol01.par2").write_text("test")

        # Without error flag, PAR2 files protect folder
        assert not handler.is_folder_empty_or_removable(temp_dir)

        # With par2_error flag, should be removable
        assert handler.is_folder_empty_or_removable(temp_dir, par2_error=True)

    def test_folder_removable_recursive_subdirs(self, handler, temp_dir):
        """Test recursive checking of subdirectories."""
        # Create nested structure with only junk
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "file.nfo").write_text("test")
        (temp_dir / "file.txt").write_text("test")

        # All junk, should be removable
        assert handler.is_folder_empty_or_removable(temp_dir)

    def test_folder_not_removable_nested_video(self, handler, temp_dir):
        """Test folder not removable if subdirectory has video."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "video.mp4").write_text("test")
        (temp_dir / "file.nfo").write_text("test")

        # Has video in subdir, not removable
        assert not handler.is_folder_empty_or_removable(temp_dir)


class TestFileClassification:
    """Tests for file type classification."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def handler(self):
        """Create FileHandler instance."""
        config = Config()
        return FileHandler(config)

    def test_contains_non_video_files(self, handler, temp_dir):
        """Test detection of non-video files in folder."""
        (temp_dir / "video.mp4").write_text("test")
        (temp_dir / "doc.pdf").write_text("test")

        assert handler.contains_non_video_files(temp_dir)

    def test_contains_only_videos(self, handler, temp_dir):
        """Test folder with only videos."""
        (temp_dir / "video1.mp4").write_text("test")
        (temp_dir / "video2.mkv").write_text("test")

        assert not handler.contains_non_video_files(temp_dir)

    def test_contains_unwanted_files(self, handler, temp_dir):
        """Test detection of unwanted files (not video/par2/rar)."""
        (temp_dir / "video.mp4").write_text("test")
        (temp_dir / "file.nfo").write_text("test")

        assert handler.contains_unwanted_files(temp_dir)

    def test_contains_only_wanted_files(self, handler, temp_dir):
        """Test folder with only wanted files (video/par2/rar)."""
        (temp_dir / "video.mp4").write_text("test")
        (temp_dir / "video.par2").write_text("test")
        (temp_dir / "archive.rar").write_text("test")

        assert not handler.contains_unwanted_files(temp_dir)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def handler(self):
        """Create FileHandler instance."""
        config = Config()
        return FileHandler(config)

    def test_init_with_none_config(self):
        """Test that initialization with None config raises error."""
        from utils.defensive import ValidationError
        with pytest.raises(ValidationError):
            FileHandler(None)

    def test_init_with_invalid_config(self):
        """Test that initialization with invalid config raises error."""
        from utils.defensive import ValidationError
        config = Mock(spec=[])  # Mock with no attributes
        # Config missing required attributes (video_extensions, removable_extensions)
        with pytest.raises(ValidationError, match="missing required attribute"):
            FileHandler(config)

    def test_sanitize_control_characters(self, handler):
        """Test removal of control characters from filenames."""
        filename = "file\x00name\x01.mp4"  # Null and SOH control chars
        result = handler.sanitize_filename(filename)
        assert '\x00' not in result
        assert '\x01' not in result

    def test_sanitize_very_long_unicode_name(self, handler):
        """Test handling of very long Unicode filename."""
        long_unicode = 'фи' * 150 + '.mp4'  # Cyrillic chars
        result = handler.sanitize_filename(long_unicode)
        # Should be transliterated and length-limited
        assert len(result) <= 204
        assert result.endswith('.mp4')

    def test_find_videos_with_permission_error(self, handler):
        """Test graceful handling of permission errors."""
        # Mock path that raises PermissionError
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = True
        mock_path.iterdir.side_effect = PermissionError("Access denied")

        videos = handler.find_video_files(mock_path)
        # Should return empty list, not crash
        assert videos == []

    def test_contains_non_video_files_with_scan_error(self, handler):
        """Unreadable trees should fail-safe as non-video content present."""
        mock_path = Mock(spec=Path)
        mock_path.rglob.side_effect = OSError("Access denied")
        assert handler.contains_non_video_files(mock_path)

    def test_contains_unwanted_files_with_scan_error(self, handler):
        """Unreadable trees should fail-safe as unwanted content present."""
        mock_path = Mock(spec=Path)
        mock_path.rglob.side_effect = OSError("Access denied")
        assert handler.contains_unwanted_files(mock_path)

    def test_is_folder_empty_or_removable_with_scan_error(self, handler):
        """Unreadable folders should never be treated as removable."""
        mock_path = Mock(spec=Path)
        mock_path.iterdir.side_effect = OSError("Access denied")
        assert not handler.is_folder_empty_or_removable(mock_path)


class TestStatsTracking:
    """Tests for optional stats tracking."""

    @pytest.fixture
    def handler_with_stats(self):
        """Create FileHandler with stats tracking."""
        config = Config()
        stats = {'sanitized': 0}
        return FileHandler(config, stats=stats)

    def test_stats_tracking_optional(self, handler_with_stats):
        """Test that stats tracking is optional and works when provided."""
        # Stats object is passed and accessible
        assert handler_with_stats.stats is not None
        assert 'sanitized' in handler_with_stats.stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
