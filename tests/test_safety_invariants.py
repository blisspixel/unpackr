"""
Test suite for safety_invariants module.

Tests cover all 10 safety invariants plus the enforcement wrapper.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.safety_invariants import (
    SafetyInvariants,
    InvariantEnforcer,
    SafetyViolationError,
    FileOperation,
    OperationType,
    ValidationDecision,
    ValidationResult,
    ValidationCache
)


class TestInvariantI1PathSafety:
    """Test I1: Never write outside destination."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def invariants(self, temp_dir):
        return SafetyInvariants(destination_root=temp_dir)

    def test_write_inside_destination_allowed(self, invariants, temp_dir):
        """Test writing inside destination is allowed."""
        target = temp_dir / "subdir" / "file.txt"
        operation = FileOperation(OperationType.WRITE, target)

        assert invariants.never_write_outside_destination(operation) is True

    def test_write_outside_destination_blocked(self, invariants, temp_dir):
        """Test writing outside destination is blocked."""
        outside_path = Path("C:/Windows/System32/evil.exe")
        operation = FileOperation(OperationType.WRITE, outside_path)

        assert invariants.never_write_outside_destination(operation) is False

    def test_move_to_outside_destination_blocked(self, invariants, temp_dir):
        """Test moving to outside destination is blocked."""
        source = temp_dir / "file.txt"
        outside_dest = Path("C:/Users/Public/file.txt")
        operation = FileOperation(OperationType.MOVE, source, outside_dest)

        assert invariants.never_write_outside_destination(operation) is False

    def test_read_operations_not_affected(self, invariants, temp_dir):
        """Test that read operations don't trigger path checks."""
        outside_path = Path("C:/Windows/System32/kernel32.dll")
        # DELETE is not a write operation in this context
        operation = FileOperation(OperationType.DELETE, outside_path)

        # I1 doesn't apply to DELETE operations
        assert invariants.never_write_outside_destination(operation) is True


class TestInvariantI2VideoProtection:
    """Test I2: Never delete validated videos."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
        ValidationCache.clear()

    @pytest.fixture
    def invariants(self, temp_dir):
        return SafetyInvariants(destination_root=temp_dir)

    def test_delete_unvalidated_video_allowed(self, invariants, temp_dir):
        """Test deleting unvalidated video is allowed."""
        video = temp_dir / "test.mp4"
        operation = FileOperation(OperationType.DELETE, video)

        assert invariants.never_delete_validated_video(operation) is True

    def test_delete_validated_healthy_video_blocked(self, invariants, temp_dir):
        """Test deleting validated healthy video is blocked."""
        video = temp_dir / "healthy.mp4"
        video.write_text("test")

        # Mark as validated and healthy
        result = ValidationResult(
            path=video,
            decision=ValidationDecision.PASS,
            timestamp=None,
            metadata={}
        )
        ValidationCache.set(video, result)

        operation = FileOperation(OperationType.DELETE, video)
        assert invariants.never_delete_validated_video(operation) is False

    def test_delete_corrupt_video_allowed(self, invariants, temp_dir):
        """Test deleting corrupt video is allowed even after validation."""
        video = temp_dir / "corrupt.mp4"
        video.write_text("test")

        # Mark as validated but corrupt
        result = ValidationResult(
            path=video,
            decision=ValidationDecision.FAIL_CORRUPT,
            timestamp=None,
            metadata={}
        )
        ValidationCache.set(video, result)

        operation = FileOperation(OperationType.DELETE, video)
        assert invariants.never_delete_validated_video(operation) is True

    def test_delete_non_video_not_affected(self, invariants, temp_dir):
        """Test deleting non-video files isn't affected."""
        text_file = temp_dir / "readme.txt"
        operation = FileOperation(OperationType.DELETE, text_file)

        assert invariants.never_delete_validated_video(operation) is True


