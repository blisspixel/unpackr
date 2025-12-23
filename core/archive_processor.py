"""
Archive processing for Unpackr.
Handles RAR extraction and PAR2 repair operations.
"""

import logging
import subprocess
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
    
    def process_rar_files(self, folder: Path) -> bool:
        """
        Extract RAR files in the given folder.
        
        Args:
            folder: Path to folder containing RAR files
            
        Returns:
            True if processing completed successfully, False otherwise
        """
        try:
            rar_files = list(folder.glob('*.rar'))
            sevenz_files = list(folder.glob('*.7z')) + list(folder.glob('*.7z.001'))
            archive_files = rar_files + sevenz_files

            if not archive_files:
                return True  # No archive files to process

            # Safety: limit number of archive files
            loop_limit = getattr(self.config, 'archive_extraction_loop_limit', 100)
            loop_guard = LoopSafety(loop_limit, "Archive extraction loop")
            success_count = 0
            total_count = len(archive_files)

            for archive_file in archive_files:
                if not loop_guard.tick():
                    logging.error(f"RAR extraction loop safety triggered in {folder}")
                    break

                try:
                    # Get 7z command from config
                    sevenzip_cmd = self.system_check.get_tool_command('7z')
                    if not sevenzip_cmd:
                        sevenzip_cmd = ['7z']

                    # Use safe subprocess with timeout
                    success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                        sevenzip_cmd + ['x', str(archive_file), f'-o{folder}', '-aoa'],
                        timeout=SafetyLimits.RAR_EXTRACTION_TIMEOUT,
                        cwd=folder,
                        operation=f"Archive extraction: {archive_file.name}"
                    )

                    if success:
                        success_count += 1
                        logging.info(f"Successfully extracted {archive_file.name}")
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
        Repair files using PAR2 in the given folder.
        
        Args:
            folder: Path to folder containing PAR2 files
            
        Returns:
            True if processing completed successfully, False otherwise
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
            
            # Use safe subprocess with timeout
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                par2_cmd + ['r', str(par2_file)],
                timeout=SafetyLimits.PAR2_REPAIR_TIMEOUT,
                cwd=folder,
                operation=f"PAR2 repair: {par2_file.name}"
            )

            # Delete PAR2 files irrespective of the result
            self._delete_files_by_extension(folder, '.par2')

            if success:
                logging.info(f"PAR2 repair completed successfully for {folder}")
                return True
            else:
                logging.error(f"PAR2 processing failed for {folder}:\nStdout: {stdout}\nStderr: {stderr}")
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
        Delete all files with the given extension in the folder.
        
        Args:
            folder: Path to folder
            extension: File extension to delete (e.g., '.rar')
        """
        for file in folder.glob('*' + extension):
            try:
                file.unlink()
                logging.info(f"Deleted file: {file}")
            except Exception as e:
                logging.error(f"Failed to delete file {file}: {e}")
