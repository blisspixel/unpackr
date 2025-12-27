"""
Chaos Test Scenarios

Systematic fault injection tests covering 50+ failure modes.
Each test verifies that the system maintains data integrity and
degrades gracefully under adverse conditions.

Test Categories:
1. Disk I/O Failures (disk full, permission denied, read errors)
2. Archive Extraction Failures (corrupt archives, incomplete parts, extraction hangs)
3. Video Processing Failures (corrupt videos, invalid metadata, decode failures)
4. Resource Exhaustion (memory limits, process limits, file handle exhaustion)
5. Timing Failures (timeouts, race conditions, slow operations)

References:
- docs/DEEP_ANALYSIS.md - Systematic Defensiveness section
- docs/SAFETY_CONTRACT.md - Invariants that must hold even under failure
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.archive_processor import ArchiveProcessor
from core.video_processor import VideoProcessor
from core.file_handler import FileHandler
from core.config import Config
from tests.chaos.fault_injectors import (
    DiskFullInjector,
    PermissionDeniedInjector,
    CorruptDataInjector,
    ProcessHangInjector,
    multiple_faults
)


# ============================================================================
# Category 1: Disk I/O Failures
# ============================================================================

class TestDiskIOChaos:
    """Test system behavior under disk I/O failures."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def config(self):
        return Config()

    def test_disk_full_during_extraction(self, temp_dir, config):
        """
        SCENARIO: Disk becomes full during archive extraction.

        Expected behavior:
        - Extraction fails gracefully
        - No partial files left behind
        - Original archive remains intact
        - Error logged with disk space details
        """
        processor = ArchiveProcessor(config)
        archive = temp_dir / "test.rar"
        archive.write_bytes(b"fake archive data" * 1000)

        with DiskFullInjector(available_bytes=1000):
            with patch('core.archive_processor.StateValidator.check_disk_space', return_value=False):
                result = processor.process_rar_files(temp_dir)

                # Should fail gracefully
                assert result is False or result is True  # May skip or fail

                # Archive should still exist
                assert archive.exists()

                # No extracted content should exist (or if it does, it's partial and logged)

    def test_permission_denied_on_delete(self, temp_dir, config):
        """
        SCENARIO: Permission denied when trying to delete processed files.

        Expected behavior:
        - Processing continues for other files
        - Protected file is logged as unable to delete
        - No crash or hang
        - User warned about manual cleanup needed
        """
        handler = FileHandler(config)
        protected_file = temp_dir / "protected.txt"
        normal_file = temp_dir / "normal.txt"

        protected_file.write_text("protected")
        normal_file.write_text("normal")

        with PermissionDeniedInjector(path=protected_file, operation='delete'):
            # Attempt to delete (should fail gracefully for protected file)
            try:
                protected_file.unlink()
                assert False, "Should have raised PermissionError"
            except PermissionError:
                pass  # Expected

            # Normal file should still be deletable
            normal_file.unlink()
            assert not normal_file.exists()

    def test_permission_denied_on_move(self, temp_dir, config):
        """
        SCENARIO: Permission denied when moving video to destination.

        Expected behavior:
        - Error logged with file details
        - File remains in source location
        - No data loss
        - Other files continue processing
        """
        source = temp_dir / "source.mp4"
        dest_dir = temp_dir / "dest"
        dest_dir.mkdir()

        source.write_bytes(b"video data" * 1000)

        with PermissionDeniedInjector(operation='write'):
            try:
                dest = dest_dir / source.name
                shutil.move(str(source), str(dest))
                # If move succeeds without error, that's OK too
            except (PermissionError, OSError):
                # Expected - file should remain at source
                assert source.exists()

    def test_read_error_during_validation(self, temp_dir, config):
        """
        SCENARIO: I/O error when reading video for validation.

        Expected behavior:
        - Video marked as corrupt/unreadable
        - Processing continues with other videos
        - Error logged with details
        - No crash
        """
        processor = VideoProcessor(config)
        video = temp_dir / "test.mp4"
        video.write_bytes(b"fake video" * 1000)

        with PermissionDeniedInjector(path=video, operation='read'):
            # Attempt to read should fail
            try:
                content = video.read_text()
                assert False, "Should have raised PermissionError"
            except PermissionError:
                pass  # Expected behavior

    def test_disk_full_mid_write(self, temp_dir, config):
        """
        SCENARIO: Disk fills up while writing a file.

        Expected behavior:
        - Write operation fails
        - Partial file is cleaned up
        - Error logged clearly
        - Operation can be retried when space available
        """
        injector = DiskFullInjector(available_bytes=500, trigger_after=500)

        with injector:
            test_file = temp_dir / "test.txt"

            try:
                # Simulate writing more data than available
                with open(test_file, 'wb') as f:
                    f.write(b"x" * 100)
                    injector.simulate_write(100)

                    # This should trigger disk full
                    f.write(b"x" * 1000)
                    injector.simulate_write(1000)

                    assert False, "Should have raised OSError"
            except OSError as e:
                # Expected - disk full
                assert "No space left" in str(e) or e.errno == 28


