"""
Archive processing for Unpackr.
Handles RAR extraction and PAR2 repair operations.
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.safety import SubprocessSafety, SafetyLimits, LoopSafety
from utils.system_check import SystemCheck


class ArchiveProcessor:
    """Handles archive extraction and repair operations."""
    
    def __init__(self, config=None):
        """Initialize the archive processor."""
        self.config = config or {}
        self.system_check = SystemCheck(config)
    
    def process_rar_files(self, folder: Path, progress_callback=None) -> bool:
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
            all_rar_files = list(folder.glob('*.rar'))
            rar_files = []
            for rar in all_rar_files:
                name_lower = rar.name.lower()
                # Skip .part002 and higher - only extract .part001 or non-part RARs
                if '.part' in name_lower:
                    if '.part001.' in name_lower or '.part01.' in name_lower or '.part1.' in name_lower:
                        rar_files.append(rar)
                else:
                    rar_files.append(rar)

            # Find 7z files - only .7z or .7z.001 (7z auto-handles .7z.002+)
            sevenz_files = list(folder.glob('*.7z')) + list(folder.glob('*.7z.001'))
            archive_files = rar_files + sevenz_files

            if not archive_files:
                return True  # No archive files to process

            # Safety: limit number of archive files
            loop_limit = getattr(self.config, 'archive_extraction_loop_limit', 100)
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
                    sevenzip_cmd = self.system_check.get_tool_command('7z')
                    if not sevenzip_cmd:
                        sevenzip_cmd = ['7z']

                    # Log start time for this archive
                    start_time = time.time()

                    # Use safe subprocess with timeout
                    success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                        sevenzip_cmd + ['x', str(archive_file), f'-o{folder}', '-aoa'],
                        timeout=SafetyLimits.RAR_EXTRACTION_TIMEOUT,
                        cwd=folder,
                        operation=f"Archive extraction: {archive_file.name}"
                    )

                    elapsed = time.time() - start_time

                    if success:
                        success_count += 1
                        speed_mbps = file_size_mb / elapsed if elapsed > 0 else 0
                        logging.info(f"Extracted {archive_file.name} ({file_size_mb:.1f}MB in {elapsed:.1f}s, {speed_mbps:.1f}MB/s)")
                    else:
                        logging.error(f"Archive extraction failed for {archive_file}:\nStdout: {stdout}\nStderr: {stderr}")

                except Exception as e:
                    logging.error(f"Error extracting {archive_file}: {e}")

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
            logging.error(f"Unexpected error during RAR extraction for {folder}: {e}")
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
            par2_files = list(folder.glob('*.par2'))

            if not par2_files:
                return True  # No PAR2 files to process

            # Use the first PAR2 file found (usually the main one)
            par2_file = par2_files[0]

            # Get par2 command from config
            par2_cmd = self.system_check.get_tool_command('par2')
            if not par2_cmd:
                par2_cmd = ['par2']

            # Count PAR2 files for display
            par2_count = len(par2_files)
            total_par2_size = sum(p.stat().st_size for p in par2_files) / (1024 * 1024)

            # Run repair (will verify first, only repair if needed - faster!)
            logging.info(f"PAR2 verify/repair: {par2_file.name} ({par2_count} files, {total_par2_size:.1f}MB)")

            start_time = time.time()
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                par2_cmd + ['r', str(par2_file)],
                timeout=SafetyLimits.PAR2_REPAIR_TIMEOUT,
                cwd=folder,
                operation=f"PAR2 repair: {par2_file.name}"
            )
            elapsed = time.time() - start_time

            if success:
                # Files OK (either no repair needed or repair succeeded)
                # Check if repair was actually done by looking for "repaired" in output
                if "repaired successfully" in stdout.lower() or "repaired successfully" in stderr.lower():
                    logging.info(f"PAR2 repair completed in {elapsed:.1f}s for {folder}")
                else:
                    logging.info(f"PAR2 verification passed (no repair needed) in {elapsed:.1f}s for {folder}")
                self._delete_files_by_extension(folder, '.par2')
                return True
            else:
                # Repair failed - archives are corrupted beyond repair
                logging.error(f"PAR2 repair FAILED after {elapsed:.1f}s for {folder} - deleting corrupted archives")
                logging.error(f"Output:\nStdout: {stdout[:500]}\nStderr: {stderr[:500]}")

                # Delete PAR2 files
                self._delete_files_by_extension(folder, '.par2')

                # Delete archive files (they're corrupted)
                self._delete_archive_files(folder)

                return False

        except Exception as e:
            logging.error(f"Unexpected error during PAR2 processing for {folder}: {e}")
            return False
    
    def _delete_archive_files(self, folder: Path):
        """Delete RAR, 7z and related archive files."""
        # Delete .rar files
        self._delete_files_by_extension(folder, '.rar')

        # Delete split RAR files (.r00, .r01, etc.)
        for i in range(100):
            ext = f'.r{str(i).zfill(2)}'
            self._delete_files_by_extension(folder, ext)

        # Delete .7z files
        self._delete_files_by_extension(folder, '.7z')

        # Delete split 7z files (.7z.001, .7z.002, etc.)
        for i in range(1, 100):
            ext = f'.7z.{str(i).zfill(3)}'
            self._delete_files_by_extension(folder, ext)
    
    def _delete_files_by_extension(self, folder: Path, extension: str):
        """
        Delete all files with the given extension in the folder with retry logic.

        Args:
            folder: Path to folder
            extension: File extension to delete (e.g., '.rar')
        """
        for file in folder.glob('*' + extension):
            # Try deleting with retries for locked files
            for attempt in range(3):
                try:
                    file.unlink()
                    logging.info(f"Deleted file: {file}")
                    break  # Success
                except PermissionError as e:
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