class TestInvariantI3ArchiveSafety:
    """Test I3: Never delete archives before extraction validated."""

    @pytest.fixture
    def invariants(self):
        temp_dir = Path(tempfile.mkdtemp())
        inv = SafetyInvariants(destination_root=temp_dir)
        yield inv
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_archive_after_verification_allowed(self, invariants):
        """Test deleting archive after verification is allowed."""
        archive = Path("test.rar")
        operation = FileOperation(OperationType.DELETE, archive)

        assert invariants.never_delete_archives_before_validation(
            operation,
            extraction_verified=True
        ) is True

    def test_delete_archive_before_verification_blocked(self, invariants):
        """Test deleting archive before verification is blocked."""
        archive = Path("test.rar")
        operation = FileOperation(OperationType.DELETE, archive)

        assert invariants.never_delete_archives_before_validation(
            operation,
            extraction_verified=False
        ) is False

    def test_delete_non_archive_not_affected(self, invariants):
        """Test deleting non-archives isn't affected."""
        video = Path("test.mp4")
        operation = FileOperation(OperationType.DELETE, video)

        # Non-archive files don't trigger this invariant
        assert invariants.never_delete_archives_before_validation(
            operation,
            extraction_verified=False
        ) is True


class TestInvariantI4LoopBounds:
    """Test I4: Never exceed loop bounds."""

    @pytest.fixture
    def invariants(self):
        temp_dir = Path(tempfile.mkdtemp())
        config = Mock()
        config.archive_extraction_loop_limit = 10
        inv = SafetyInvariants(destination_root=temp_dir, config=config)
        yield inv
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_loop_within_bounds_allowed(self, invariants):
        """Test loop within bounds is allowed."""
        assert invariants.never_exceed_loop_bounds("test_loop", 5, 10) is True

    def test_loop_at_bound_blocked(self, invariants):
        """Test loop at boundary is blocked."""
        assert invariants.never_exceed_loop_bounds("test_loop", 10, 10) is False

    def test_loop_exceeds_bound_blocked(self, invariants):
        """Test loop exceeding bound is blocked."""
        assert invariants.never_exceed_loop_bounds("test_loop", 15, 10) is False

    def test_loop_uses_config_default(self, invariants):
        """Test loop uses config default when not specified."""
        # Config has limit of 10
        assert invariants.never_exceed_loop_bounds("test_loop", 5) is True
        assert invariants.never_exceed_loop_bounds("test_loop", 10) is False


class TestInvariantI5DiskSpace:
    """Test I5: Never operate without disk space."""

    @pytest.fixture
    def invariants(self):
        temp_dir = Path(tempfile.mkdtemp())
        inv = SafetyInvariants(destination_root=temp_dir)
        yield inv
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_sufficient_space_allowed(self, invariants):
        """Test operation with sufficient space is allowed."""
        required = 100 * 1024 * 1024  # 100MB
        available = 200 * 1024 * 1024  # 200MB
        # With 1.5x buffer, needs 150MB, have 200MB
        assert invariants.never_operate_without_disk_space(required, available) is True

    def test_insufficient_space_blocked(self, invariants):
        """Test operation without enough space is blocked."""
        required = 100 * 1024 * 1024  # 100MB
        available = 100 * 1024 * 1024  # 100MB
        # With 1.5x buffer, needs 150MB, only have 100MB
        assert invariants.never_operate_without_disk_space(required, available) is False

    def test_custom_buffer_ratio(self, invariants):
        """Test custom buffer ratio."""
        required = 100 * 1024 * 1024  # 100MB
        available = 180 * 1024 * 1024  # 180MB
        # With 2.0x buffer, needs 200MB, only have 180MB
        assert invariants.never_operate_without_disk_space(
            required, available, buffer_ratio=2.0
        ) is False


