"""
Progress tracking and display for Unpackr.
"""

import threading
from types import TracebackType
from typing import NoReturn, Self

from tqdm import tqdm


class ProgressTracker:
    """Manages progress bar display and updates with thread safety."""

    def __init__(self) -> None:
        """Initialize the progress tracker."""
        self.pbar: tqdm[NoReturn] | None = None
        self._lock = threading.Lock()  # Protect concurrent access to progress bar

    def start(self, total: int, desc: str = "Processing", unit: str = "folder") -> None:
        """
        Start a new progress bar.

        Args:
            total: Total number of items to process
            desc: Description to display
            unit: Unit name for progress
        """
        with self._lock:
            self.pbar = tqdm(total=total, desc=desc, unit=unit)

    def update(self, n: int = 1, desc: str | None = None) -> None:
        """
        Update progress bar.

        Args:
            n: Number of items to increment
            desc: New description (optional)
        """
        with self._lock:
            if self.pbar:
                if desc:
                    self.pbar.set_description(desc)
                self.pbar.update(n)

    def close(self) -> None:
        """Close the progress bar."""
        with self._lock:
            if self.pbar:
                self.pbar.close()
                self.pbar = None

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.close()
