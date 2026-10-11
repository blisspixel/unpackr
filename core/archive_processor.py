"""
Archive processing for Unpackr.
Handles RAR extraction and PAR2 repair operations.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.safety_invariants import InvariantEnforcer
from utils.defensive import StateValidator
from utils.error_messages import log_error
from utils.filesystem_policy import containment_violation
from utils.safety import LoopSafety, ProcessTracker, SafetyLimits, SubprocessSafety
from utils.system_check import SystemCheck

_SPLIT_7Z = re.compile(r"^(?P<base>.+\.7z)\.(?P<num>\d{3})$", re.IGNORECASE)
_RAR_PART = re.compile(r"^(?P<base>.+)\.part(?P<num>\d+)\.rar$", re.IGNORECASE)
_RAR_OLD_VOLUME = re.compile(r"^(?P<base>.+)\.r(?P<num>\d{2})$", re.IGNORECASE)
_ZIP_VOLUME = re.compile(r"^(?P<base>.+)\.z(?P<num>\d{2})$", re.IGNORECASE)

# Outcomes that leave the archive volumes in place so the user can fix and retry.
HELD_STATUSES = ("held",)


@dataclass
class ArchiveSet:
    """One logical archive: a single file or a numbered multi-volume set."""

    name: str
    kind: str
    volumes: List[Path] = field(default_factory=list)
    first: Optional[Path] = None
    missing: List[str] = field(default_factory=list)


@dataclass
class ArchiveOutcome:
    """What happened to one archive set during a run.

    status is "extracted", "held" (kept for the user to fix and retry),
    "blocked" (unsafe contents) or "failed" (damaged; treated as junk).
    """

    name: str
    status: str
    reason_code: str
    detail: str
    volumes: List[Path] = field(default_factory=list)


def _volume_gaps(numbers: List[int], start: int) -> List[int]:
    if not numbers:
        return []
    present = set(numbers)
    return [n for n in range(start, max(numbers) + 1) if n not in present]


def find_archive_sets(folder: Path) -> List[ArchiveSet]:
    """Group the archive files in a folder into sets and report missing volumes.

    Recognizes plain ``.7z`` and ``.rar`` files, split 7z sets (``.7z.001``),
    RAR part sets (``.part01.rar``) and old-style RAR sets (``.rar`` + ``.r00``).
    Missing volumes are reported for gaps in the numbering and for a missing
    first volume; a missing final volume cannot be seen from names alone.
    """
    try:
        files = sorted(f for f in folder.iterdir() if f.is_file())
    except OSError:
        return []

    split_7z: Dict[str, Dict[int, Path]] = {}
    rar_parts: Dict[str, Dict[int, Tuple[Path, int]]] = {}
    old_rar_volumes: Dict[str, Dict[int, Path]] = {}
    plain_rar: Dict[str, Path] = {}
    zip_volumes: Dict[str, Dict[int, Path]] = {}
    zip_heads: Dict[str, Path] = {}
    sets: List[ArchiveSet] = []

    for f in files:
        name = f.name
        lower = name.lower()
        m = _SPLIT_7Z.match(name)
        if m:
            split_7z.setdefault(m.group("base"), {})[int(m.group("num"))] = f
            continue
        m = _RAR_PART.match(name)
        if m:
            rar_parts.setdefault(m.group("base"), {})[int(m.group("num"))] = (f, len(m.group("num")))
            continue
        m = _RAR_OLD_VOLUME.match(name)
        if m:
            old_rar_volumes.setdefault(m.group("base"), {})[int(m.group("num"))] = f
            continue
        m = _ZIP_VOLUME.match(name)
        if m:
            zip_volumes.setdefault(m.group("base"), {})[int(m.group("num"))] = f
            continue
        if lower.endswith(".zip"):
            zip_heads[name[:-4]] = f
            continue
        if lower.endswith(".7z"):
            sets.append(ArchiveSet(name=name, kind="7z", volumes=[f], first=f))
        elif lower.endswith(".rar"):
            plain_rar[name[:-4]] = f

    for base, vols in split_7z.items():
        nums = sorted(vols)
        missing = [f"{base}.{n:03d}" for n in _volume_gaps(nums, 1)]
        sets.append(
            ArchiveSet(
                name=base,
                kind="7z-split",
                volumes=[vols[n] for n in nums],
                first=vols.get(1),
                missing=missing,
            )
        )

    for base, parts in rar_parts.items():
        nums = sorted(parts)
        width = parts[nums[0]][1]
        missing = [f"{base}.part{n:0{width}d}.rar" for n in _volume_gaps(nums, 1)]
        first = parts[1][0] if 1 in parts else None
        sets.append(
            ArchiveSet(
                name=f"{base}.rar",
                kind="rar-parts",
                volumes=[parts[n][0] for n in nums],
                first=first,
                missing=missing,
            )
        )

    for base, head in plain_rar.items():
        vols = old_rar_volumes.pop(base, {})
        nums = sorted(vols)
        missing = [f"{base}.r{n:02d}" for n in _volume_gaps(nums, 0)]
        sets.append(
            ArchiveSet(
                name=head.name,
                kind="rar" if not vols else "rar-volumes",
                volumes=[head] + [vols[n] for n in nums],
                first=head,
                missing=missing,
            )
        )

    # Spanned zip: data.z01, data.z02 ... with data.zip as the last volume (7-Zip opens the .zip).
    for base, head in zip_heads.items():
        vols = zip_volumes.pop(base, {})
        nums = sorted(vols)
        missing = [f"{base}.z{n:02d}" for n in _volume_gaps(nums, 1)]
        sets.append(
            ArchiveSet(
                name=head.name,
                kind="zip" if not vols else "zip-spanned",
                volumes=[vols[n] for n in nums] + [head],
                first=head,
                missing=missing,
            )
        )
    for base, vols in zip_volumes.items():
        nums = sorted(vols)
        missing = [f"{base}.z{n:02d}" for n in _volume_gaps(nums, 1)] + [f"{base}.zip"]
        sets.append(
            ArchiveSet(name=f"{base}.zip", kind="zip-spanned", volumes=[vols[n] for n in nums], missing=missing)
        )

    # .rNN volumes whose .rar head is missing
    for base, vols in old_rar_volumes.items():
        nums = sorted(vols)
        missing = [f"{base}.rar"] + [f"{base}.r{n:02d}" for n in _volume_gaps(nums, 0)]
        sets.append(
            ArchiveSet(name=f"{base}.rar", kind="rar-volumes", volumes=[vols[n] for n in nums], missing=missing)
        )

    return sorted(sets, key=lambda s: s.name.lower())


def classify_extract_failure(stdout: str, stderr: str, code: int, timeout: int) -> Tuple[str, str, str]:
    """Map a failed 7z extraction to (status, reason_code, detail)."""
    text = f"{stdout}\n{stderr}".lower()
    if "timeout" in text:
        return "held", "archive_timeout", f"Operation timed out after {timeout}s"
    if "password" in text or "wrong password" in text:
        return "held", "archive_password", "Archive is password-protected"
    if any(k in text for k in ("missing volume", "unexpected end of archive", "unavailable data", "is not archive")):
        return "held", "archive_incomplete", "Archive is incomplete (a volume is missing or cut short)"
    if any(k in text for k in ("crc failed", "data error", "corrupt", "broken", "headers error")):
        return "failed", "archive_corrupt", "Archive data is damaged (CRC or data error)"
    if "cannot find" in text or "can not open" in text:
        return "held", "archive_unreadable", "Archive file not accessible"
    return "held", "archive_extract_failed", f"7z returned error code {code}"


class ArchiveProcessor:
    """Handles archive extraction and repair operations."""

    def __init__(
        self,
        config: Any = None,
        destination_root: Path | None = None,
        process_tracker: ProcessTracker | None = None,
    ) -> None:
        """Initialize the archive processor.

        Args:
            config: Configuration object
            destination_root: Root destination for safety invariants
            process_tracker: Object with 'active_process' attribute for cancellation support
        """
        self.config = config or {}
        self.system_check = SystemCheck(config)
        self.process_tracker = process_tracker
        self.enforcer = None
        if destination_root:
            self.enforcer = InvariantEnforcer(destination_root, config)
        self.last_outcomes: List[ArchiveOutcome] = []
        self._last_path_check = "archive_unsafe_paths"
        # Optional Remover (quarantine, trash or permanent delete); permanent without one.
        self.remover: Any = None

    @staticmethod
    def describe_missing(missing: List[str], limit: int = 3) -> str:
        shown = ", ".join(missing[:limit])
        more = len(missing) - limit
        return f"{shown} and {more} more" if more > 0 else shown

    def process_rar_files(
        self,
        folder: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> bool:
        """
        Extract RAR files in the given folder.

        Args:
            folder: Path to folder containing RAR files
            progress_callback: Optional callback(current, total, message)

        Returns:
            True if processing completed successfully, False otherwise
        """
        self.last_outcomes = []
        try:
            archive_sets = find_archive_sets(folder)
            if not archive_sets:
                return True  # No archive files to process

            # Safety: limit number of archive sets
            loop_limit = getattr(self.config, "archive_extraction_loop_limit", 100)
            loop_guard = LoopSafety(loop_limit, "Archive extraction loop")
            success_count = 0
            total_count = len(archive_sets)

            for idx, archive_set in enumerate(archive_sets, 1):
                if progress_callback:
                    progress_callback(idx, total_count, f"Extracting: {archive_set.name[:50]}")

                if not loop_guard.tick():
                    logging.error(f"Archive extraction loop safety triggered in {folder}")
                    break

                outcome = self._process_archive_set(archive_set, folder)
                self.last_outcomes.append(outcome)
                if outcome.status == "extracted":
                    success_count += 1
                    # Only a set that extracted cleanly is removed; anything else stays for review.
                    self._delete_volumes(outcome.volumes)

            if success_count == 0:
                logging.warning(f"All {total_count} archive extractions failed in {folder}")
                return False
            if success_count < total_count:
                logging.warning(f"Partial extraction: {success_count}/{total_count} archives succeeded in {folder}")
                return True
            logging.info(f"All {total_count} archives extracted successfully in {folder}")
            return True

        except Exception as e:
            log_error(
                what_failed="Archive processing failed",
                reason=str(e),
                action="Check folder permissions and disk space",
                location=folder,
            )
            return False

    def _process_archive_set(self, archive_set: ArchiveSet, folder: Path) -> ArchiveOutcome:
        """Extract one archive set and report what happened to it."""

        def outcome(status: str, code: str, detail: str) -> ArchiveOutcome:
            return ArchiveOutcome(archive_set.name, status, code, detail, list(archive_set.volumes))

        if archive_set.missing or archive_set.first is None:
            missing = self.describe_missing(archive_set.missing)
            if archive_set.kind == "7z-split":
                logging.warning(f"Incomplete 7z archive detected in {folder}: {archive_set.name} (missing {missing})")
            log_error(
                what_failed=f"Incomplete archive set: {archive_set.name}",
                reason=f"Missing volume(s): {missing}",
                action="Download the missing volume(s) and run again; the other volumes were kept",
                location=folder,
            )
            return outcome("held", "archive_volume_missing", f"missing {missing}")

        archive_file = archive_set.first
        try:
            sevenzip_cmd = self.system_check.get_tool_command("7z")
            if not sevenzip_cmd:
                logging.error("7-Zip executable unavailable or configured with an unsafe relative path")
                return outcome("held", "tool_missing", "7-Zip unavailable")

            start_time = time.time()
            try:
                file_size_bytes = sum(v.stat().st_size for v in archive_set.volumes)
            except OSError:
                file_size_bytes = 0
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Check disk space before extraction (archives typically expand 1.5-3x)
            required_space_mb = int(file_size_mb * 3)
            if not StateValidator.check_disk_space(folder, required_mb=required_space_mb):
                import shutil

                available = shutil.disk_usage(folder).free / (1024 * 1024)
                log_error(
                    what_failed=f"Cannot extract {archive_file.name}",
                    reason=f"Disk full (need {required_space_mb}MB, have {int(available)}MB)",
                    action="Free up space or skip this file",
                    location=folder,
                )
                return outcome("held", "disk_space_low", f"need {required_space_mb}MB")

            # SECURITY: Check archive contents for path traversal before extraction
            self._last_path_check = "archive_unsafe_paths"
            if not self._validate_archive_paths(archive_file, folder, sevenzip_cmd):
                if self._last_path_check == "archive_unlistable":
                    log_error(
                        what_failed=f"Could not read {archive_file.name}",
                        reason="7-Zip could not list the archive (a volume is missing, it is damaged, or it is password-protected)",
                        action="Check the download is complete; the volumes were kept",
                        location=archive_file.parent,
                    )
                    return outcome("held", "archive_unlistable", "7-Zip could not list the archive")
                log_error(
                    what_failed=f"SECURITY: Blocked {archive_file.name}",
                    reason="Archive contains unsafe paths (path traversal attempt)",
                    action="Do not extract this archive - it may be malicious",
                    location=archive_file.parent,
                )
                return outcome("blocked", "archive_unsafe_paths", "entries would extract outside the folder")

            extraction_timeout = SafetyLimits.calculate_rar_timeout(file_size_bytes)
            if extraction_timeout > SafetyLimits.RAR_EXTRACTION_TIMEOUT:
                logging.info(f"Using extended timeout {extraction_timeout}s for large archive ({file_size_mb:.1f}MB)")

            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                sevenzip_cmd + ["x", str(archive_file), f"-o{folder}", "-aoa"],
                timeout=extraction_timeout,
                cwd=folder,
                operation=f"Archive extraction: {archive_file.name}",
                use_temp_files=True,
                process_tracker=self.process_tracker,
            )
            elapsed = time.time() - start_time

            if success:
                speed_mbps = file_size_mb / elapsed if elapsed > 0 else 0
                logging.info(
                    f"Extracted {archive_file.name} ({file_size_mb:.1f}MB in {elapsed:.1f}s, {speed_mbps:.1f}MB/s)"
                )
                return outcome("extracted", "archive_extracted", f"{file_size_mb:.1f}MB in {elapsed:.1f}s")

            status, reason_code, reason = classify_extract_failure(stdout or "", stderr or "", code, extraction_timeout)
            log_error(
                what_failed=f"Failed to extract {archive_file.name}",
                reason=reason,
                action="Check if archive is complete, not password-protected, and not corrupted",
                location=archive_file.parent,
                details=stderr[:300] if stderr else None,
            )
            return outcome(status, reason_code, reason)

        except Exception as e:
            log_error(
                what_failed=f"Unexpected error extracting {archive_file.name}",
                reason=str(e),
                action="Check archive file is accessible and not locked by another process",
                location=archive_file.parent,
            )
            return outcome("held", "archive_extract_error", str(e)[:200])

    def _delete_volumes(self, volumes: List[Path]) -> None:
        """Delete the volumes of one successfully extracted set."""
        for volume in volumes:
            self._delete_path(volume)

    def process_par2_files(self, folder: Path) -> bool:
        """
        Verify and repair files using PAR2 in the given folder.
        Uses par2 'r' (repair) command which automatically verifies first,
        then only repairs if needed. Faster than separate verify + repair.

        Strategy:
        1. Run repair (auto-verifies, only repairs if needed)
        2. If successful (verified OK or repaired OK), delete PAR2 files
        3. If repair fails, delete both PAR2 and archive files (corrupted beyond repair)

        Args:
            folder: Path to folder containing PAR2 files

        Returns:
            True if files are OK (no repair needed or repair succeeded)
            False if repair failed (archives corrupted beyond repair)
        """
        try:
            par2_files = list(folder.glob("*.par2"))

            if not par2_files:
                return True  # No PAR2 files to process

            # Use the first PAR2 file found (usually the main one)
            par2_file = par2_files[0]

            # Get par2 command from config
            par2_cmd = self.system_check.get_tool_command("par2")
            if not par2_cmd:
                logging.warning("PAR2 executable unavailable or configured with an unsafe relative path")
                return False

            # Count PAR2 files and calculate total size for timeout calculation
            par2_count = len(par2_files)
            total_par2_size_bytes = sum(p.stat().st_size for p in par2_files)
            total_par2_size_mb = total_par2_size_bytes / (1024 * 1024)

            # PERFORMANCE: Calculate dynamic timeout based on PAR2 file sizes (handles large repairs)
            par2_timeout = SafetyLimits.calculate_par2_timeout(total_par2_size_bytes)
            if par2_timeout > SafetyLimits.PAR2_REPAIR_TIMEOUT:
                logging.info(f"Using extended timeout {par2_timeout}s for large PAR2 set ({total_par2_size_mb:.1f}MB)")

            # Run repair (will verify first, only repair if needed - faster!)
            logging.info(f"PAR2 verify/repair: {par2_file.name} ({par2_count} files, {total_par2_size_mb:.1f}MB)")

            start_time = time.time()
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                par2_cmd + ["r", str(par2_file)],
                timeout=par2_timeout,
                cwd=folder,
                operation=f"PAR2 repair: {par2_file.name}",
                use_temp_files=True,  # PAR2 can output large amounts of data, use temp files
                process_tracker=self.process_tracker,
            )
            elapsed = time.time() - start_time

            # Check for failure indicators FIRST (par2 can return 0 even on failure sometimes)
            combined_output = (stdout + stderr).lower()
            failure_keywords = [
                "repair failed",
                "repair is impossible",
                "cannot repair",
                "repair is not possible",
                "insufficient",
                "damaged beyond repair",
                "fatal error",
                "could not repair",
            ]

            # Check if repair explicitly failed
            repair_failed = any(keyword in combined_output for keyword in failure_keywords)

            if repair_failed or (not success and code != 0):
                # Repair failed - archives are corrupted beyond repair
                log_error(
                    what_failed="PAR2 repair failed",
                    reason=f"Archives are corrupted beyond repair (completed in {elapsed:.1f}s)",
                    action="Download missing PAR2 files or re-download archives",
                    location=folder,
                    details=f"Exit code: {code}\nStdout: {stdout[:300]}\nStderr: {stderr[:300]}",
                )

                # Delete PAR2 files
                self._delete_files_by_extension(folder, ".par2")

                # Delete archive files (they're corrupted)
                self._delete_archive_files(folder)

                return False

            # Check for success indicators
            if success:
                # Check if repair was actually done by looking for "repaired" in output
                if "repaired successfully" in combined_output or "repair complete" in combined_output:
                    logging.info(f"PAR2 repair completed successfully in {elapsed:.1f}s for {folder}")
                elif "all files are correct" in combined_output or "no repair" in combined_output:
                    logging.info(f"PAR2 verification passed (no repair needed) in {elapsed:.1f}s for {folder}")
                else:
                    # Success exit code but unclear output - assume OK
                    logging.info(f"PAR2 verification/repair finished in {elapsed:.1f}s for {folder}")

                self._delete_files_by_extension(folder, ".par2")
                return True

            # Timeout or unknown error
            log_error(
                what_failed="PAR2 operation failed",
                reason="Operation timed out or returned unexpected error",
                action="Check if PAR2 files are valid and archives are accessible",
                location=folder,
            )
            return False

        except Exception as e:
            log_error(
                what_failed="PAR2 processing failed",
                reason=str(e),
                action="Check folder permissions and PAR2 file validity",
                location=folder,
            )
            return False

    def _delete_archive_files(self, folder: Path) -> None:
        """Delete RAR, 7z and related archive files."""
        # Delete .rar files
        self._delete_files_by_extension(folder, ".rar")

        # Delete split RAR files (.r00, .r01, etc.)
        for i in range(100):
            ext = f".r{str(i).zfill(2)}"
            self._delete_files_by_extension(folder, ext)

        # Delete .7z files
        self._delete_files_by_extension(folder, ".7z")

        # Delete split 7z files (.7z.001, .7z.002, etc.)
        for i in range(1, 100):
            ext = f".7z.{str(i).zfill(3)}"
            self._delete_files_by_extension(folder, ext)

    def _delete_files_by_extension(self, folder: Path, extension: str) -> None:
        """
        Delete all files with the given extension in the folder with retry logic.

        Args:
            folder: Path to folder
            extension: File extension to delete (e.g., '.rar')
        """
        for file in folder.glob("*" + extension):
            self._delete_path(file)

    def _delete_path(self, file: Path) -> None:
        """Delete one archive-related file with invariant checks and lock retries."""
        # Safety check: enforce invariants before deletion if enforcer is configured
        if self.enforcer:
            try:
                # Callers only delete volumes of a set that extracted, or of a set PAR2 could not repair.
                self.enforcer.enforce_delete(file, extraction_verified=True)
            except Exception as e:
                logging.error(f"Safety check prevented deletion of {file}: {e}")
                return

        # Try deleting with retries for locked files
        for attempt in range(3):
            try:
                if self.remover is not None:
                    self.remover.remove(file, "archive_cleanup")
                else:
                    file.unlink()
                logging.info(f"Removed file: {file}")
                break  # Success
            except PermissionError:
                if attempt < 2:
                    # File is locked, wait and retry
                    logging.warning(f"File locked (attempt {attempt + 1}/3): {file}")
                    time.sleep(1)
                elif self.remover is not None and self.remover.mode != "permanent":
                    logging.error(f"Could not {self.remover.mode} locked file {file} after 3 attempts")
                else:
                    # Final attempt failed - try forcing via unlink with missing_ok
                    try:
                        file.unlink(missing_ok=True)
                        logging.info(f"Force deleted file: {file}")
                    except Exception as e2:
                        logging.error(f"Failed to delete locked file {file} after 3 attempts: {e2}")
            except Exception as e:
                logging.error(f"Failed to delete file {file}: {e}")
                break

    def _validate_archive_paths(self, archive_file: Path, target_folder: Path, sevenzip_cmd: list) -> bool:
        """
        Validate all paths in archive to prevent path traversal attacks.

        SECURITY: Checks that all files in the archive would extract to within target_folder.
        Rejects archives containing:
        - Absolute paths (C:\\, /, etc.)
        - Parent directory references (../)
        - Symbolic links pointing outside target

        Args:
            archive_file: Archive file to validate
            target_folder: Intended extraction directory
            sevenzip_cmd: 7z command to use for listing

        Returns:
            True if archive is safe to extract, False if malicious paths detected
        """
        try:
            # SECURITY: Stream the full 7z listing line-by-line so we cannot miss
            # entries hidden in the middle of a multi-megabyte listing. The previous
            # implementation relied on a 64 KiB head/tail sample, which an attacker
            # could exploit by inflating the listing to hide an unsafe entry in the
            # truncated middle (see _read_bounded_text in utils/safety.py).
            target_folder_resolved = target_folder.resolve()
            unsafe: dict[str, str] = {}

            def check_line(line: str) -> bool:
                # Skip blank/header/footer lines.
                stripped = line.strip()
                if not stripped or "---" in line or "Date" in line or "Path" in line:
                    return True

                # 7z list format: Date Time Attr Size CompSize Path
                parts = line.split()
                if len(parts) < 6:
                    return True

                file_path = " ".join(parts[5:])
                if not file_path:
                    return True

                reason = containment_violation(file_path, target_folder_resolved)
                if reason:
                    unsafe["reason"] = reason
                    return False
                return True

            success, _, code = SubprocessSafety.run_with_line_handler(
                sevenzip_cmd + ["l", str(archive_file)],
                timeout=30,  # Listing should be fast
                line_handler=check_line,
                operation=f"Archive path validation: {archive_file.name}",
            )

            if unsafe:
                logging.error(f"SECURITY: Archive contains {unsafe['reason']}")
                return False

            if not success or code != 0:
                logging.warning(f"Could not list archive contents for {archive_file.name} - not extracting")
                self._last_path_check = "archive_unlistable"
                return False

            # Every line in the full (untruncated) listing passed validation.
            return True

        except Exception as e:
            logging.error(f"Error validating archive paths for {archive_file.name}: {e}")
            self._last_path_check = "archive_unlistable"
            return False  # Fail closed on errors
