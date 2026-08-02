"""
Configuration management for Unpackr.
Loads and validates configuration settings.
"""

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypeGuard, cast


def _is_str_list(value: Any) -> TypeGuard[List[str]]:
    """Return True when a config value is a list of strings."""
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) for item in cast(List[object], value))


class Config:
    """Manages application configuration."""

    # Default configuration values
    DEFAULT_CONFIG = {
        "video_extensions": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".mpg", ".mpeg", ".m4v", ".3gp", ".webm"],
        "music_extensions": [".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".wma"],
        "image_extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".raw", ".cr2", ".nef"],
        "document_extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt"],
        "removable_extensions": [
            ".sfv",
            ".nfo",
            ".srr",
            ".srs",
            ".url",
            ".db",
            ".nzb",
            ".txt",
            ".xml",
            ".dat",
            ".exe",
            ".htm",
            ".html",
            ".log",
            ".json",
            ".encr",
            ".encrypted",
            ".md5",
            ".sha1",
            ".sha256",
            ".torrent",
            ".magnet",
        ],
        "min_music_files": 10,
        "min_image_files": 10,
        "min_documents": 10,
        "min_sample_size_mb": 50,
        "max_log_files": 3,
        "log_folder": "logs",
        "max_runtime_hours": 48,
        "max_videos_per_folder": 500,
        "max_subfolder_depth": 20,
        "stuck_timeout_hours": 3,
        "file_delete_max_attempts": 5,
        "file_delete_retry_delay": 1,
        "folder_delete_max_attempts": 2,
        "folder_delete_retry_delay": 5,
        "file_lock_wait_attempts": 10,
        "file_lock_wait_delay": 1,
        "archive_extraction_loop_limit": 100,
    }

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """
        Initialize configuration.

        Args:
            config_path: Path to config.json file. If None, uses defaults.
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = deepcopy(self.DEFAULT_CONFIG)
        self.is_valid = config_path is None

        if config_path is not None:
            try:
                config_exists = config_path.is_file()
            except OSError:
                config_exists = False
            if config_exists:
                self.is_valid = self.load_config(config_path)

    def load_config(self, config_path: Path) -> bool:
        """Load configuration from JSON file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                if not isinstance(user_config, dict):
                    print("\nERROR: Config file must contain a JSON object at top level")
                    print(f"  Config file: {config_path.absolute()}")
                    print("Configuration is invalid and will block startup.")
                    return False

                # Validate loaded config before applying
                is_valid, errors = self._validate_config(cast(Dict[str, Any], user_config))
                if not is_valid:
                    print("\nConfiguration validation failed:")
                    print(f"  Config file: {config_path.absolute()}")
                    print()
                    for error in errors:
                        print(error)
                        print()
                    print("Configuration is invalid and will block startup.")
                    return False

                self.config.update(cast(Dict[str, Any], user_config))
                return True
        except json.JSONDecodeError as e:
            print("\nERROR: Invalid JSON in config file")
            print(f"  Config file: {config_path.absolute()}")
            print(f"  Problem: {e}")
            print(f"  Line: {e.lineno}, Column: {e.colno}")
            print()
            print("Fix the JSON syntax and try again.")
            print("Configuration is invalid and will block startup.")
            return False
        except Exception as e:
            print("\nERROR: Could not load config file")
            print(f"  Config file: {config_path.absolute()}")
            print(f"  Problem: {e}")
            print()
            print("Configuration is invalid and will block startup.")
            return False

    def save_config(self, config_path: Path) -> None:
        """Save current configuration to JSON file."""
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config to {config_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self.config[key] = value

    def _validate_config(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate configuration dictionary.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors: List[str] = []

        # Validate numeric ranges
        numeric_fields = {
            "min_music_files": (0, 1000, "Minimum music files", 10),
            "min_image_files": (0, 1000, "Minimum image files", 10),
            "min_documents": (0, 1000, "Minimum documents", 10),
            "min_sample_size_mb": (1, 10000, "Minimum sample size", 50),
            "max_log_files": (1, 100, "Maximum log files", 3),
            "max_runtime_hours": (1, 168, "Maximum runtime hours", 48),
            "max_videos_per_folder": (1, 10000, "Maximum videos per folder", 500),
            "max_subfolder_depth": (1, 50, "Maximum subfolder depth", 20),
            "stuck_timeout_hours": (1, 24, "Stuck timeout hours", 3),
            "file_delete_max_attempts": (1, 100, "File deletion attempts", 5),
            "file_delete_retry_delay": (1, 3600, "File deletion retry delay", 1),
            "folder_delete_max_attempts": (1, 100, "Folder deletion attempts", 2),
            "folder_delete_retry_delay": (1, 3600, "Folder deletion retry delay", 5),
            "file_lock_wait_attempts": (1, 1000, "File lock wait attempts", 10),
            "file_lock_wait_delay": (1, 3600, "File lock wait delay", 1),
            "archive_extraction_loop_limit": (1, 10000, "Archive extraction loop limit", 100),
        }

        for field, (min_val, max_val, _display_name, example) in numeric_fields.items():
            if field in config:
                value = config[field]
                if not isinstance(value, int) or isinstance(value, bool):
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Value: {repr(value)} ({type(value).__name__})\n"
                        f"  Expected: number (integer)\n"
                        f"  Example: {example}\n"
                        f"  Valid range: {min_val} to {max_val}"
                    )
                elif value < min_val or value > max_val:
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Value: {value}\n"
                        f"  Expected: number between {min_val} and {max_val}\n"
                        f"  Example: {example}"
                    )

        # Validate list fields (must be lists of strings)
        list_fields = {
            "video_extensions": [".mp4", ".mkv", ".avi"],
            "music_extensions": [".mp3", ".flac", ".wav"],
            "image_extensions": [".jpg", ".png", ".gif"],
            "document_extensions": [".pdf", ".doc", ".txt"],
            "removable_extensions": [".nfo", ".sfv", ".txt"],
        }

        for field, examples in list_fields.items():
            if field in config:
                value = config[field]
                if not isinstance(value, list):
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Value: {repr(value)} ({type(value).__name__})\n"
                        f"  Expected: list of strings\n"
                        f"  Example: {examples}"
                    )
                elif not _is_str_list(value):
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Problem: List contains non-string values\n"
                        f"  Expected: All entries must be strings\n"
                        f"  Example: {examples}"
                    )
                elif not all(ext.startswith(".") for ext in value):
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Problem: Extensions must start with '.'\n"
                        f"  Example: {examples} (note the dots)"
                    )

        # Validate tool_paths (if present)
        if "tool_paths" in config:
            tool_paths = config["tool_paths"]
            if not isinstance(tool_paths, dict):
                errors.append("tool_paths must be a dictionary")
            else:
                for tool, paths in cast(Dict[str, Any], tool_paths).items():
                    if not isinstance(paths, list):
                        errors.append(f"tool_paths['{tool}'] must be a list of paths")
                    elif not _is_str_list(paths):
                        errors.append(f"tool_paths['{tool}'] must contain only strings")

        # Validate string fields
        if "log_folder" in config:
            log_folder = config["log_folder"]
            if not isinstance(log_folder, str):
                errors.append(f"log_folder must be a string, got {type(log_folder).__name__}")
            elif not log_folder.strip():
                errors.append("log_folder must be a non-empty string")
            elif "\x00" in log_folder:
                errors.append("log_folder must not contain null bytes")

        return (len(errors) == 0, errors)

    def validate_tool_paths(self) -> Tuple[bool, List[str]]:
        """
        Validate that configured tool paths exist and are executable.

        Returns:
            Tuple of (all_valid, error_messages)
        """
        errors: List[str] = []
        tool_paths = self.config.get("tool_paths", {})
        if not isinstance(tool_paths, dict):
            return False, ["tool_paths must be a dictionary"]

        for tool_name, paths in cast(Dict[str, Any], tool_paths).items():
            if not _is_str_list(paths):
                continue  # Already caught by _validate_config

            str_paths = paths
            unsafe_relative = [
                path_str
                for path_str in str_paths
                if not Path(path_str).is_absolute()
                and ("/" in path_str or "\\" in path_str or path_str.startswith("."))
            ]
            if unsafe_relative:
                errors.append(
                    f"Tool '{tool_name}' has unsafe relative executable path(s): {', '.join(unsafe_relative)}\n"
                    "  Fix: Use an absolute path or a command name that resolves from PATH"
                )
                continue

            found_valid = False
            for path_str in str_paths:
                path = Path(path_str)
                if path.is_absolute() and path.exists():
                    found_valid = True
                    break
                if not path.is_absolute() and shutil.which(path_str):
                    found_valid = True
                    break

            if not found_valid:
                errors.append(
                    f"Tool '{tool_name}' not found at any configured path:\n"
                    f"  Paths tried: {', '.join(str_paths)}\n"
                    f"  Fix: Install {tool_name} or update tool_paths['{tool_name}'] in config.json"
                )

        return (len(errors) == 0, errors)

    @property
    def video_extensions(self) -> List[str]:
        """Get list of video file extensions."""
        return self._get_str_list("video_extensions", cast(List[str], self.DEFAULT_CONFIG["video_extensions"]))

    @property
    def image_extensions(self) -> List[str]:
        """Get list of image file extensions."""
        return self._get_str_list("image_extensions", cast(List[str], self.DEFAULT_CONFIG["image_extensions"]))

    @property
    def removable_extensions(self) -> List[str]:
        """Get list of removable file extensions."""
        return self._get_str_list("removable_extensions", cast(List[str], self.DEFAULT_CONFIG["removable_extensions"]))

    @property
    def music_extensions(self) -> List[str]:
        """Get list of music file extensions."""
        return self._get_str_list("music_extensions", cast(List[str], self.DEFAULT_CONFIG["music_extensions"]))

    @property
    def document_extensions(self) -> List[str]:
        """Get list of document file extensions."""
        return self._get_str_list("document_extensions", cast(List[str], self.DEFAULT_CONFIG["document_extensions"]))

    @property
    def min_music_files(self) -> int:
        """Get minimum number of music files to preserve folder."""
        return self._get_int("min_music_files", 10)

    @property
    def min_image_files(self) -> int:
        """Get minimum number of image files to preserve folder."""
        return self._get_int("min_image_files", 10)

    @property
    def min_documents(self) -> int:
        """Get minimum number of documents to preserve folder."""
        return self._get_int("min_documents", 10)

    @property
    def max_log_files(self) -> int:
        """Get maximum number of log files to keep."""
        return self._get_int("max_log_files", 3)

    @property
    def log_folder(self) -> str:
        """Get log folder path."""
        return self._get_str("log_folder", "logs")

    @property
    def max_runtime_hours(self) -> int:
        """Get maximum runtime in hours."""
        return self._get_int("max_runtime_hours", 48)

    @property
    def max_videos_per_folder(self) -> int:
        """Get maximum videos per folder safety limit."""
        return self._get_int("max_videos_per_folder", 500)

    @property
    def max_subfolder_depth(self) -> int:
        """Get maximum subfolder recursion depth."""
        return self._get_int("max_subfolder_depth", 20)

    @property
    def stuck_timeout_hours(self) -> int:
        """Get stuck detection timeout in hours."""
        return self._get_int("stuck_timeout_hours", 3)

    @property
    def file_delete_max_attempts(self) -> int:
        """Get maximum attempts for deleting a file."""
        return self._get_int("file_delete_max_attempts", 5)

    @file_delete_max_attempts.setter
    def file_delete_max_attempts(self, value: int) -> None:
        self.set("file_delete_max_attempts", value)

    @property
    def file_delete_retry_delay(self) -> int:
        """Get initial file deletion retry delay in seconds."""
        return self._get_int("file_delete_retry_delay", 1)

    @file_delete_retry_delay.setter
    def file_delete_retry_delay(self, value: int) -> None:
        self.set("file_delete_retry_delay", value)

    @property
    def folder_delete_max_attempts(self) -> int:
        """Get maximum attempts for deleting a folder."""
        return self._get_int("folder_delete_max_attempts", 2)

    @folder_delete_max_attempts.setter
    def folder_delete_max_attempts(self, value: int) -> None:
        self.set("folder_delete_max_attempts", value)

    @property
    def folder_delete_retry_delay(self) -> int:
        """Get folder deletion retry delay in seconds."""
        return self._get_int("folder_delete_retry_delay", 5)

    @folder_delete_retry_delay.setter
    def folder_delete_retry_delay(self, value: int) -> None:
        self.set("folder_delete_retry_delay", value)

    @property
    def file_lock_wait_attempts(self) -> int:
        """Get maximum checks while waiting for a file lock."""
        return self._get_int("file_lock_wait_attempts", 10)

    @file_lock_wait_attempts.setter
    def file_lock_wait_attempts(self, value: int) -> None:
        self.set("file_lock_wait_attempts", value)

    @property
    def file_lock_wait_delay(self) -> int:
        """Get delay between file lock checks in seconds."""
        return self._get_int("file_lock_wait_delay", 1)

    @file_lock_wait_delay.setter
    def file_lock_wait_delay(self, value: int) -> None:
        self.set("file_lock_wait_delay", value)

    @property
    def archive_extraction_loop_limit(self) -> int:
        """Get the maximum archive extraction loop iterations."""
        return self._get_int("archive_extraction_loop_limit", 100)

    @archive_extraction_loop_limit.setter
    def archive_extraction_loop_limit(self, value: int) -> None:
        self.set("archive_extraction_loop_limit", value)

    def _get_str_list(self, key: str, default: List[str]) -> List[str]:
        value = self.config.get(key, default)
        if _is_str_list(value):
            return value
        return default

    def _get_int(self, key: str, default: int) -> int:
        value = self.config.get(key, default)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    def _get_str(self, key: str, default: str) -> str:
        value = self.config.get(key, default)
        return value if isinstance(value, str) else default