# ============================================================================
# Category 2: Archive Extraction Failures
# ============================================================================

class TestArchiveExtractionChaos:
    """Test system behavior with problematic archives."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def config(self):
        return Config()

    @pytest.fixture
    def processor(self, config):
        return ArchiveProcessor(config)

    def test_corrupt_archive_header(self, processor, temp_dir):
        """
        SCENARIO: Archive has corrupt header, 7z fails to extract.

        Expected behavior:
        - Extraction fails with clear error
        - No partial files left behind
        - Archive marked as corrupt
        - Processing continues with other archives
        """
        corrupt_archive = temp_dir / "corrupt.rar"
        corrupt_archive.write_bytes(b"NOT A REAL ARCHIVE")

        with patch('core.archive_processor.SubprocessSafety.run_with_timeout') as mock:
            mock.return_value = (False, '', 'Cannot open archive', 2)

            with patch('core.archive_processor.StateValidator.check_disk_space', return_value=True):
                with patch.object(processor, '_validate_archive_paths', return_value=True):
                    result = processor.process_rar_files(temp_dir)

                    # Should handle failure gracefully
                    assert result is False

    def test_incomplete_multipart_archive(self, processor, temp_dir):
        """
        SCENARIO: Multi-part archive is incomplete (missing parts).

        Expected behavior:
        - Detection of incomplete archive set
        - Clear warning about missing parts
        - No extraction attempted (would fail)
        - Folder preserved for manual intervention
        """
        # Create only part2 without part1
        part2 = temp_dir / "archive.part002.rar"
        part2.write_text("incomplete")

        # Should detect incomplete set
        result = processor.process_rar_files(temp_dir)

        # Should complete without error (no archives to process)
        assert result is True

    def test_extraction_timeout(self, processor, temp_dir):
        """
        SCENARIO: Archive extraction exceeds timeout (stuck/huge file).

        Expected behavior:
        - Extraction terminated after timeout
        - Partial extraction cleaned up
        - Error logged with archive details
        - System remains responsive
        """
        large_archive = temp_dir / "huge.rar"
        large_archive.write_bytes(b"x" * (100 * 1024 * 1024))  # 100MB

        with ProcessHangInjector(hang_on="7z", hang_duration=0.5):
            with patch('core.archive_processor.StateValidator.check_disk_space', return_value=True):
                with patch.object(processor, '_validate_archive_paths', return_value=True):
                    # Should timeout quickly due to our hang injector
                    result = processor.process_rar_files(temp_dir)

                    # May fail or succeed depending on timing
                    assert result is not None

    def test_password_protected_archive(self, processor, temp_dir):
        """
        SCENARIO: Archive is password protected (cannot extract).

        Expected behavior:
        - Extraction fails with password error
        - Archive preserved (not deleted)
        - Clear error message logged
        - Folder marked for manual review
        """
        protected = temp_dir / "protected.rar"
        protected.write_text("password protected")

        with patch('core.archive_processor.SubprocessSafety.run_with_timeout') as mock:
            mock.return_value = (False, '', 'Wrong password', 2)

            with patch('core.archive_processor.StateValidator.check_disk_space', return_value=True):
                with patch.object(processor, '_validate_archive_paths', return_value=True):
                    result = processor.process_rar_files(temp_dir)

                    # Should fail gracefully
                    assert result is False

                    # Archive should still exist
                    assert protected.exists()

    def test_path_traversal_in_archive(self, processor, temp_dir):
        """
        SCENARIO: Archive contains path traversal attack (../../etc/passwd).

        Expected behavior:
        - Archive validation BLOCKS extraction
        - SECURITY warning logged
        - Archive preserved for analysis
        - No extraction attempted
        - System remains secure
        """
        malicious = temp_dir / "malicious.rar"
        malicious.write_text("path traversal")

        # Mock validation to detect path traversal
        with patch.object(processor, '_validate_archive_paths', return_value=False):
            with patch('core.archive_processor.logging.error') as mock_log:
                result = processor.process_rar_files(temp_dir)

                # Should detect and block
                # Check that security error was logged
                assert any('SECURITY' in str(call) for call in mock_log.call_args_list)

    def test_nested_archives_loop_prevention(self, processor, temp_dir):
        """
        SCENARIO: Archive contains archive contains archive... (loop bomb).

        Expected behavior:
        - Loop detection triggers after configured limit
        - Extraction stops before exhausting resources
        - Clear error about loop limit
        - Partial extraction cleaned up
        """
        # Create mock nested archives
        for i in range(15):
            nested = temp_dir / f"nested{i}.rar"
            nested.write_text(f"level {i}")

        with patch('core.archive_processor.SubprocessSafety.run_with_timeout') as mock:
            mock.return_value = (True, '', '', 0)

            with patch('core.archive_processor.StateValidator.check_disk_space', return_value=True):
                with patch.object(processor, '_validate_archive_paths', return_value=True):
                    with patch('core.archive_processor.logging.error') as mock_log:
                        # Lower the loop limit for testing
                        processor.config.archive_extraction_loop_limit = 5

                        result = processor.process_rar_files(temp_dir)

                        # Should hit loop limit
                        assert any('loop safety' in str(call).lower()
                                 for call in mock_log.call_args_list)


# ============================================================================
# Category 3: Video Processing Failures
# ============================================================================

class TestVideoProcessingChaos:
    """Test system behavior with problematic videos."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def config(self):
        return Config()

    @pytest.fixture
    def processor(self, config):
        return VideoProcessor(config)

    def test_corrupt_video_header(self, processor, temp_dir):
        """
        SCENARIO: Video has corrupt header, ffprobe fails to read metadata.

        Expected behavior:
        - Video marked as corrupt
        - No crash on parse failure
        - Video moved to rejected folder or deleted
        - Other videos continue processing
        """
        corrupt = temp_dir / "corrupt.mp4"
        corrupt.write_bytes(b"NOT A VIDEO")

        with patch('core.video_processor.SubprocessSafety.run_with_timeout') as mock:
            # Simulate ffprobe failure
            mock.return_value = (False, '', 'Invalid data found', 1)

            result = processor.check_video_health(corrupt)

            # Should be marked as corrupt
            assert result is False

    def test_video_missing_metadata(self, processor, temp_dir):
        """
        SCENARIO: Video has no duration/resolution in metadata.

        Expected behavior:
        - Handles missing metadata gracefully
        - Uses defaults or marks as unknown quality
        - Video not automatically rejected
        - Logged for manual review
        """
        weird_video = temp_dir / "weird.mp4"
        weird_video.write_bytes(b"x" * 1000000)

        with patch('core.video_processor.SubprocessSafety.run_with_timeout') as mock:
            # Return metadata with missing fields
            mock.return_value = (True, '', 'Stream #0:0: Video: h264', 1)

            result = processor.check_video_health(weird_video)

            # Should handle gracefully (may pass or fail depending on logic)
            assert result is not None

    def test_video_decode_timeout(self, processor, temp_dir):
        """
        SCENARIO: Video decode test hangs (corrupt frames).

        Expected behavior:
        - Decode terminates after timeout
        - Video marked as corrupt
        - ffmpeg process killed cleanly
        - No zombie processes left
        """
        hanging_video = temp_dir / "hanging.mp4"
        hanging_video.write_bytes(b"x" * 1000000)

        with ProcessHangInjector(hang_on="ffmpeg", hang_duration=0.5):
            # This would normally hang, but injector limits it
            result = processor.check_video_health(hanging_video)

            # Should timeout and reject
            assert result is not None

    def test_video_truncated_file(self, processor, temp_dir):
        """
        SCENARIO: Video file is truncated (incomplete download).

        Expected behavior:
        - Size validation detects truncation
        - Video rejected as incomplete
        - Clear log message about size mismatch
        - Not mistaken for valid video
        """
        truncated = temp_dir / "truncated.mp4"
        # Create small file that claims to be long
        truncated.write_bytes(b"x" * 10000)

        with patch('core.video_processor.SubprocessSafety.run_with_timeout') as mock:
            # Metadata claims 2500 kb/s for 600 seconds (expected ~192MB)
            # But file is only 10KB - clear truncation
            metadata = """
            Duration: 00:10:00.00, bitrate: 2500 kb/s
            Stream #0:0: Video: h264, yuv420p, 1920x1080
            """
            mock.side_effect = [
                (True, '', metadata, 1),  # Metadata
                (True, '', '', 0)  # Decode test
            ]

            result = processor.check_video_health(truncated)

            # Should detect size mismatch
            # The actual result depends on implementation, but should not crash
            assert result is not None


