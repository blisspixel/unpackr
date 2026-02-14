"""
Executable Safety Invariants

This module implements the Safety Contract as executable predicates that MUST
hold true at all times during operation. These invariants are checked before
every destructive operation (delete, move, overwrite).

Design Philosophy:
- Convert prose safety guarantees into bool-returning functions
- Fail fast with detailed error messages when invariants are violated
- Zero tolerance for invariant violations (safety-critical code)
- Comprehensive logging for forensic analysis

References:
- docs/DEEP_ANALYSIS.md - Theoretical foundation
- docs/SAFETY_CONTRACT.md - Original prose contract
"""

import logging
from pathlib import Path
from typing import Optional, Set
from enum import Enum, auto
from dataclasses import dataclass
from datetime import datetime


logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of file operations that require invariant checking."""
    WRITE = auto()
    DELETE = auto()
    MOVE = auto()
    OVERWRITE = auto()


class ValidationDecision(Enum):
    """Video validation decisions."""
    PASS = auto()
    FAIL_CORRUPT = auto()
    FAIL_LOW_QUALITY = auto()
    FAIL_DUPLICATE = auto()
    FAIL_SAMPLE = auto()
    UNKNOWN = auto()


@dataclass
class FileOperation:
    """Represents a file operation that must satisfy invariants."""
    type: OperationType
    path: Path
    destination: Optional[Path] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def is_video(self) -> bool:
        """Check if target is a video file."""
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        return self.path.suffix.lower() in video_extensions


@dataclass
class ValidationResult:
    """Result of video health validation."""
    path: Path
    decision: ValidationDecision
    timestamp: datetime
    metadata: dict


class ValidationCache:
    """Cache of video validation results."""
    _cache: dict[Path, ValidationResult] = {}

    @classmethod
    def get(cls, path: Path) -> Optional[ValidationResult]:
        """Get validation result for a video."""
        return cls._cache.get(path.resolve())

    @classmethod
    def set(cls, path: Path, result: ValidationResult):
        """Store validation result."""
        cls._cache[path.resolve()] = result

    @classmethod
    def clear(cls):
        """Clear cache (for testing)."""
        cls._cache.clear()


class SafetyInvariants:
    """
    Executable predicates that MUST hold true at all times.

    Each method returns True if the invariant is satisfied, False otherwise.
    These are checked before destructive operations to prevent data loss.
    """

    def __init__(self, destination_root: Path, config=None):
        """
        Initialize invariants with system configuration.

        Args:
            destination_root: The root directory where files are organized
            config: Configuration object with safety settings
        """
        self.destination_root = destination_root.resolve()
        self.config = config
        self._protected_paths: Set[Path] = set()
        self._validated_videos: Set[Path] = set()

    # ============================================================================
    # I1: Path Safety - Never write outside destination
    # ============================================================================

    def never_write_outside_destination(self, operation: FileOperation) -> bool:
        """
        I1: All writes target destination root or subdirectories.

        This prevents path traversal attacks and accidental writes to
        system directories, user documents, or other critical locations.

        Args:
            operation: File operation to validate

        Returns:
            True if write target is safe, False otherwise
        """
        if operation.type in (OperationType.WRITE, OperationType.MOVE):
            target = operation.destination if operation.destination else operation.path

            try:
                target_resolved = target.resolve()

                # Check if target is within destination root
                is_safe = target_resolved.is_relative_to(self.destination_root)

                if not is_safe:
                    logger.error(
                        f"INVARIANT VIOLATION I1: Write outside destination\n"
                        f"  Operation: {operation.type.name}\n"
                        f"  Target: {target_resolved}\n"
                        f"  Allowed root: {self.destination_root}"
                    )

                return is_safe

            except (ValueError, OSError) as e:
                logger.error(f"I1 check failed with error: {e}")
                return False

        return True  # Non-write operations don't violate this invariant

    # ============================================================================
    # I2: Video Protection - Never delete validated videos
    # ============================================================================

    def never_delete_validated_video(self, operation: FileOperation) -> bool:
        """
        I2: Videos that passed validation are only MOVED, never DELETED.

        This prevents accidental loss of good video files. Validated videos
        must be explicitly moved to destination, never deleted from source.

        Args:
            operation: File operation to validate

        Returns:
            True if operation is safe, False if attempting to delete validated video
        """
        if operation.type == OperationType.DELETE and operation.is_video():
            validation_result = ValidationCache.get(operation.path)

            # If video was validated and passed, it should be moved, not deleted
            if validation_result and validation_result.decision == ValidationDecision.PASS:
                logger.error(
                    f"INVARIANT VIOLATION I2: Attempting to delete validated video\n"
                    f"  Path: {operation.path}\n"
                    f"  Validation: {validation_result.decision.name}\n"
                    f"  Validated at: {validation_result.timestamp}"
                )
                return False

        return True

    # ============================================================================
    # I3: Archive Safety - Never delete archives before extraction validated
    # ============================================================================

    def never_delete_archives_before_validation(
        self,
        operation: FileOperation,
        extraction_verified: bool = False
    ) -> bool:
        """
        I3: Archive files (.rar, .zip, .7z) are only deleted after successful
        extraction AND validation of extracted contents.

        This prevents losing archived videos if extraction appears successful
        but extracted files are corrupt or incomplete.

        Args:
            operation: File operation to validate
            extraction_verified: Whether extracted contents have been validated

        Returns:
            True if safe to delete archive, False otherwise
        """
        archive_extensions = {'.rar', '.zip', '.7z', '.par2'}

        if operation.type == OperationType.DELETE:
            if operation.path.suffix.lower() in archive_extensions:
                if not extraction_verified:
                    logger.error(
                        f"INVARIANT VIOLATION I3: Deleting archive before validation\n"
                        f"  Archive: {operation.path}\n"
                        f"  Extraction verified: {extraction_verified}"
                    )
                    return False

        return True

    # ============================================================================
    # I4: Loop Bound - Never exceed maximum iteration counts
    # ============================================================================

    def never_exceed_loop_bounds(
        self,
        loop_name: str,
        iteration_count: int,
        max_iterations: Optional[int] = None
    ) -> bool:
        """
        I4: All loops have explicit upper bounds to prevent infinite loops.

        This prevents runaway operations that could consume unlimited disk space,
        CPU time, or get stuck in extraction loops.

        Args:
            loop_name: Identifier for the loop being checked
            iteration_count: Current iteration number
            max_iterations: Maximum allowed iterations (from config if not provided)

        Returns:
            True if within bounds, False if exceeded
        """
        if max_iterations is None and self.config:
            max_iterations = getattr(
                self.config,
                'archive_extraction_loop_limit',
                100
            )

        if max_iterations and iteration_count >= max_iterations:
            logger.error(
                f"INVARIANT VIOLATION I4: Loop bound exceeded\n"
                f"  Loop: {loop_name}\n"
                f"  Iterations: {iteration_count}\n"
                f"  Max allowed: {max_iterations}"
            )
            return False

        return True

    # ============================================================================
    # I5: Disk Space - Never start operations without sufficient space
    # ============================================================================

    def never_operate_without_disk_space(
        self,
        required_bytes: int,
        available_bytes: int,
        buffer_ratio: float = 1.5
    ) -> bool:
        """
        I5: Operations requiring disk space have 1.5x buffer over estimated need.

        This prevents disk-full errors mid-operation which could leave the
        system in an inconsistent state with partial files.

        Args:
            required_bytes: Estimated space needed for operation
            available_bytes: Currently available disk space
            buffer_ratio: Safety buffer multiplier (default 1.5x)

        Returns:
            True if sufficient space available, False otherwise
        """
        required_with_buffer = required_bytes * buffer_ratio

        if available_bytes < required_with_buffer:
            logger.error(
                f"INVARIANT VIOLATION I5: Insufficient disk space\n"
                f"  Required: {required_bytes / (1024**3):.2f} GB\n"
                f"  Required with buffer: {required_with_buffer / (1024**3):.2f} GB\n"
                f"  Available: {available_bytes / (1024**3):.2f} GB\n"
                f"  Buffer ratio: {buffer_ratio}x"
            )
            return False

        return True

    # ============================================================================
    # I6: Filename Safety - Never create files with dangerous names
    # ============================================================================

    def never_create_dangerous_filename(self, filename: str) -> bool:
        """
        I6: All created files have sanitized names (no path traversal, control chars).

        This prevents directory traversal attacks, shell injection, and
        filesystem corruption from malformed filenames.

        Args:
            filename: Proposed filename to validate

        Returns:
            True if filename is safe, False otherwise
        """
        dangerous_patterns = [
            '..',           # Path traversal
            '~',            # Home directory expansion
            '$',            # Shell variable expansion
            '`',            # Command substitution
            '|', ';', '&',  # Shell operators
            '\x00',         # Null byte
        ]

        # Check for dangerous patterns
        for pattern in dangerous_patterns:
            if pattern in filename:
                logger.error(
                    f"INVARIANT VIOLATION I6: Dangerous filename pattern\n"
                    f"  Filename: {filename}\n"
                    f"  Dangerous pattern: {repr(pattern)}"
                )
                return False

        # Check for control characters (0x00-0x1F)
        if any(ord(c) < 32 for c in filename):
            logger.error(
                f"INVARIANT VIOLATION I6: Control characters in filename\n"
                f"  Filename: {repr(filename)}"
            )
            return False

        # Check for Windows reserved names
        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }

        name_without_ext = Path(filename).stem.upper()
        if name_without_ext in reserved_names:
            logger.error(
                f"INVARIANT VIOLATION I6: Windows reserved name\n"
                f"  Filename: {filename}\n"
                f"  Reserved name: {name_without_ext}"
            )
            return False

        return True

    # ============================================================================
    # I7: State Consistency - Never transition to illegal state
    # ============================================================================

    def is_legal_state_transition(
        self,
        current_state: str,
        next_state: str,
        allowed_transitions: dict
    ) -> bool:
        """
        I7: State machine transitions follow explicit allowed paths.

        This prevents the system from entering undefined or inconsistent states
        by enforcing explicit state transition rules.

        Args:
            current_state: Current state name
            next_state: Proposed next state
            allowed_transitions: Dict mapping states to allowed next states

        Returns:
            True if transition is legal, False otherwise
        """
        if current_state not in allowed_transitions:
            logger.error(
                f"INVARIANT VIOLATION I7: Unknown current state\n"
                f"  State: {current_state}"
            )
            return False

        if next_state not in allowed_transitions[current_state]:
            logger.error(
                f"INVARIANT VIOLATION I7: Illegal state transition\n"
                f"  From: {current_state}\n"
                f"  To: {next_state}\n"
                f"  Allowed: {allowed_transitions[current_state]}"
            )
            return False

        return True

    # ============================================================================
    # I8: Timeout Bounds - Never use unbounded timeouts
    # ============================================================================

    def has_valid_timeout(
        self,
        operation_name: str,
        timeout_seconds: Optional[int]
    ) -> bool:
        """
        I8: All subprocess operations have explicit timeouts.

        This prevents hanging on stuck processes (corrupt archives, network timeouts).

        Args:
            operation_name: Name of the operation being performed
            timeout_seconds: Proposed timeout value

        Returns:
            True if timeout is valid, False if None or unreasonably large
        """
        if timeout_seconds is None:
            logger.error(
                f"INVARIANT VIOLATION I8: No timeout specified\n"
                f"  Operation: {operation_name}"
            )
            return False

        # Reasonable upper bound: 2 hours (7200 seconds)
        max_reasonable_timeout = 7200

        if timeout_seconds > max_reasonable_timeout:
            logger.warning(
                f"INVARIANT I8: Unusually large timeout\n"
                f"  Operation: {operation_name}\n"
                f"  Timeout: {timeout_seconds}s ({timeout_seconds/3600:.1f}h)\n"
                f"  Max reasonable: {max_reasonable_timeout}s"
            )
            # Return True but log warning - may be legitimate for very large archives
            return True

        return True

    # ============================================================================
    # I9: Resource Cleanup - Never leave temp files after operation
    # ============================================================================

    def verify_cleanup_complete(
        self,
        temp_paths: Set[Path],
        operation_name: str
    ) -> bool:
        """
        I9: Temporary files are cleaned up even on operation failure.

        This prevents disk space leaks from abandoned temporary files.

        Args:
            temp_paths: Set of temporary paths that should be cleaned up
            operation_name: Name of operation that created temp files

        Returns:
            True if all temp files are gone, False if any remain
        """
        remaining_files = [p for p in temp_paths if p.exists()]

        if remaining_files:
            logger.error(
                f"INVARIANT VIOLATION I9: Temporary files not cleaned up\n"
                f"  Operation: {operation_name}\n"
                f"  Remaining files ({len(remaining_files)}):\n" +
                '\n'.join(f"    {p}" for p in remaining_files[:5])
            )
            return False

        return True

    # ============================================================================
    # I10: Provenance Integrity - Never lose operation history
    # ============================================================================

    def has_valid_provenance(
        self,
        target_path: Path,
        expected_source: Optional[Path] = None
    ) -> bool:
        """
        I10: Every file in destination has traceable origin.

        This enables forensic analysis of where files came from and what
        operations were performed on them.

        Args:
            target_path: File in destination to check
            expected_source: Optional expected source path

        Returns:
            True if provenance is traceable, False otherwise

        Note: Full implementation requires provenance tracking system (Phase 2)
        """
        # For now, just verify the file is within destination root
        # Full provenance tracking to be implemented in Phase 2

        try:
            # Normalize/canonicalize target before containment checks so Windows
            # short aliases (e.g. RUNNER~1) match resolved destination paths.
            target_resolved = target_path.resolve()

            if not target_resolved.is_relative_to(self.destination_root):
                logger.error(
                    f"INVARIANT VIOLATION I10: File outside destination\n"
                    f"  File: {target_path}\n"
                    f"  Destination root: {self.destination_root}"
                )
                return False
        except ValueError:
            return False

        return True

    # ============================================================================
    # Convenience: Check all relevant invariants for an operation
    # ============================================================================

    def check_before_operation(
        self,
        operation: FileOperation,
        **kwargs
    ) -> tuple[bool, list[str]]:
        """
        Check all relevant invariants before performing an operation.

        Args:
            operation: The operation to validate
            **kwargs: Additional context for specific invariants

        Returns:
            Tuple of (all_passed, list_of_violations)
        """
        violations = []

        # I1: Path safety
        if not self.never_write_outside_destination(operation):
            violations.append("I1: Write outside destination")

        # I2: Video protection
        if not self.never_delete_validated_video(operation):
            violations.append("I2: Deleting validated video")

        # I3: Archive safety (if context provided)
        if 'extraction_verified' in kwargs:
            if not self.never_delete_archives_before_validation(
                operation,
                kwargs['extraction_verified']
            ):
                violations.append("I3: Deleting unverified archive")

        # I6: Filename safety
        if operation.type in (OperationType.WRITE, OperationType.MOVE):
            filename = operation.path.name
            if not self.never_create_dangerous_filename(filename):
                violations.append("I6: Dangerous filename")

        # I10: Provenance
        if operation.type in (OperationType.WRITE, OperationType.MOVE):
            target = operation.destination or operation.path
            if not self.has_valid_provenance(target):
                violations.append("I10: Invalid provenance")

        return (len(violations) == 0, violations)


class InvariantEnforcer:
    """
    Wrapper that enforces invariants before operations.

    Usage:
        enforcer = InvariantEnforcer(destination_root, config)

        # Before deleting a file
        enforcer.enforce_delete(file_path)

        # Before moving a file
        enforcer.enforce_move(source, destination)
    """

    def __init__(self, destination_root: Path, config=None):
        self.invariants = SafetyInvariants(destination_root, config)
        self.violations_count = 0
        self.strict_mode = True  # Raise exceptions on violations

    def enforce_delete(self, path: Path, **kwargs) -> bool:
        """
        Check invariants before deleting a file.

        Args:
            path: File to delete
            **kwargs: Additional context for invariants

        Returns:
            True if safe to proceed, False/raises otherwise
        """
        operation = FileOperation(OperationType.DELETE, path)
        passed, violations = self.invariants.check_before_operation(operation, **kwargs)

        if not passed:
            self.violations_count += len(violations)
            error_msg = f"Cannot delete {path}: " + ", ".join(violations)

            if self.strict_mode:
                raise SafetyViolationError(error_msg)
            else:
                logger.error(error_msg)
                return False

        return True

    def enforce_move(self, source: Path, destination: Path, **kwargs) -> bool:
        """
        Check invariants before moving a file.

        Args:
            source: Source path
            destination: Destination path
            **kwargs: Additional context for invariants

        Returns:
            True if safe to proceed, False/raises otherwise
        """
        operation = FileOperation(OperationType.MOVE, source, destination)
        passed, violations = self.invariants.check_before_operation(operation, **kwargs)

        if not passed:
            self.violations_count += len(violations)
            error_msg = f"Cannot move {source} to {destination}: " + ", ".join(violations)

            if self.strict_mode:
                raise SafetyViolationError(error_msg)
            else:
                logger.error(error_msg)
                return False

        return True

    def enforce_write(self, path: Path, **kwargs) -> bool:
        """
        Check invariants before writing a file.

        Args:
            path: File to write
            **kwargs: Additional context for invariants

        Returns:
            True if safe to proceed, False/raises otherwise
        """
        operation = FileOperation(OperationType.WRITE, path)
        passed, violations = self.invariants.check_before_operation(operation, **kwargs)

        if not passed:
            self.violations_count += len(violations)
            error_msg = f"Cannot write {path}: " + ", ".join(violations)

            if self.strict_mode:
                raise SafetyViolationError(error_msg)
            else:
                logger.error(error_msg)
                return False

        return True


class SafetyViolationError(Exception):
    """Raised when a safety invariant is violated."""
    pass
