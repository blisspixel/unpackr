"""
Progress tracking and display for Unpackr.
"""

from tqdm import tqdm
from typing import Optional


class ProgressTracker:
    """Manages progress bar display and updates."""
    
    def __init__(self):
        """Initialize the progress tracker."""
        self.pbar: Optional[tqdm] = None
    
    def start(self, total: int, desc: str = "Processing", unit: str = "folder"):
        """
        Start a new progress bar.
        
        Args:
            total: Total number of items to process
            desc: Description to display
            unit: Unit name for progress
        """
        self.pbar = tqdm(total=total, desc=desc, unit=unit)
    
    def update(self, n: int = 1, desc: Optional[str] = None):
        """
        Update progress bar.
        
        Args:
            n: Number of items to increment
            desc: New description (optional)
        """
        if self.pbar:
            if desc:
                self.pbar.set_description(desc)
            self.pbar.update(n)
    
    def close(self):
        """Close the progress bar."""
        if self.pbar:
            self.pbar.close()
            self.pbar = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