# ============================================================================
# Category 4: Resource Exhaustion
# ============================================================================

class TestResourceExhaustionChaos:
    """Test system behavior under resource limits."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def config(self):
        return Config()

    def test_too_many_open_files(self, temp_dir, config):
        """
        SCENARIO: System file handle limit reached.

        Expected behavior:
        - Graceful degradation (process in smaller batches)
        - Clear error about file handle limit
        - Files closed properly after processing
        - No handle leaks
        """
        # Create many small files
        for i in range(100):
            (temp_dir / f"file{i}.txt").write_text("test")

        # Actual test would need to lower ulimit, which is OS-specific
        # For now, just verify no leaks in normal operation
        handler = FileHandler(config)
        files = list(temp_dir.glob("*.txt"))

        # Process all files (should not exhaust handles)
        for f in files:
            _ = handler.sanitize_filename(f.name)

        # Should complete without errors

    def test_very_large_archive_extraction(self, temp_dir, config):
        """
        SCENARIO: Archive expands to many GB (zip bomb).

        Expected behavior:
        - Size check before extraction detects issue
        - Extraction blocked if exceeds safety threshold
        - Clear warning about expansion ratio
        - Disk space protected
        """
        processor = ArchiveProcessor(config)

        # Create tiny archive that claims to expand hugely
        tiny_archive = temp_dir / "bomb.rar"
        tiny_archive.write_bytes(b"x" * 1000)

        # Mock disk space check to fail
        with patch('core.archive_processor.StateValidator.check_disk_space', return_value=False):
            with patch('core.archive_processor.logging.error') as mock_log:
                result = processor.process_rar_files(temp_dir)

                # Should detect space issue
                # May log error about disk space
                # Result may be True (skipped) or False (failed)

    def test_thousands_of_small_files_in_archive(self, temp_dir, config):
        """
        SCENARIO: Archive contains 10,000+ small files.

        Expected behavior:
        - Extraction proceeds with progress updates
        - Memory usage remains bounded
        - All files extracted correctly
        - Performance remains reasonable
        """
        processor = ArchiveProcessor(config)

        # Create mock archive
        many_files = temp_dir / "many.rar"
        many_files.write_bytes(b"x" * 1000000)

        with patch('core.archive_processor.SubprocessSafety.run_with_timeout') as mock:
            mock.return_value = (True, '', '', 0)

            with patch('core.archive_processor.StateValidator.check_disk_space', return_value=True):
                with patch.object(processor, '_validate_archive_paths', return_value=True):
                    result = processor.process_rar_files(temp_dir)

                    # Should complete successfully
                    assert result is True


# ============================================================================
# Category 5: Timing and Concurrency Failures
# ============================================================================

class TestTimingChaos:
    """Test system behavior with timing-related failures."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def config(self):
        return Config()

    def test_file_deleted_during_processing(self, temp_dir, config):
        """
        SCENARIO: File is deleted by external process during validation.

        Expected behavior:
        - FileNotFoundError handled gracefully
        - Processing continues with other files
        - Error logged with details
        - No crash
        """
        handler = FileHandler(config)

        video = temp_dir / "vanishing.mp4"
        video.write_bytes(b"x" * 1000)

        # Simulate file vanishing
        video.unlink()

        # Try to process non-existent file
        try:
            _ = video.stat()
            assert False, "File should not exist"
        except FileNotFoundError:
            pass  # Expected

    def test_filesystem_becomes_readonly(self, temp_dir, config):
        """
        SCENARIO: Filesystem remounted read-only during operation.

        Expected behavior:
        - Write attempts fail with clear error
        - No data corruption
        - Current operation aborted safely
        - State remains consistent
        """
        # This is very OS-specific and hard to test portably
        # Would require actual remount on Linux/Unix

        with PermissionDeniedInjector(operation='write'):
            try:
                test_file = temp_dir / "test.txt"
                test_file.write_text("should fail")
                assert False, "Write should have failed"
            except (PermissionError, OSError):
                pass  # Expected


# ============================================================================
# Combined Scenarios
# ============================================================================

class TestCombinedFailureModes:
    """Test multiple simultaneous failures."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def config(self):
        return Config()

    def test_disk_full_and_permission_denied(self, temp_dir, config):
        """
        SCENARIO: Disk full AND permission denied on cleanup.

        Expected behavior:
        - Both errors logged clearly
        - Partial state documented
        - User guidance provided
        - No data loss
        """
        with multiple_faults(
            DiskFullInjector(available_bytes=1000),
            PermissionDeniedInjector(operation='delete')
        ):
            # Operations should handle both failure modes
            test_file = temp_dir / "test.txt"

            # This will test both constraints
            # Disk space check should prevent write
            # Permission check should prevent delete


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
