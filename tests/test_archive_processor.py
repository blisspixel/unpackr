"""
Test suite for archive_processor module.

Tests cover:
- RAR file extraction (single, multi-part, 7z)
- PAR2 repair and verification
- Archive validation (path traversal detection)
- Timeout handling for large archives
- Safety limits and loop guards
- Cleanup operations
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.archive_processor import ArchiveProcessor
from core.config import Config


class TestArchiveDetection:
    """Tests for archive file detection and filtering."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        processor = ArchiveProcessor(config)
        processor.system_check.get_tool_command = Mock(return_value=[r"C:\Program Files\7-Zip\7z.exe"])
        return processor

    def test_finds_rar_files(self, processor, temp_dir):
        """Test detection of RAR files in directory."""
        (temp_dir / "archive.rar").write_text("test")
        (temp_dir / "archive.part001.rar").write_text("test")
        (temp_dir / "not_archive.txt").write_text("test")

        # Processor should find RAR files
        # Note: This tests the glob logic indirectly through process_rar_files
        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch("core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(True, "", "", 0)):
                result = processor.process_rar_files(temp_dir)
                assert result is True

    def test_skips_higher_rar_parts(self, processor, temp_dir):
        """Test that .part002+ RAR files are skipped (only part001 extracted)."""
        (temp_dir / "archive.part001.rar").write_text("test")
        (temp_dir / "archive.part002.rar").write_text("test")
        (temp_dir / "archive.part003.rar").write_text("test")

        # Only part001 should be processed
        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch(
                "core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(True, "", "", 0)
            ) as mock_run:
                processor.process_rar_files(temp_dir)
                # Should only call 7z once (for part001)
                assert mock_run.call_count == 1

    def test_finds_7z_files(self, processor, temp_dir):
        """Test detection of 7z archive files."""
        (temp_dir / "archive.7z").write_text("test")
        (temp_dir / "archive2.7z.001").write_text("test")

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch(
                "core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(True, "", "", 0)
            ) as mock_run:
                processor.process_rar_files(temp_dir)
                # Should process both 7z files
                assert mock_run.call_count == 2

    def test_warns_incomplete_7z_archive(self, processor, temp_dir):
        """Test warning for incomplete 7z archives (e.g., .7z.100 without .7z.001)."""
        # Create only .7z.100 without .7z.001 (incomplete download)
        (temp_dir / "archive.7z.100").write_text("test")

        with patch("core.archive_processor.logging.warning") as mock_warn:
            with patch.object(processor, "_validate_archive_paths", return_value=True):
                with patch("core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(True, "", "", 0)):
                    processor.process_rar_files(temp_dir)
                    # Should log warning about incomplete archive
                    assert any("Incomplete 7z archive" in str(call) for call in mock_warn.call_args_list)

    def test_no_archives_returns_true(self, processor, temp_dir):
        """Test that folders with no archives return success."""
        (temp_dir / "video.mp4").write_text("test")
        (temp_dir / "readme.txt").write_text("test")

        result = processor.process_rar_files(temp_dir)
        assert result is True


class TestExtractionProcess:
    """Tests for archive extraction process."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        processor = ArchiveProcessor(config)
        processor.system_check.get_tool_command = Mock(return_value=[r"C:\Program Files\7-Zip\7z.exe"])
        return processor

    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_extraction_fails_closed_when_no_safe_7z_command(self, mock_disk_space, processor, temp_dir):
        """Test extraction aborts if no safe 7-Zip command resolves."""
        (temp_dir / "archive.rar").write_bytes(b"fake rar data" * 1000)
        processor.system_check.get_tool_command = Mock(return_value=[])
        mock_disk_space.return_value = True

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch("core.archive_processor.SubprocessSafety.run_with_timeout") as mock_run:
                result = processor.process_rar_files(temp_dir)

        assert result is False
        assert not mock_run.called

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_extraction_uses_temp_files_for_large_7z_output(
        self, mock_disk_space, mock_subprocess, processor, temp_dir
    ):
        """Extraction should avoid PIPE buffering for potentially huge 7z output."""
        (temp_dir / "archive.rar").write_bytes(b"fake rar data" * 1000)

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (True, "extracted", "", 0)

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch.object(processor, "_delete_archive_files"):
                result = processor.process_rar_files(temp_dir)

        assert result is True
        assert mock_subprocess.call_args.kwargs["use_temp_files"] is True

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_successful_extraction(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test successful RAR extraction."""
        (temp_dir / "archive.rar").write_bytes(b"fake rar data" * 1000)

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (True, "extracted", "", 0)

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch.object(processor, "_delete_archive_files"):
                result = processor.process_rar_files(temp_dir)

        assert result is True
        assert mock_subprocess.called

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_extraction_failure(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test handling of extraction failure."""
        (temp_dir / "corrupt.rar").write_text("corrupt data")

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (False, "", "extraction failed", 1)

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch.object(processor, "_delete_archive_files"):
                result = processor.process_rar_files(temp_dir)

        # Should return False when all extractions fail
        assert result is False

    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_insufficient_disk_space(self, mock_disk_space, processor, temp_dir):
        """Test skipping extraction when disk space insufficient."""
        (temp_dir / "large.rar").write_bytes(b"x" * (100 * 1024 * 1024))  # 100MB

        mock_disk_space.return_value = False  # Not enough space

        with patch("core.archive_processor.logging.error") as mock_error:
            processor.process_rar_files(temp_dir)
            # Should log error about disk space (new multi-line format)
            assert mock_error.called
            error_message = str(mock_error.call_args_list).lower()
            assert "disk" in error_message and ("space" in error_message or "full" in error_message)

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_progress_callback(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test progress callback is called during extraction."""
        (temp_dir / "archive1.rar").write_text("test")
        (temp_dir / "archive2.rar").write_text("test")

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (True, "", "", 0)
        callback = Mock()

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch.object(processor, "_delete_archive_files"):
                processor.process_rar_files(temp_dir, progress_callback=callback)

        # Callback should be called for each archive
        assert callback.call_count == 2


class TestSecurityValidation:
    """Tests for security validation (path traversal detection)."""

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        processor = ArchiveProcessor(config)
        processor.system_check.get_tool_command = Mock(return_value=[r"C:\Program Files\7-Zip\7z.exe"])
        return processor

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_malicious_archive_skipped(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test that archives with path traversal are skipped."""
        (temp_dir / "malicious.rar").write_text("test")

        mock_disk_space.return_value = True

        # Simulate _validate_archive_paths detecting malicious content
        with patch.object(processor, "_validate_archive_paths", return_value=False):
            with patch("core.archive_processor.logging.error") as mock_error:
                processor.process_rar_files(temp_dir)
                # Should log security error
                assert any("SECURITY" in str(call) for call in mock_error.call_args_list)

        # Subprocess should NOT be called for malicious archive
        assert not mock_subprocess.called


class TestPAR2Processing:
    """Tests for PAR2 repair and verification."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        return ArchiveProcessor(config)

    def test_par2_processing_fails_closed_when_no_safe_command(self, processor, temp_dir):
        (temp_dir / "repair.par2").write_text("test")
        processor.system_check.get_tool_command = Mock(return_value=[])

        assert processor.process_par2_files(temp_dir) is False

    def test_no_par2_files_returns_true(self, processor, temp_dir):
        """Test that folders with no PAR2 files return success."""
        result = processor.process_par2_files(temp_dir)
        assert result is True

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    def test_successful_par2_verify(self, mock_subprocess, processor, temp_dir):
        """Test successful PAR2 verification (no repair needed)."""
        (temp_dir / "file.par2").write_text("test")
        (temp_dir / "file.vol01.par2").write_text("test")
        processor.system_check.get_tool_command = Mock(return_value=[r"C:\Program Files\par2cmdline\par2.exe"])

        # Simulate successful verification (code 0, success message in output)
        mock_subprocess.return_value = (True, "All files are correct", "", 0)

        with patch.object(processor, "_delete_files_by_extension"):
            result = processor.process_par2_files(temp_dir)

        assert result is True
        assert mock_subprocess.called

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    def test_successful_par2_repair(self, mock_subprocess, processor, temp_dir):
        """Test successful PAR2 repair."""
        (temp_dir / "file.par2").write_text("test")
        processor.system_check.get_tool_command = Mock(return_value=[r"C:\Program Files\par2cmdline\par2.exe"])

        # Simulate successful repair (repair complete message)
        mock_subprocess.return_value = (True, "Repair complete", "", 0)

        with patch.object(processor, "_delete_files_by_extension"):
            result = processor.process_par2_files(temp_dir)

        assert result is True

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    def test_par2_repair_failure(self, mock_subprocess, processor, temp_dir):
        """Test PAR2 repair failure (corrupted beyond repair)."""
        (temp_dir / "corrupt.par2").write_text("test")

        # Simulate repair failure (failure keyword in output)
        mock_subprocess.return_value = (False, "", "Repair failed", 1)

        with patch.object(processor, "_delete_files_by_extension"):
            with patch.object(processor, "_delete_archive_files"):
                result = processor.process_par2_files(temp_dir)

        # Should return False when repair fails
        assert result is False


class TestTimeoutHandling:
    """Tests for timeout handling with large archives."""

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        return ArchiveProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch("core.archive_processor.logging.info")
    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    @patch("core.archive_processor.SafetyLimits.calculate_rar_timeout")
    def test_dynamic_timeout_large_archive(
        self, mock_timeout_calc, mock_disk_space, mock_subprocess, mock_log, processor, temp_dir
    ):
        """Test that large archives get extended timeout."""
        # Create large archive
        large_archive = temp_dir / "large.rar"
        large_archive.write_bytes(b"x" * (100 * 1024 * 1024))  # 100MB actual file

        mock_disk_space.return_value = True
        mock_timeout_calc.return_value = 7200  # 2 hours for large file (> default timeout)
        mock_subprocess.return_value = (True, "", "", 0)

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch.object(processor, "_delete_archive_files"):
                processor.process_rar_files(temp_dir)

        # Should log about extended timeout
        assert any("extended timeout" in str(call).lower() for call in mock_log.call_args_list)


class TestSafetyLimits:
    """Tests for safety limits and loop guards."""

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor with safety limits."""
        config = Config()
        config.archive_extraction_loop_limit = 5  # Low limit for testing
        return ArchiveProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_loop_safety_limit(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test loop safety guard triggers when limit exceeded."""
        # Create more archives than the limit
        for i in range(10):
            (temp_dir / f"archive{i}.rar").write_text("test")

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (True, "", "", 0)

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch("core.archive_processor.logging.error") as mock_error:
                with patch.object(processor, "_delete_archive_files"):
                    processor.process_rar_files(temp_dir)

                # Should log loop safety error
                assert any("loop safety" in str(call).lower() for call in mock_error.call_args_list)


class TestCleanupOperations:
    """Tests for cleanup of archive and PAR2 files."""

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        return ArchiveProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_archives_deleted_after_extraction(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test that archive files are deleted after extraction."""
        archive = temp_dir / "archive.rar"
        archive.write_text("test")

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (True, "", "", 0)

        with patch.object(processor, "_validate_archive_paths", return_value=True):
            with patch.object(processor, "_delete_archive_files") as mock_delete:
                processor.process_rar_files(temp_dir)
                # Cleanup should be called
                assert mock_delete.called

    def test_delete_files_by_extension_retries_permission_error_then_force_deletes(self, processor, temp_dir):
        """Locked files should fall back to a final missing_ok unlink attempt."""
        archive = temp_dir / "locked.rar"
        archive.write_text("test")

        unlink_mock = Mock(
            side_effect=[
                PermissionError("locked"),
                PermissionError("still locked"),
                PermissionError("final lock"),
                None,
            ]
        )
        with patch.object(Path, "unlink", unlink_mock):
            with patch("core.archive_processor.time.sleep") as mock_sleep:
                processor._delete_files_by_extension(temp_dir, ".rar")

        assert unlink_mock.call_count == 4
        assert unlink_mock.call_args_list[-1].kwargs == {"missing_ok": True}
        assert mock_sleep.call_count == 2

    def test_delete_files_by_extension_skips_when_safety_enforcer_blocks(self, temp_dir):
        """Deletion should be skipped when invariant enforcement rejects the file."""
        config = Config()
        processor = ArchiveProcessor(config, destination_root=temp_dir)
        archive = temp_dir / "safe.rar"
        archive.write_text("test")
        processor.enforcer = Mock()
        processor.enforcer.enforce_delete.side_effect = RuntimeError("blocked")

        with patch.object(Path, "unlink") as mock_unlink:
            processor._delete_files_by_extension(temp_dir, ".rar")

        assert not mock_unlink.called


class TestArchivePathValidation:
    """Tests for _validate_archive_paths fail-closed behavior."""

    @pytest.fixture
    def processor(self):
        config = Config()
        return ArchiveProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @staticmethod
    def _fake_listing(stdout: str, *, success: bool = True, code: int = 0):
        """Build a fake run_with_line_handler that streams ``stdout`` line-by-line."""

        def fake(*_args, **kwargs):
            handler = kwargs["line_handler"]
            for line in stdout.split("\n"):
                if handler(line) is False:
                    break
            return success, "", code

        return fake

    def test_validate_archive_paths_returns_false_when_listing_fails(self, processor, temp_dir):
        archive = temp_dir / "archive.rar"
        archive.write_text("test")

        fake = self._fake_listing("", success=False, code=2)
        with patch("core.archive_processor.SubprocessSafety.run_with_line_handler", side_effect=fake):
            assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is False

    def test_validate_archive_paths_rejects_absolute_paths(self, processor, temp_dir):
        archive = temp_dir / "archive.rar"
        archive.write_text("test")
        stdout = "2024-01-01 00:00:00 ....A 1 1 C:\\evil.txt\n"

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler",
            side_effect=self._fake_listing(stdout),
        ):
            assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is False

    def test_validate_archive_paths_rejects_parent_traversal(self, processor, temp_dir):
        archive = temp_dir / "archive.rar"
        archive.write_text("test")
        stdout = "2024-01-01 00:00:00 ....A 1 1 ..\\evil.txt\n"

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler",
            side_effect=self._fake_listing(stdout),
        ):
            assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is False

    def test_validate_archive_paths_accepts_safe_relative_paths(self, processor, temp_dir):
        archive = temp_dir / "archive.rar"
        archive.write_text("test")
        stdout = "2024-01-01 00:00:00 ....A 1 1 subdir\\video.mkv\n"

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler",
            side_effect=self._fake_listing(stdout),
        ):
            assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is True

    def test_validate_archive_paths_returns_false_on_validation_exception(self, processor, temp_dir):
        archive = temp_dir / "archive.rar"
        archive.write_text("test")
        stdout = "2024-01-01 00:00:00 ....A 1 1 safe.txt\n"

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler",
            side_effect=self._fake_listing(stdout),
        ):
            with patch.object(Path, "resolve", side_effect=RuntimeError("boom")):
                assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is False

    def test_validate_archive_paths_streams_full_listing_no_truncation_bypass(self, processor, temp_dir):
        """
        Regression: a previous version read a 64 KiB head/tail sample from the
        7z listing temp file. An attacker could craft an archive whose listing
        exceeds the cap and place an unsafe entry in the truncated middle, then
        validation would pass while extraction still saw the entry. The fix
        streams the full listing line-by-line, so unsafe entries are rejected
        regardless of where they appear.
        """
        archive = temp_dir / "archive.rar"
        archive.write_text("test")

        safe_line = "2024-01-01 00:00:00 ....A 1 1 safe_file_{i}.txt"
        unsafe_line = "2024-01-01 00:00:00 ....A 1 1 ../outside_pwned.txt"
        # Build a listing larger than the bounded-capture cap, with the unsafe
        # entry buried in the middle.
        head_lines = [safe_line.format(i=i) for i in range(4000)]
        tail_lines = [safe_line.format(i=i) for i in range(4000, 8000)]
        full_listing = "\n".join(head_lines + [unsafe_line] + tail_lines) + "\n"

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler",
            side_effect=self._fake_listing(full_listing),
        ):
            assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is False

    def test_validate_archive_paths_accepts_large_safe_listing(self, processor, temp_dir):
        """Control case: a multi-megabyte listing of only safe entries is accepted."""
        archive = temp_dir / "archive.rar"
        archive.write_text("test")

        safe_line = "2024-01-01 00:00:00 ....A 1 1 sub/file_{i}.txt"
        full_listing = "\n".join(safe_line.format(i=i) for i in range(20000)) + "\n"

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_line_handler",
            side_effect=self._fake_listing(full_listing),
        ):
            assert processor._validate_archive_paths(archive, temp_dir, ["7z"]) is True


class TestPar2ErrorHandling:
    """Tests for less common PAR2 completion and failure branches."""

    @pytest.fixture
    def processor(self):
        config = Config()
        processor = ArchiveProcessor(config)
        processor.system_check.get_tool_command = Mock(return_value=[r"C:\Program Files\par2cmdline\par2.exe"])
        return processor

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    def test_par2_success_with_unclear_output_still_returns_true(self, processor, temp_dir):
        (temp_dir / "file.par2").write_text("test")

        with patch("core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(True, "done", "", 0)):
            with patch.object(processor, "_delete_files_by_extension") as mock_delete:
                assert processor.process_par2_files(temp_dir) is True

        mock_delete.assert_called_once_with(temp_dir, ".par2")

    def test_par2_timeout_or_unknown_error_returns_false_without_cleanup(self, processor, temp_dir):
        (temp_dir / "file.par2").write_text("test")

        with patch("core.archive_processor.SubprocessSafety.run_with_timeout", return_value=(False, "", "", 0)):
            with patch.object(processor, "_delete_files_by_extension") as mock_delete:
                with patch.object(processor, "_delete_archive_files") as mock_delete_archives:
                    assert processor.process_par2_files(temp_dir) is False

        assert not mock_delete.called
        assert not mock_delete_archives.called

    def test_par2_failure_deletes_par2_and_archives(self, processor, temp_dir):
        (temp_dir / "file.par2").write_text("test")

        with patch(
            "core.archive_processor.SubprocessSafety.run_with_timeout",
            return_value=(False, "", "repair is impossible", 2),
        ):
            with patch.object(processor, "_delete_files_by_extension") as mock_delete:
                with patch.object(processor, "_delete_archive_files") as mock_delete_archives:
                    assert processor.process_par2_files(temp_dir) is False

        mock_delete.assert_called_once_with(temp_dir, ".par2")
        mock_delete_archives.assert_called_once_with(temp_dir)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def processor(self):
        """Create ArchiveProcessor instance."""
        config = Config()
        return ArchiveProcessor(config)

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    def test_empty_directory(self, processor, temp_dir):
        """Test processing empty directory."""
        result = processor.process_rar_files(temp_dir)
        assert result is True

    @patch("core.archive_processor.SubprocessSafety.run_with_timeout")
    @patch("core.archive_processor.StateValidator.check_disk_space")
    def test_archive_stat_failure(self, mock_disk_space, mock_subprocess, processor, temp_dir):
        """Test graceful handling when file stat fails."""
        archive = temp_dir / "archive.rar"
        archive.write_text("test")

        mock_disk_space.return_value = True
        mock_subprocess.return_value = (True, "", "", 0)

        # Mock stat to raise exception
        with patch.object(Path, "stat", side_effect=OSError("Stat failed")):
            with patch.object(processor, "_validate_archive_paths", return_value=True):
                with patch.object(processor, "_delete_archive_files"):
                    # Should handle gracefully, not crash
                    result = processor.process_rar_files(temp_dir)
                    assert result is not None

    def test_process_with_none_config(self):
        """Test processor works with None config (uses defaults)."""
        processor = ArchiveProcessor(config=None)
        assert processor.config is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
