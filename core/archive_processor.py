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


class ArchiveProcessor:
    """Handles archive extraction and repair operations."""
    
    def __init__(self):
        """Initialize the archive processor."""
        pass
    
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
            
            if not rar_files:
                return True  # No RAR files to process
            
            # Safety: limit number of RAR files
            loop_guard = LoopSafety(100, "RAR extraction loop")
            
            for rar_file in rar_files:
                if not loop_guard.tick():
                    logging.error(f"RAR extraction loop safety triggered in {folder}")
                    break
                
                try:
                    # Use safe subprocess with timeout
                    success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                        ['7z', 'x', str(rar_file), f'-o{folder}', '-aoa'],
                        timeout=SafetyLimits.RAR_EXTRACTION_TIMEOUT,
                        cwd=folder,
                        operation=f"RAR extraction: {rar_file.name}"
                    )
                    
                    if not success:
                        logging.error(f"RAR extraction failed for {rar_file}:\nStdout: {stdout}\nStderr: {stderr}")
                        
                except Exception as e:
                    logging.error(f"Error extracting {rar_file}: {e}")
            
            # Delete RAR files after extraction attempt
            self._delete_archive_files(folder)
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
            
            # Use safe subprocess with timeout
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ['par2', 'r', str(par2_file)],
                timeout=SafetyLimits.PAR2_REPAIR_TIMEOUT,
                cwd=folder,
                operation=f"PAR2 repair: {par2_file.name}"
            )
            
            if not success:
                logging.error(f"PAR2 processing failed for {folder}:\nStdout: {stdout}\nStderr: {stderr}")
            
            # Delete PAR2 files irrespective of the result
            self._delete_files_by_extension(folder, '.par2')
            return True
            
        except Exception as e:
            logging.error(f"Unexpected error during PAR2 processing for {folder}: {e}")
            return False
    
    def _delete_archive_files(self, folder: Path):
        """Delete RAR and related archive files."""
        # Delete .rar files
        self._delete_files_by_extension(folder, '.rar')
        
        # Delete split RAR files (.r00, .r01, etc.)
        for i in range(100):
            ext = f'.r{str(i).zfill(2)}'
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