class TestInvariantI6FilenameSafety:
    """Test I6: Never create dangerous filenames."""

    @pytest.fixture
    def invariants(self):
        temp_dir = Path(tempfile.mkdtemp())
        inv = SafetyInvariants(destination_root=temp_dir)
        yield inv
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_safe_filename_allowed(self, invariants):
        """Test safe filename is allowed."""
        assert invariants.never_create_dangerous_filename("video.mp4") is True
        assert invariants.never_create_dangerous_filename("My Movie (2023).mkv") is True

    def test_path_traversal_blocked(self, invariants):
        """Test path traversal is blocked."""
        assert invariants.never_create_dangerous_filename("../../../etc/passwd") is False
        assert invariants.never_create_dangerous_filename("..\\windows\\system32") is False

    def test_shell_operators_blocked(self, invariants):
        """Test shell operators are blocked."""
        assert invariants.never_create_dangerous_filename("file|command.mp4") is False
        assert invariants.never_create_dangerous_filename("file;rm -rf.mp4") is False
        assert invariants.never_create_dangerous_filename("file&background.mp4") is False

    def test_command_substitution_blocked(self, invariants):
        """Test command substitution is blocked."""
        assert invariants.never_create_dangerous_filename("file`whoami`.mp4") is False
        assert invariants.never_create_dangerous_filename("file$(id).mp4") is False

    def test_control_characters_blocked(self, invariants):
        """Test control characters are blocked."""
        assert invariants.never_create_dangerous_filename("file\x00.mp4") is False
        assert invariants.never_create_dangerous_filename("file\x01name.mp4") is False

    def test_windows_reserved_names_blocked(self, invariants):
        """Test Windows reserved names are blocked."""
        assert invariants.never_create_dangerous_filename("CON.mp4") is False
        assert invariants.never_create_dangerous_filename("PRN.txt") is False
        assert invariants.never_create_dangerous_filename("AUX.mp4") is False
        assert invariants.never_create_dangerous_filename("COM1.dat") is False


class TestInvariantI7StateTransitions:
    """Test I7: State machine transitions follow explicit paths."""

    @pytest.fixture
    def invariants(self):
        temp_dir = Path(tempfile.mkdtemp())
        inv = SafetyInvariants(destination_root=temp_dir)
        yield inv
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_legal_transition_allowed(self, invariants):
        """Test legal state transition is allowed."""
        allowed = {
            'DISCOVERED': {'SCANNING', 'ERROR'},
            'SCANNING': {'CLASSIFYING', 'ERROR'},
            'CLASSIFYING': {'PROCESSING', 'ERROR'}
        }

        assert invariants.is_legal_state_transition(
            'DISCOVERED', 'SCANNING', allowed
        ) is True

    def test_illegal_transition_blocked(self, invariants):
        """Test illegal state transition is blocked."""
        allowed = {
            'DISCOVERED': {'SCANNING', 'ERROR'},
            'SCANNING': {'CLASSIFYING', 'ERROR'}
        }

        # Can't go directly from DISCOVERED to CLASSIFYING
        assert invariants.is_legal_state_transition(
            'DISCOVERED', 'CLASSIFYING', allowed
        ) is False

    def test_unknown_state_blocked(self, invariants):
        """Test unknown state is blocked."""
        allowed = {
            'DISCOVERED': {'SCANNING'}
        }

        assert invariants.is_legal_state_transition(
            'UNKNOWN_STATE', 'SCANNING', allowed
        ) is False


class TestInvariantI8TimeoutBounds:
    """Test I8: All operations have explicit timeouts."""

    @pytest.fixture
    def invariants(self):
        temp_dir = Path(tempfile.mkdtemp())
        inv = SafetyInvariants(destination_root=temp_dir)
        yield inv
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_valid_timeout_allowed(self, invariants):
        """Test valid timeout is allowed."""
        assert invariants.has_valid_timeout("extraction", 3600) is True

    def test_no_timeout_blocked(self, invariants):
        """Test missing timeout is blocked."""
        assert invariants.has_valid_timeout("extraction", None) is False

    def test_excessive_timeout_warned(self, invariants):
        """Test excessive timeout is warned but allowed."""
        # 10 hours is excessive but may be legitimate
        assert invariants.has_valid_timeout("extraction", 36000) is True


class TestInvariantI9ResourceCleanup:
    """Test I9: Temporary files are cleaned up."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def invariants(self, temp_dir):
        return SafetyInvariants(destination_root=temp_dir)

    def test_cleanup_complete_passes(self, invariants, temp_dir):
        """Test cleanup verification passes when files are gone."""
        temp_file = temp_dir / "temp.txt"
        temp_file.write_text("temp")
        temp_file.unlink()  # Clean up

        assert invariants.verify_cleanup_complete({temp_file}, "test_op") is True

    def test_cleanup_incomplete_fails(self, invariants, temp_dir):
        """Test cleanup verification fails when files remain."""
        temp_file = temp_dir / "temp.txt"
        temp_file.write_text("temp")
        # Don't clean up

        assert invariants.verify_cleanup_complete({temp_file}, "test_op") is False


class TestInvariantI10Provenance:
    """Test I10: Every file has traceable origin."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def invariants(self, temp_dir):
        return SafetyInvariants(destination_root=temp_dir)

    def test_file_in_destination_has_provenance(self, invariants, temp_dir):
        """Test file in destination passes provenance check."""
        target = temp_dir / "video.mp4"
        assert invariants.has_valid_provenance(target) is True

    def test_file_outside_destination_fails_provenance(self, invariants, temp_dir):
        """Test file outside destination fails provenance check."""
        outside = Path("C:/Users/Public/video.mp4")
        assert invariants.has_valid_provenance(outside) is False


