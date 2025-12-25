"""
File handling operations for Unpackr.
Manages file operations, folder cleanup, and content classification.
"""

import os
import shutil
import logging
import time
import psutil
from pathlib import Path
from typing import List, Tuple, Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.defensive import InputValidator, StateValidator, ErrorRecovery, ValidationError


class FileHandler:
    """Handles file and folder operations."""
    
    def __init__(self, config, stats=None):
        """
        Initialize the file handler.

        Args:
            config: Config instance with file extensions and settings
            stats: Optional stats dict to track sanitization count
        """
        # Defensive: validate config
        if config is None:
            raise ValidationError("Config cannot be None")

        self.config = config
        self.stats = stats  # Optional stats tracking

        # Defensive: verify config has required attributes
        required_attrs = ['video_extensions', 'removable_extensions']
        for attr in required_attrs:
            if not hasattr(config, attr):
                raise ValidationError(f"Config missing required attribute: {attr}")

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by removing/replacing problematic characters.

        Handles:
        - Windows forbidden characters: < > : " / \\ | ? *
        - Unicode/Cyrillic transliteration to ASCII
        - Control characters and unicode weirdness
        - Multiple dots/spaces/underscores
        - Leading/trailing dots, spaces, underscores

        Args:
            filename: Original filename (with extension)

        Returns:
            Sanitized filename
        """
        # Split into name and extension
        path = Path(filename)
        name = path.stem
        ext = path.suffix

        # Fix misnamed video files like .mp4.1, .mkv.bak, etc.
        # Check if stem ends with a video extension
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}
        name_lower = name.lower()
        for video_ext in video_exts:
            if name_lower.endswith(video_ext):
                # file.mp4.1 -> name="file.mp4", ext=".1"
                # Change to: name="file", ext=".mp4"
                name = name[:-len(video_ext)]
                ext = video_ext
                logging.info(f"Fixed misnamed video extension: {filename} -> {name}{ext}")
                break

        # Replace forbidden Windows characters with safe alternatives
        replacements = {
            '<': '(',
            '>': ')',
            ':': '-',
            '"': "'",
            '/': '-',
            '\\': '-',
            '|': '-',
            '?': '',
            '*': '',
            '\x00': '',  # null
        }

        for bad_char, replacement in replacements.items():
            name = name.replace(bad_char, replacement)

        # Transliterate Unicode to ASCII (handle Cyrillic, accents, etc.)
        # Manual transliteration map for common characters
        transliteration_map = {
            # Cyrillic
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo', 'Ж': 'Zh',
            'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O',
            'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts',
            'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch', 'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
            'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
            'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
            'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            # Common accented characters
            'á': 'a', 'à': 'a', 'â': 'a', 'ä': 'a', 'ã': 'a', 'å': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ñ': 'n', 'ç': 'c', 'ß': 'ss',
            'Á': 'A', 'À': 'A', 'Â': 'A', 'Ä': 'A', 'Ã': 'A', 'Å': 'A',
            'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
            'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
            'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Ö': 'O', 'Õ': 'O',
            'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
            'Ñ': 'N', 'Ç': 'C',
        }

        # Apply transliteration
        transliterated = []
        for char in name:
            if char in transliteration_map:
                transliterated.append(transliteration_map[char])
            else:
                transliterated.append(char)
        name = ''.join(transliterated)

        # Filter to ASCII printable characters only
        name = ''.join(char for char in name if 32 <= ord(char) < 127)

        # Normalize multiple separators
        name = name.replace('..', '.').replace('--', '-').replace('__', '_')
        name = name.replace('  ', ' ')

        # Remove leading/trailing dots, spaces, underscores, dashes
        name = name.strip('. _-')

        # Ensure name isn't empty after sanitization (use timestamp fallback)
        if not name:
            import time
            name = f'file_{int(time.time())}'

        # Windows reserved names (CON, PRN, AUX, etc.) - add underscore suffix
        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        if name.upper() in reserved_names:
            name = name + '_'

        # Limit length (Windows MAX_PATH is 260, leave room for path)
        max_name_length = 200
        if len(name) > max_name_length:
            name = name[:max_name_length]

        return name + ext

    def find_video_files(self, folder: Path) -> List[Path]:
        """
        Recursively find video files in the given folder.
        
        Args:
            folder: Path to search
            
        Returns:
            List of paths to video files (empty list if error)
        """
        # Defensive: validate inputs
        try:
            folder = InputValidator.validate_path(folder, must_exist=True, must_be_dir=True)
        except ValidationError as e:
            logging.error(f"Invalid folder path: {e}")
            return []
        
        try:
            video_extensions = self.config.video_extensions
            
            # Defensive: validate extensions list
            if not video_extensions or not isinstance(video_extensions, list):
                logging.error("Invalid video_extensions config")
                return []
            
            # Defensive: check folder is accessible
            if not folder.exists() or not folder.is_dir():
                logging.warning(f"Folder not accessible: {folder}")
                return []

            # Only look for videos directly in this folder (not recursive)
            # Subfolders are processed separately via _process_subfolder
            return [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in video_extensions]
            
        except Exception as e:
            logging.error(f"Error finding video files in {folder}: {e}")
            return []
    
    def contains_non_video_files(self, folder: Path) -> bool:
        """
        Check if folder contains files other than video files.
        
        Args:
            folder: Path to check
            
        Returns:
            True if non-video files exist, False otherwise
        """
        all_files = [f for f in folder.rglob('*') if f.is_file()]
        video_extensions = self.config.video_extensions
        non_video_files = [f for f in all_files if f.suffix.lower() not in video_extensions]
        return len(non_video_files) > 0
    
    def contains_unwanted_files(self, folder: Path) -> bool:
        """
        Check if folder contains files other than video, PAR2, or RAR files.
        
        Args:
            folder: Path to check
            
        Returns:
            True if unwanted files exist, False otherwise
        """
        video_extensions = self.config.video_extensions
        
        for file in folder.rglob('*'):
            if file.is_file() and not (
                file.suffix.lower() in video_extensions or
                file.suffix.lower() == '.par2' or
                file.suffix.lower() == '.rar'
            ):
                return True
        return False
    
    def is_folder_empty_or_removable(self, folder: Path, par2_error: bool = False,
                                     archive_error: bool = False) -> bool:
        """
        Check if folder is empty or contains only removable files.

        Args:
            folder: Path to check
            par2_error: Whether PAR2 processing had errors
            archive_error: Whether archive extraction had errors

        Returns:
            True if folder can be safely deleted, False otherwise
        """
        removable_extensions = self.config.removable_extensions
        image_count = 0
        image_total_bytes = 0
        image_extensions = self.config.image_extensions

        for file in folder.iterdir():
            if file.is_dir():
                logging.info(f"Folder '{folder}' not deleted: contains subdirectory '{file.name}'")
                return False

            file_ext = file.suffix.lower()

            # Count image files (distinguish between single cover art vs image collection)
            if file_ext in image_extensions:
                image_count += 1
                try:
                    image_total_bytes += file.stat().st_size
                except (OSError, FileNotFoundError):
                    pass
                # Match scan logic: need both min_image_files threshold AND >10MB to be considered a collection
                # Just having 5-10 cover art images shouldn't protect the folder
                image_total_mb = image_total_bytes / (1024 * 1024)
                min_images = self.config.min_image_files
                if image_count > min_images and image_total_mb > 10:
                    logging.info(f"Folder '{folder}' not deleted: contains image collection ({image_count} images, {image_total_mb:.1f}MB)")
                    return False
                continue  # Single images and small collections (cover art) are treated as removable

            # Check if it's a removable file (junk)
            elif file_ext in removable_extensions or (file_ext.startswith('.r') and file_ext[2:].isdigit()):
                continue

            # If PAR2 processing failed, treat PAR2 files as removable junk
            elif file_ext == '.par2' and par2_error:
                continue

            # If archive extraction failed, treat archives as removable junk
            elif archive_error and (file_ext == '.rar' or file_ext == '.7z' or
                                   file_ext.startswith('.7z.') or
                                   (file_ext.startswith('.r') and file_ext[2:].isdigit())):
                continue

            else:
                logging.info(f"Folder '{folder}' not deleted: contains non-removable file '{file.name}'")
                return False

        return True
    
    def safe_delete_folder(self, folder: Path, max_attempts: int = None,
                          par2_error: bool = False, archive_error: bool = False) -> bool:
        """
        Safely delete a folder with retry logic and fallback methods.
        Handles special characters in filenames (brackets, etc.) and locked files.

        RACE CONDITION FIX: Implements double-check pattern to prevent deletion
        of folders whose contents changed between check and delete.

        Args:
            folder: Path to folder to delete
            max_attempts: Maximum number of deletion attempts (None = use config)
            par2_error: Whether PAR2 processing had errors (for double-check)
            archive_error: Whether archive extraction had errors (for double-check)

        Returns:
            True if successful, False otherwise
        """
        if max_attempts is None:
            max_attempts = getattr(self.config, 'folder_delete_max_attempts', 2)
        retry_delay = getattr(self.config, 'folder_delete_retry_delay', 5)

        # RACE CONDITION FIX: Double-check folder is still removable before deletion
        # Prevents deleting folders whose contents changed since initial check
        if not self.is_folder_empty_or_removable(folder, par2_error, archive_error):
            logging.warning(f"RACE CONDITION PREVENTED: Folder {folder} contents changed, not removable anymore")
            return False

        for attempt in range(max_attempts):
            try:
                # Try standard shutil.rmtree first
                shutil.rmtree(folder)
                logging.info(f"Successfully deleted folder {folder}")
                return True
            except PermissionError as e:
                # File is locked - try killing processes holding it
                logging.warning(f"Permission denied deleting {folder} on attempt {attempt + 1}: {e}")
                self._kill_processes_using_folder(folder)
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
            except Exception as e:
                logging.error(f"Failed to delete folder {folder} on attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)

        # Final attempt using PowerShell (handles special chars better)
        logging.info(f"Trying PowerShell force delete for {folder}")
        try:
            import subprocess
            # SECURITY FIX: Use array form to prevent command injection
            # Pass folder path as parameter, not via string interpolation
            # PowerShell's -LiteralPath handles special chars without injection risk
            result = subprocess.run(
                ['powershell', '-Command',
                 'Remove-Item', '-LiteralPath', str(folder), '-Recurse', '-Force', '-ErrorAction', 'SilentlyContinue'],
                capture_output=True,
                text=True,
                timeout=60
            )
            # Check if folder still exists
            if not folder.exists():
                logging.info(f"PowerShell successfully deleted folder {folder}")
                return True
        except Exception as e:
            logging.error(f"PowerShell delete failed for {folder}: {e}")

        logging.error(f"Could not delete folder {folder} after all attempts")
        return False

    def _kill_processes_using_folder(self, folder: Path):
        """
        Kill processes that have files open in the given folder.

        Args:
            folder: Path to folder
        """
        try:
            import psutil
            folder_str = str(folder)
            killed_pids = set()

            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    # Check if process has any files open in this folder
                    for file in proc.open_files():
                        if folder_str in file.path:
                            if proc.pid not in killed_pids:
                                logging.info(f"Killing process {proc.name()} (PID {proc.pid}) using {folder}")
                                proc.kill()
                                killed_pids.add(proc.pid)
                            break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue

            if killed_pids:
                time.sleep(2)  # Give processes time to die
        except Exception as e:
            logging.warning(f"Error killing processes for {folder}: {e}")
    
    def move_file(self, source: Path, destination_dir: Path) -> bool:
        """
        Move a file to the destination directory.
        
        Args:
            source: Path to source file
            destination_dir: Path to destination directory
            
        Returns:
            True if successful, False otherwise
        """
        # Defensive: validate inputs
        try:
            source = InputValidator.validate_path(source, must_exist=True, must_be_file=True)
            destination_dir = InputValidator.validate_path(destination_dir, must_exist=True, must_be_dir=True)
        except ValidationError as e:
            logging.error(f"Invalid path in move_file: {e}")
            return False
        
        # Defensive: check source is accessible
        if not StateValidator.check_file_accessible(source):
            logging.error(f"Source file not accessible: {source}")
            return False
        
        # Defensive: check destination is writable
        if not StateValidator.check_dir_writable(destination_dir):
            logging.error(f"Destination directory not writable: {destination_dir}")
            return False
        
        # Defensive: check disk space
        try:
            file_size_mb = source.stat().st_size / (1024 * 1024)
            if not StateValidator.check_disk_space(destination_dir, required_mb=int(file_size_mb * 1.1)):
                logging.error(f"Insufficient disk space for {source.name}")
                return False
        except Exception as e:
            logging.warning(f"Cannot check disk space: {e}")
        
        # Perform move with defensive error recovery
        try:
            # Sanitize filename before moving
            sanitized_name = self.sanitize_filename(source.name)
            destination_file = destination_dir / sanitized_name

            # Log if filename was changed
            if sanitized_name != source.name:
                logging.info(f"Sanitized filename: '{source.name}' -> '{sanitized_name}'")
                if self.stats:
                    self.stats['files_sanitized'] += 1

            # Defensive: check if destination already exists
            if destination_file.exists():
                logging.warning(f"Destination file already exists: {destination_file}")
                # Create unique name
                base = destination_file.stem
                suffix = destination_file.suffix
                counter = 1
                while destination_file.exists():
                    destination_file = destination_dir / f"{base}_{counter}{suffix}"
                    counter += 1
                logging.info(f"Using unique name: {destination_file.name}")
            
            # Use error recovery helper
            if ErrorRecovery.safe_move(source, destination_file):
                logging.info(f"Moved file: {source.name} -> {destination_file}")
                return True
            else:
                logging.error(f"Failed to move file: {source}")
                return False
                
        except Exception as e:
            logging.error(f"Error moving file {source}: {e}", exc_info=True)
            return False
    
    def delete_video_file_with_retry(self, video_file: Path, max_attempts: int = None,
                                    retry_delay: int = None) -> bool:
        """
        Delete a video file with retry logic and exponential backoff.

        Note: File lock checks (wait_for_file_release) before calling this are
        advisory only. The actual delete operation is protected by try/except
        to handle race conditions where file becomes locked between check and delete.

        Args:
            video_file: Path to video file
            max_attempts: Maximum deletion attempts (None = use config)
            retry_delay: Initial delay between attempts in seconds (None = use config)

        Returns:
            True if successful, False otherwise
        """
        if max_attempts is None:
            max_attempts = getattr(self.config, 'file_delete_max_attempts', 5)
        if retry_delay is None:
            retry_delay = getattr(self.config, 'file_delete_retry_delay', 1)

        current_delay = retry_delay

        for attempt in range(max_attempts):
            self._terminate_related_processes(str(video_file))

            try:
                if attempt > 0:
                    time.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff

                video_file.unlink(missing_ok=True)
                logging.info(f"Successfully deleted video file: {video_file}")
                return True
            except PermissionError as e:
                logging.warning(f"Attempt {attempt + 1}/{max_attempts} - File locked: {video_file}")
                # Continue retry loop with backoff
            except Exception as e:
                logging.error(f"Attempt {attempt + 1}/{max_attempts} - Error deleting {video_file}: {e}")

        logging.error(f"Failed to delete video file {video_file} after {max_attempts} attempts")
        return False
    
    def wait_for_file_release(self, file_path: str, max_attempts: int = None,
                             delay: int = None) -> bool:
        """
        Wait for a file to be released by other processes.

        Args:
            file_path: Path to file as string
            max_attempts: Maximum wait attempts (None = use config)
            delay: Delay between checks in seconds (None = use config)

        Returns:
            True if file is released, False if timeout
        """
        if max_attempts is None:
            max_attempts = getattr(self.config, 'file_lock_wait_attempts', 10)
        if delay is None:
            delay = getattr(self.config, 'file_lock_wait_delay', 1)
        for attempt in range(max_attempts):
            is_locked = False
            
            for proc in psutil.process_iter(attrs=['pid', 'name']):
                try:
                    if file_path in (f.path for f in proc.open_files()):
                        is_locked = True
                        break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            
            if not is_locked:
                return True
            
            time.sleep(delay)
        
        return False
    
    def _terminate_related_processes(self, file_name: str, 
                                    allowed_processes: List[str] = None):
        """
        Terminate processes that might be using the file.
        
        Args:
            file_name: Name of the file
            allowed_processes: List of process names to terminate
        """
        if allowed_processes is None:
            allowed_processes = ['ffmpeg', '7z']
        
        for process in psutil.process_iter():
            try:
                process_info = process.as_dict(attrs=['pid', 'name'])
                if process_info['name'] in allowed_processes and file_name in process.cmdline():
                    process.terminate()
                    logging.info(f"Terminated process {process_info['name']} "
                               f"(PID: {process_info['pid']}) using file {file_name}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
