"""
Configuration management for Unpackr.
Loads and validates configuration settings.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple


class Config:
    """Manages application configuration."""
    
    # Default configuration values
    DEFAULT_CONFIG = {
        'video_extensions': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', 
                           '.mpg', '.mpeg', '.m4v', '.3gp', '.webm'],
        'music_extensions': ['.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.wma'],
        'image_extensions': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', 
                           '.webp', '.raw', '.cr2', '.nef'],
        'document_extensions': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', 
                              '.ppt', '.pptx', '.txt', '.rtf', '.odt'],
        'ebook_extensions': ['.epub', '.mobi', '.azw', '.azw3', '.pdf'],
        'archive_extensions': ['.zip', '.7z', '.rar'],
        'removable_extensions': ['.sfv', '.nfo', '.srr', '.srs', '.url', '.db', 
                               '.nzb', '.txt', '.xml', '.dat', '.exe', '.htm', '.log'],
        'min_music_files': 10,
        'min_image_files': 10,
        'min_documents': 10,
        'min_sample_size_mb': 50,
        'max_log_files': 5,
        'log_folder': 'logs'
    }
    
    def __init__(self, config_path: Path = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Path to config.json file. If None, uses defaults.
        """
        self.config = self.DEFAULT_CONFIG.copy()
        
        if config_path and config_path.exists():
            self.load_config(config_path)
    
    def load_config(self, config_path: Path):
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)

                # Validate loaded config before applying
                is_valid, errors = self._validate_config(user_config)
                if not is_valid:
                    print(f"\nConfiguration validation failed:")
                    print(f"  Config file: {config_path.absolute()}")
                    print()
                    for error in errors:
                        print(error)
                        print()
                    print("Using default configuration instead.")
                    return

                self.config.update(user_config)
        except json.JSONDecodeError as e:
            print(f"\nERROR: Invalid JSON in config file")
            print(f"  Config file: {config_path.absolute()}")
            print(f"  Problem: {e}")
            print(f"  Line: {e.lineno}, Column: {e.colno}")
            print()
            print("Fix the JSON syntax and try again.")
            print("Using default configuration.")
        except Exception as e:
            print(f"\nERROR: Could not load config file")
            print(f"  Config file: {config_path.absolute()}")
            print(f"  Problem: {e}")
            print()
            print("Using default configuration.")
    
    def save_config(self, config_path: Path):
        """Save current configuration to JSON file."""
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config to {config_path}: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value."""
        self.config[key] = value

    def _validate_config(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate configuration dictionary.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate numeric ranges
        numeric_fields = {
            'min_music_files': (0, 1000, "Minimum music files", 10),
            'min_image_files': (0, 1000, "Minimum image files", 10),
            'min_documents': (0, 1000, "Minimum documents", 10),
            'min_sample_size_mb': (1, 10000, "Minimum sample size", 50),
            'max_log_files': (1, 100, "Maximum log files", 5),
            'max_runtime_hours': (1, 168, "Maximum runtime hours", 24),
            'max_videos_per_folder': (1, 10000, "Maximum videos per folder", 100),
            'max_subfolder_depth': (1, 50, "Maximum subfolder depth", 10),
            'stuck_timeout_hours': (1, 24, "Stuck timeout hours", 4),
        }

        for field, (min_val, max_val, display_name, example) in numeric_fields.items():
            if field in config:
                value = config[field]
                if not isinstance(value, int):
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
            'video_extensions': ['.mp4', '.mkv', '.avi'],
            'music_extensions': ['.mp3', '.flac', '.wav'],
            'image_extensions': ['.jpg', '.png', '.gif'],
            'document_extensions': ['.pdf', '.doc', '.txt'],
            'ebook_extensions': ['.epub', '.mobi', '.pdf'],
            'archive_extensions': ['.zip', '.rar', '.7z'],
            'removable_extensions': ['.nfo', '.sfv', '.txt']
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
                elif not all(isinstance(ext, str) for ext in value):
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Problem: List contains non-string values\n"
                        f"  Expected: All entries must be strings\n"
                        f"  Example: {examples}"
                    )
                elif not all(ext.startswith('.') for ext in value):
                    errors.append(
                        f"ERROR: Invalid config value\n"
                        f"  Field: {field}\n"
                        f"  Problem: Extensions must start with '.'\n"
                        f"  Example: {examples} (note the dots)"
                    )

        # Validate tool_paths (if present)
        if 'tool_paths' in config:
            tool_paths = config['tool_paths']
            if not isinstance(tool_paths, dict):
                errors.append("tool_paths must be a dictionary")
            else:
                for tool, paths in tool_paths.items():
                    if not isinstance(paths, list):
                        errors.append(f"tool_paths['{tool}'] must be a list of paths")
                    elif not all(isinstance(p, str) for p in paths):
                        errors.append(f"tool_paths['{tool}'] must contain only strings")

        # Validate string fields
        if 'log_folder' in config:
            if not isinstance(config['log_folder'], str):
                errors.append(f"log_folder must be a string, got {type(config['log_folder']).__name__}")

        return (len(errors) == 0, errors)

    def validate_tool_paths(self) -> Tuple[bool, List[str]]:
        """
        Validate that configured tool paths exist and are executable.

        Returns:
            Tuple of (all_valid, error_messages)
        """
        errors = []
        tool_paths = self.config.get('tool_paths', {})

        for tool_name, paths in tool_paths.items():
            if not isinstance(paths, list):
                continue  # Already caught by _validate_config

            found_valid = False
            for path_str in paths:
                path = Path(path_str)
                if path.exists():
                    found_valid = True
                    break

            if not found_valid:
                errors.append(
                    f"Tool '{tool_name}' not found at any configured path:\n"
                    f"  Paths tried: {', '.join(paths)}\n"
                    f"  Fix: Install {tool_name} or update tool_paths['{tool_name}'] in config.json"
                )

        return (len(errors) == 0, errors)

    @property
    def video_extensions(self) -> List[str]:
        """Get list of video file extensions."""
        return self.config['video_extensions']

    @property
    def image_extensions(self) -> List[str]:
        """Get list of image file extensions."""
        return self.config['image_extensions']

    @property
    def removable_extensions(self) -> List[str]:
        """Get list of removable file extensions."""
        return self.config['removable_extensions']

    @property
    def music_extensions(self) -> List[str]:
        """Get list of music file extensions."""
        return self.config['music_extensions']

    @property
    def document_extensions(self) -> List[str]:
        """Get list of document file extensions."""
        return self.config['document_extensions']

    @property
    def min_music_files(self) -> int:
        """Get minimum number of music files to preserve folder."""
        return self.config['min_music_files']

    @property
    def min_image_files(self) -> int:
        """Get minimum number of image files to preserve folder."""
        return self.config['min_image_files']

    @property
    def min_documents(self) -> int:
        """Get minimum number of documents to preserve folder."""
        return self.config['min_documents']

    @property
    def max_log_files(self) -> int:
        """Get maximum number of log files to keep."""
        return self.config['max_log_files']

    @property
    def log_folder(self) -> str:
        """Get log folder path."""
        return self.config['log_folder']

    @property
    def max_runtime_hours(self) -> int:
        """Get maximum runtime in hours."""
        return self.config.get('max_runtime_hours', 12)

    @property
    def max_videos_per_folder(self) -> int:
        """Get maximum videos per folder safety limit."""
        return self.config.get('max_videos_per_folder', 200)

    @property
    def max_subfolder_depth(self) -> int:
        """Get maximum subfolder recursion depth."""
        return self.config.get('max_subfolder_depth', 15)

    @property
    def stuck_timeout_hours(self) -> int:
        """Get stuck detection timeout in hours."""
        return self.config.get('stuck_timeout_hours', 3)