class TestInvariantEnforcer:
    """Test the InvariantEnforcer wrapper."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)
        ValidationCache.clear()

    @pytest.fixture
    def enforcer(self, temp_dir):
        return InvariantEnforcer(destination_root=temp_dir)

    def test_safe_delete_allowed(self, enforcer, temp_dir):
        """Test safe delete operation is allowed."""
        file = temp_dir / "test.txt"
        file.write_text("test")

        assert enforcer.enforce_delete(file) is True

    def test_unsafe_delete_blocked_strict_mode(self, enforcer, temp_dir):
        """Test unsafe delete raises exception in strict mode."""
        video = temp_dir / "healthy.mp4"
        video.write_text("test")

        # Mark as validated
        result = ValidationResult(
            path=video,
            decision=ValidationDecision.PASS,
            timestamp=None,
            metadata={}
        )
        ValidationCache.set(video, result)

        with pytest.raises(SafetyViolationError, match="Cannot delete"):
            enforcer.enforce_delete(video)

    def test_unsafe_delete_logged_permissive_mode(self, enforcer, temp_dir):
        """Test unsafe delete is logged but not raised in permissive mode."""
        enforcer.strict_mode = False

        video = temp_dir / "healthy.mp4"
        video.write_text("test")

        # Mark as validated
        result = ValidationResult(
            path=video,
            decision=ValidationDecision.PASS,
            timestamp=None,
            metadata={}
        )
        ValidationCache.set(video, result)

        # Should return False but not raise
        assert enforcer.enforce_delete(video) is False
        assert enforcer.violations_count > 0

    def test_safe_move_allowed(self, enforcer, temp_dir):
        """Test safe move operation is allowed."""
        source = temp_dir / "source.txt"
        dest = temp_dir / "dest.txt"
        source.write_text("test")

        assert enforcer.enforce_move(source, dest) is True

    def test_unsafe_move_blocked(self, enforcer, temp_dir):
        """Test move outside destination is blocked."""
        source = temp_dir / "source.txt"
        outside_dest = Path("C:/Windows/System32/evil.exe")

        with pytest.raises(SafetyViolationError, match="Cannot move"):
            enforcer.enforce_move(source, outside_dest)

    def test_safe_write_allowed(self, enforcer, temp_dir):
        """Test safe write operation is allowed."""
        target = temp_dir / "new_file.txt"
        assert enforcer.enforce_write(target) is True

    def test_dangerous_filename_write_blocked(self, enforcer, temp_dir):
        """Test write with dangerous filename is blocked."""
        target = temp_dir / "file|command.txt"

        with pytest.raises(SafetyViolationError, match="Cannot write"):
            enforcer.enforce_write(target)


class TestCheckBeforeOperation:
    """Test the comprehensive check_before_operation method."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def invariants(self, temp_dir):
        return SafetyInvariants(destination_root=temp_dir)

    def test_all_checks_pass(self, invariants, temp_dir):
        """Test operation that passes all checks."""
        target = temp_dir / "file.txt"
        operation = FileOperation(OperationType.WRITE, target)

        passed, violations = invariants.check_before_operation(operation)

        assert passed is True
        assert len(violations) == 0

    def test_multiple_violations_detected(self, invariants, temp_dir):
        """Test operation with multiple violations."""
        # File outside destination + dangerous filename
        outside = Path("C:/Windows/../etc") / "file|command.txt"
        operation = FileOperation(OperationType.WRITE, outside)

        passed, violations = invariants.check_before_operation(operation)

        assert passed is False
        assert len(violations) >= 2  # At least I1 and I6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
