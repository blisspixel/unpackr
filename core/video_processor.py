"""
Video processing for Unpackr.
Handles video file health checks and validation.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.safety import SubprocessSafety, SafetyLimits


class VideoProcessor:
    """Handles video file validation and health checks."""
    
    def __init__(self):
        """Initialize the video processor."""
        pass
    
    def check_video_health(self, video_file: Path) -> bool:
        """
        Check if a video file is healthy and not corrupted.
        
        Args:
            video_file: Path to video file
            
        Returns:
            True if video is healthy, False if corrupted or 0 bytes
        """
        # Check if file size is 0 (0 KB)
        if video_file.stat().st_size == 0:
            logging.error(f"0 KB file detected and will be deleted: {video_file}")
            try:
                video_file.unlink()
                logging.info(f"Successfully deleted 0 KB file: {video_file}")
            except Exception as e:
                logging.error(f"Error deleting 0 KB file {video_file}: {e}")
            return False
        
        # Use ffmpeg to check video integrity with timeout
        try:
            # Use safe subprocess with timeout
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ['ffmpeg', '-v', 'error', '-i', str(video_file), '-f', 'null', '-'],
                timeout=SafetyLimits.VIDEO_CHECK_TIMEOUT,
                operation=f"Video health check: {video_file.name}"
            )
            
            if not success or code != 0:
                logging.error(f"Corrupt video file detected: {video_file}\nOutput: {stderr}")
                return False
            
            return True
                
        except FileNotFoundError:
            logging.warning("FFMPEG is not installed. Skipping health check.")
            return True  # Assume healthy if can't check
        except Exception as e:
            logging.error(f"Error during FFMPEG health check: {e}")
            return False
    
    def is_sample_file(self, video_file: Path, min_size_mb: int = 50) -> bool:
        """
        Check if a video file is likely a sample (too small).
        
        Args:
            video_file: Path to video file
            min_size_mb: Minimum size in MB to not be considered a sample
            
        Returns:
            True if file is likely a sample, False otherwise
        """
        # Check if file exists first
        if not video_file.exists():
            return False
        
        # Check filename for 'sample' keyword
        if 'sample' in video_file.name.lower():
            return True
            
        # Check file size
        try:
            size_mb = video_file.stat().st_size / (1024 * 1024)
            return size_mb < min_size_mb
        except (OSError, FileNotFoundError):
            return False
