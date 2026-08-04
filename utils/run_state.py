"""
Persistent run-state for safe resume after interruption.

Records folders that finished processing so a later --resume run can skip them
without re-moving or re-deleting completed work. Fail-closed: corrupt state
files are ignored and treated as empty.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Set


def default_state_path(source_dir: Path) -> Path:
    """Return the default resume state file path under the source tree."""
    return Path(source_dir) / ".unpackr-state.json"


@dataclass
class RunState:
    """Track completed folder paths for resumable processing."""

    path: Path
    source: str = ""
    destination: str = ""
    completed: Set[str] = field(default_factory=set)
    updated_utc: str = ""

    @classmethod
    def load(cls, path: Path) -> "RunState":
        """Load state from disk; return empty state if missing or corrupt."""
        state = cls(path=Path(path))
        try:
            if not state.path.is_file():
                return state
            payload = json.loads(state.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                logging.warning(f"Ignoring corrupt run state (not an object): {state.path}")
                return state
            completed = payload.get("completed", [])
            if not isinstance(completed, list):
                logging.warning(f"Ignoring corrupt run state (completed not a list): {state.path}")
                return state
            state.source = str(payload.get("source", "") or "")
            state.destination = str(payload.get("destination", "") or "")
            state.completed = {str(item) for item in completed if isinstance(item, str) and item}
            state.updated_utc = str(payload.get("updated_utc", "") or "")
            return state
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logging.warning(f"Ignoring unreadable run state {state.path}: {exc}")
            return cls(path=Path(path))

    def configure(self, source: Path, destination: Path) -> None:
        """Bind this state file to a source/destination pair."""
        self.source = str(Path(source).resolve(strict=False))
        self.destination = str(Path(destination).resolve(strict=False))

    def is_completed(self, folder: Path) -> bool:
        """Return True when folder was recorded as fully processed."""
        key = str(Path(folder).resolve(strict=False))
        return key in self.completed

    def mark_completed(self, folder: Path) -> None:
        """Record a folder as completed and persist immediately."""
        key = str(Path(folder).resolve(strict=False))
        self.completed.add(key)
        self.updated_utc = datetime.now(timezone.utc).isoformat()
        self.save()

    def clear(self) -> None:
        """Clear completed entries and remove the state file when possible."""
        self.completed.clear()
        self.updated_utc = datetime.now(timezone.utc).isoformat()
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            logging.warning(f"Could not remove run state file {self.path}: {exc}")
            self.save()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "completed": sorted(self.completed),
            "updated_utc": self.updated_utc,
            "version": 1,
        }

    def save(self) -> None:
        """Atomically write state to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self.to_dict(), indent=2, sort_keys=True)
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(self.path)
