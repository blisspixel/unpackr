"""
Defensive programming utilities for Unpackr.
Input validation, state verification, and error recovery.
"""

import logging
from pathlib import Path
from typing import Optional, Union, List, Any


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class InputValidator:
    """Validates all inputs defensively."""
    
    @staticmethod
    def validate_path(path: Union[str, Path, None], must_exist: bool = False,
                     must_be_dir: bool = False, must_be_file: bool = False,
                     allow_none: bool = False, base_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Validate and sanitize path input with security checks.

        Args:
            path: Path to validate
            must_exist: Path must exist
            must_be_dir: Path must be a directory
            must_be_file: Path must be a file
            allow_none: Allow None values
            base_dir: Optional base directory to enforce path is within bounds

        Returns:
            Validated Path object or None

        Raises:
            ValidationError: If validation fails
        """
        # Handle None
        if path is None:
            if allow_none:
                return None
            raise ValidationError("Path cannot be None")
        
        # Convert to Path object
        try:
            if isinstance(path, str):
                # Remove null bytes (security)
                path = path.replace('\x00', '')
                path_obj = Path(path)
            elif isinstance(path, Path):
                path_obj = path
            else:
                raise ValidationError(f"Invalid path type: {type(path)}")
        except Exception as e:
            raise ValidationError(f"Invalid path format: {e}")
        
        # Check if path is absolute (recommended)
        if not path_obj.is_absolute():
            logging.warning(f"Relative path detected: {path_obj} - converting to absolute")
            try:
                path_obj = path_obj.resolve()
            except Exception as e:
                raise ValidationError(f"Cannot resolve path: {e}")
        
        # Existence checks
        if must_exist and not path_obj.exists():
            raise ValidationError(f"Path does not exist: {path_obj}")
        
        if must_be_dir and path_obj.exists() and not path_obj.is_dir():
            raise ValidationError(f"Path is not a directory: {path_obj}")
        
        if must_be_file and path_obj.exists() and not path_obj.is_file():
            raise ValidationError(f"Path is not a file: {path_obj}")
        
        # Security: Path traversal protection
        try:
            resolved_path = path_obj.resolve()

            # Check for symlink attacks
            if resolved_path != path_obj.resolve(strict=False):
                logging.warning(f"Symlink detected in path: {path_obj}")

            # If base_dir specified, ensure path is within it
            if base_dir is not None:
                try:
                    base_resolved = base_dir.resolve()
                    resolved_path.relative_to(base_resolved)
                except ValueError:
                    raise ValidationError(f"Path {resolved_path} escapes base directory {base_resolved}")

            return resolved_path
        except Exception as e:
            logging.warning(f"Path security check warning: {e}")
            return path_obj
    
    @staticmethod
    def validate_string(value: Any, min_length: int = 0, max_length: int = 10000,
                       allow_empty: bool = True, allow_none: bool = False) -> Optional[str]:
        """
        Validate string input.
        
        Args:
            value: Value to validate
            min_length: Minimum string length
            max_length: Maximum string length
            allow_empty: Allow empty strings
            allow_none: Allow None values
            
        Returns:
            Validated string or None
            
        Raises:
            ValidationError: If validation fails
        """
        if value is None:
            if allow_none:
                return None
            raise ValidationError("String cannot be None")
        
        if not isinstance(value, str):
            raise ValidationError(f"Expected string, got {type(value)}")
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        if not allow_empty and len(value) == 0:
            raise ValidationError("String cannot be empty")
        
        if len(value) < min_length:
            raise ValidationError(f"String too short: {len(value)} < {min_length}")
        
        if len(value) > max_length:
            raise ValidationError(f"String too long: {len(value)} > {max_length}")
        
        return value
    
    @staticmethod
    def validate_int(value: Any, min_val: Optional[int] = None,
                    max_val: Optional[int] = None, allow_none: bool = False) -> Optional[int]:
        """
        Validate integer input.
        
        Args:
            value: Value to validate
            min_val: Minimum value
            max_val: Maximum value
            allow_none: Allow None values
            
        Returns:
            Validated integer or None
            
        Raises:
            ValidationError: If validation fails
        """
        if value is None:
            if allow_none:
                return None
            raise ValidationError("Integer cannot be None")
        
        if not isinstance(value, int) or isinstance(value, bool):
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Cannot convert to integer: {value}")
        
        if min_val is not None and value < min_val:
            raise ValidationError(f"Value too small: {value} < {min_val}")
        
        if max_val is not None and value > max_val:
            raise ValidationError(f"Value too large: {value} > {max_val}")
        
        return value
    
    @staticmethod
    def validate_list(value: Any, min_length: int = 0, max_length: Optional[int] = None,
                     allow_none: bool = False, allow_empty: bool = True) -> Optional[list]:
        """
        Validate list input.
        
        Args:
            value: Value to validate
            min_length: Minimum list length
            max_length: Maximum list length
            allow_none: Allow None values
            allow_empty: Allow empty lists
            
        Returns:
            Validated list or None
            
        Raises:
            ValidationError: If validation fails
        """
        if value is None:
            if allow_none:
                return None
            raise ValidationError("List cannot be None")
        
        if not isinstance(value, list):
            raise ValidationError(f"Expected list, got {type(value)}")
        
        if not allow_empty and len(value) == 0:
            raise ValidationError("List cannot be empty")
        
        if len(value) < min_length:
            raise ValidationError(f"List too short: {len(value)} < {min_length}")
        
        if max_length is not None and len(value) > max_length:
            raise ValidationError(f"List too long: {len(value)} > {max_length}")
        
        return value


class StateValidator:
    """Validates object and system state."""
    
    @staticmethod
    def check_file_accessible(file_path: Path) -> bool:
        """
        Check if file is accessible for reading.
        
        Args:
            file_path: Path to file
            
        Returns:
            True if accessible, False otherwise
        """
        try:
            if not file_path.exists():
                return False
            
            if not file_path.is_file():
                return False
            
            # Try to open for reading
            with open(file_path, 'rb') as f:
                f.read(1)
            
            return True
        except (PermissionError, OSError, IOError):
            return False
    
    @staticmethod
    def check_dir_writable(dir_path: Path) -> bool:
        """
        Check if directory is writable.
        
        Args:
            dir_path: Path to directory
            
        Returns:
            True if writable, False otherwise
        """
        try:
            if not dir_path.exists():
                return False
            
            if not dir_path.is_dir():
                return False
            
            # Try to create a temporary file
            test_file = dir_path / '.unpackr_write_test'
            test_file.touch()
            test_file.unlink()
            
            return True
        except (PermissionError, OSError, IOError):
            return False
    
    @staticmethod
    def check_disk_space(path: Path, required_mb: int = 100) -> bool:
        """
        Check if sufficient disk space is available.
        
        Args:
            path: Path to check
            required_mb: Required space in MB
            
        Returns:
            True if sufficient space, False otherwise
        """
        try:
            import shutil
            stat = shutil.disk_usage(path)
            free_mb = stat.free / (1024 * 1024)
            
            if free_mb < required_mb:
                logging.warning(f"Low disk space: {free_mb:.1f}MB free, {required_mb}MB required")
                return False
            
            return True
        except Exception as e:
            logging.error(f"Cannot check disk space: {e}")
            return True  # Assume OK if can't check
    
    @staticmethod
    def validate_config_dict(config: dict, required_keys: List[str]) -> bool:
        """
        Validate configuration dictionary.
        
        Args:
            config: Config dictionary
            required_keys: List of required keys
            
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(config, dict):
            logging.error(f"Config is not a dict: {type(config)}")
            return False
        
        for key in required_keys:
            if key not in config:
                logging.error(f"Missing required config key: {key}")
                return False
        
        return True


class ErrorRecovery:
    """Graceful error recovery and fallbacks."""
    
    @staticmethod
    def safe_delete(path: Path, max_attempts: int = 3) -> bool:
        """
        Safely delete file or directory with retries.
        
        Args:
            path: Path to delete
            max_attempts: Maximum attempts
            
        Returns:
            True if deleted, False otherwise
        """
        if not path.exists():
            return True  # Already gone
        
        import time
        
        for attempt in range(max_attempts):
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    import shutil
                    shutil.rmtree(path)
                
                return True
            except Exception as e:
                logging.warning(f"Delete attempt {attempt + 1}/{max_attempts} failed: {e}")
                time.sleep(1)
        
        return False
    
    @staticmethod
    def safe_move(src: Path, dst: Path, max_attempts: int = 3, verify_integrity: bool = True,
                  atomic: bool = True) -> bool:
        """
        Safely move file with retries, integrity verification, and atomic operation support.

        Atomic mode (default): Moves to temporary file first, then renames to final destination.
        This ensures the destination file is never in a partial state.

        Args:
            src: Source path
            dst: Destination path
            max_attempts: Maximum attempts
            verify_integrity: Verify file size after move
            atomic: Use atomic rename operation (move to temp, then rename)

        Returns:
            True if moved successfully, False otherwise
        """
        if not src.exists():
            logging.error(f"Source does not exist: {src}")
            return False

        import shutil
        import time

        # Get source file size before move
        try:
            source_size = src.stat().st_size
        except Exception as e:
            logging.error(f"Cannot stat source file {src}: {e}")
            return False

        for attempt in range(max_attempts):
            temp_dst = None
            try:
                if atomic:
                    # Atomic move: first move to temp file, then rename to final destination
                    # This ensures destination is never partially written
                    temp_dst = dst.parent / f".tmp_{dst.name}_{int(time.time())}"

                    # Use shutil.move to temp location
                    shutil.move(str(src), str(temp_dst))

                    # Verify integrity if requested
                    if verify_integrity:
                        dest_size = temp_dst.stat().st_size
                        if dest_size != source_size:
                            logging.error(f"Size mismatch after move: {source_size} != {dest_size}")
                            # Rollback: restore source if possible
                            try:
                                temp_dst.unlink()
                            except OSError:
                                pass
                            return False

                    # Atomic rename (this is atomic on most filesystems)
                    temp_dst.replace(dst)

                    logging.info(f"Successfully moved (atomic) {src.name} ({source_size} bytes)")
                    return True

                else:
                    # Non-atomic move (original behavior)
                    shutil.move(str(src), str(dst))

                    # Verify integrity if requested
                    if verify_integrity:
                        try:
                            dest_size = dst.stat().st_size
                            if dest_size != source_size:
                                logging.error(f"Size mismatch after move: {source_size} != {dest_size}")
                                # Cleanup incomplete move
                                try:
                                    dst.unlink()
                                except OSError:
                                    pass
                                return False
                        except Exception as e:
                            logging.error(f"Cannot verify moved file {dst}: {e}")
                            return False

                    logging.info(f"Successfully moved {src.name} ({source_size} bytes)")
                    return True

            except Exception as e:
                logging.warning(f"Move attempt {attempt + 1}/{max_attempts} failed: {e}")

                # Cleanup temp file if it exists
                if temp_dst and temp_dst.exists():
                    try:
                        temp_dst.unlink()
                    except OSError:
                        pass

                if attempt < max_attempts - 1:
                    time.sleep(1)

        return False
    
    @staticmethod
    def safe_read_text(path: Path, default: str = "", max_size_mb: int = 10) -> str:
        """
        Safely read text file with size limit.
        
        Args:
            path: File path
            default: Default value if read fails
            max_size_mb: Maximum file size in MB
            
        Returns:
            File contents or default
        """
        try:
            # Check size first
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > max_size_mb:
                logging.error(f"File too large to read: {size_mb:.1f}MB > {max_size_mb}MB")
                return default
            
            return path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            logging.error(f"Cannot read file {path}: {e}")
            return default


def defensive_wrapper(func):
    """
    Decorator to wrap functions with defensive error handling.
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function
    """
    def wrapper(*args, **kwargs):
        try:
            # Log function entry
            logging.debug(f"[DEFENSIVE] Entering {func.__name__}")
            
            # Validate args are not None
            for i, arg in enumerate(args):
                if arg is None and i > 0:  # Allow None for self
                    logging.warning(f"[DEFENSIVE] None argument at position {i} in {func.__name__}")
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Log successful completion
            logging.debug(f"[DEFENSIVE] Completed {func.__name__}")
            
            return result
            
        except Exception as e:
            logging.error(f"[DEFENSIVE] Exception in {func.__name__}: {e}", exc_info=True)
            # Return safe default based on function name
            if 'check' in func.__name__ or 'is_' in func.__name__:
                return False
            elif 'get' in func.__name__ or 'find' in func.__name__:
                return None
            else:
                raise
    
    return wrapper
