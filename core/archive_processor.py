"""
Archive processing for Unpackr.
Handles RAR extraction and PAR2 repair operations.
"""

import logging
import time
from pathlib import Path
from typing import Any, Callable

from core.safety_invariants import InvariantEnforcer
from utils.defensive import StateValidator
from utils.error_messages import log_error
from utils.safety import LoopSafety, ProcessTracker, SafetyLimits, SubprocessSafety
from utils.system_check import SystemCheck


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
        try:
            # Find RAR files - only process .part001.rar or .rar (not .part002+)
            all_rar_files = list(folder.glob("*.rar"))
            rar_files = []
            for rar in all_rar_files:
                name_lower = rar.name.lower()
                # Skip .part002 and higher - only extract .part001 or non-part RARs
                if ".part" in name_lower:
                    if ".part001." in name_lower or ".part01." in name_lower or ".part1." in name_lower:
                        rar_files.append(rar)
                else:
                    rar_files.append(rar)

            # Find 7z files - only .7z or .7z.001 (7z auto-handles .7z.002+)
            sevenz_files = list(folder.glob("*.7z")) + list(folder.glob("*.7z.001"))

            # Check for incomplete 7z archives starting at higher part numbers (e.g., .7z.100)
            # These indicate an incomplete download and should be warned about
            all_7z_parts = list(folder.glob("*.7z.*"))
            for file in all_7z_parts:
                filename_lower = file.name.lower()
                # Look for pattern like .7z.XXX where XXX > 1
                if ".7z." in filename_lower:
                    parts = filename_lower.split(".7z.")
                    if len(parts) == 2 and parts[1].isdigit():
                        part_num = int(parts[1])
                        if part_num > 1 and not any(
                            ".7z.001" in f.name.lower() or f.name.lower().endswith(".7z") for f in all_7z_parts
                        ):
                            logging.warning(
                                f"Incomplete 7z archive detected in {folder}: {file.name} (missing parts 1-{part_num - 1})"
                            )
                            break  # Only warn once per folder

            archive_files = rar_files + sevenz_files

            if not archive_files:
                return True  # No archive files to process

            # Safety: limit number of archive files
            loop_limit = getattr(self.config, "archive_extraction_loop_limit", 100)
            loop_guard = LoopSafety(loop_limit, "Archive extraction loop")
            success_count = 0
            total_count = len(archive_files)

            for idx, archive_file in enumerate(archive_files, 1):
                # Show progress during extraction
                if progress_callback:
                    progress_callback(idx, total_count, f"Extracting: {archive_file.name[:50]}")

                if not loop_guard.tick():
                    logging.error(f"RAR extraction loop safety triggered in {folder}")
                    break

                try:
                    # Get 7z command from config
                    sevenzip_cmd = self.system_check.get_tool_command("7z")
                    if not sevenzip_cmd:
                        logging.error("7-Zip executable unavailable or configured with an unsafe relative path")
                        continue

                    # Log start time for this archive
                    start_time = time.time()

                    # Get file size before extraction (for logging, disk space check, and timeout calculation)
                    try:
                        file_size_bytes = archive_file.stat().st_size
                        file_size_mb = file_size_bytes / (1024 * 1024)
                    except OSError:
                        file_size_bytes = 0
                        file_size_mb = 0

                    # Check disk space before extraction (archives typically expand 1.5-3x)
                    # Use 3x multiplier as conservative estimate for extraction space needed
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
                        continue  # Skip this archive

                    # SECURITY: Check archive contents for path traversal before extraction
                    if not self._validate_archive_paths(archive_file, folder, sevenzip_cmd):
                        log_error(
                            what_failed=f"SECURITY: Blocked {archive_file.name}",
                            reason="Archive contains unsafe paths (path traversal attempt)",
                            action="Do not extract this archive - it may be malicious",
                            location=archive_file.parent,
                        )
                        continue  # Skip this malicious archive

                    # PERFORMANCE: Calculate dynamic timeout based on file size (handles 50GB+ archives)
                    extraction_timeout = SafetyLimits.calculate_rar_timeout(file_size_bytes)
                    if extraction_timeout > SafetyLimits.RAR_EXTRACTION_TIMEOUT:
                        logging.info(
                            f"Using extended timeout {extraction_timeout}s for large archive ({file_size_mb:.1f}MB)"
                        )

                    # Use safe subprocess with dynamic timeout
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
                        success_count += 1
                        speed_mbps = file_size_mb / elapsed if elapsed > 0 else 0
                        logging.info(
                            f"Extracted {archive_file.name} ({file_size_mb:.1f}MB in {elapsed:.1f}s, {speed_mbps:.1f}MB/s)"
                        )
                    else:
                        # Determine reason from stderr
                        reason = "Unknown error"
                        if "timeout" in stderr.lower() or "timeout" in stdout.lower():
                            reason = f"Operation timed out after {extraction_timeout}s"
                        elif "password" in stderr.lower():
                            reason = "Archive is password-protected"
                        elif "corrupt" in stderr.lower() or "broken" in stderr.lower():
                            reason = "Archive is corrupted or incomplete"
                        elif "cannot find" in stderr.lower():
                            reason = "Archive file not accessible"
                        else:
                            reason = f"7z returned error code {code}"

                        log_error(
                            what_failed=f"Failed to extract {archive_file.name}",
                            reason=reason,
                            action="Check if archive is complete, not password-protected, and not corrupted",
                            location=archive_file.parent,
                            details=stderr[:300] if stderr else None,
                        )

                except Exception as e:
                    log_error(
                        what_failed=f"Unexpected error extracting {archive_file.name}",
                        reason=str(e),
                        action="Check archive file is accessible and not locked by another process",
                        location=archive_file.parent,
                    )

            # Delete RAR files after extraction attempt
            self._delete_archive_files(folder)

            # Return True only if at least one archive extracted successfully
            if success_count == 0:
                logging.warning(f"All {total_count} archive extractions failed in {folder}")
                return False
            elif success_count < total_count:
                logging.warning(f"Partial extraction: {success_count}/{total_count} archives succeeded in {folder}")
                return True
            else:
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
            # Safety check: enforce invariants before deletion if enforcer is configured
            if self.enforcer:
                try:
                    # For archives, pass extraction_verified=True since we only call this after successful extraction
                    self.enforcer.enforce_delete(file, extraction_verified=True)
                except Exception as e:
                    logging.error(f"Safety check prevented deletion of {file}: {e}")
                    continue  # Skip this file

            # Try deleting with retries for locked files
            for attempt in range(3):
                try:
                    file.unlink()
                    logging.info(f"Deleted file: {file}")
                    break  # Success
                except PermissionError:
                    if attempt < 2:
                        # File is locked, wait and retry
                        logging.warning(f"File locked (attempt {attempt + 1}/3): {file}")
                        time.sleep(1)
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

                # Normalize separators so Windows-style archive members are judged
                # consistently on Linux/macOS (where "\\" is not a path separator).
                normalized = file_path.replace("\\", "/").strip()
                if not normalized or normalized in {".", "./"}:
                    return True

                # Absolute POSIX, Windows drive, or UNC-style members are unsafe.
                if (
                    normalized.startswith("/")
                    or normalized.startswith("//")
                    or (len(normalized) >= 3 and normalized[1] == ":" and normalized[0].isalpha())
                    or Path(file_path).is_absolute()
                    or Path(normalized).is_absolute()
                ):
                    unsafe["reason"] = f"absolute path: {file_path}"
                    return False

                member = Path(normalized)
                if ".." in member.parts:
                    unsafe["reason"] = f"parent directory reference: {file_path}"
                    return False

                try:
                    would_extract_to = (target_folder / member).resolve()
                    try:
                        would_extract_to.relative_to(target_folder_resolved)
                    except ValueError:
                        unsafe["reason"] = f"would extract outside target: {file_path} -> {would_extract_to}"
                        return False
                except Exception as e:
                    unsafe["reason"] = f"path validation error for {file_path}: {e}"
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
                logging.warning(f"Could not list archive contents for {archive_file.name} - assuming unsafe")
                return False

            # Every line in the full (untruncated) listing passed validation.
            return True

        except Exception as e:
            logging.error(f"Error validating archive paths for {archive_file.name}: {e}")
            return False  # Fail closed on errors
