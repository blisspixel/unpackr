"""
Configuration management for Unpackr.
Loads and validates configuration settings.
"""

import json
from pathlib import Path
from typing import List, Dict, Any


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
        'min_music_files': 3,
        'min_image_files': 5,
        'min_documents': 1,
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
                self.config.update(user_config)
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
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
    def max_log_files(self) -> int:
        """Get maximum number of log files to keep."""
        return self.config['max_log_files']
    
    @property
    def log_folder(self) -> str:
        """Get log folder path."""
        return self.config['log_folder']
