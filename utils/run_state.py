"""
Persistent run-state for safe resume after interruption.

Records folders that finished processing so a later --resume run can skip them
without re-moving or re-deleting completed work. Fail-closed: corrupt state
files are ignored and treated as empty.

Same-process multi-writer safety: mark/save/clear serialize per state path and
merge completed keys so concurrent in-process writers do not clobber each other.
Multi-process writers remain best-effort (atomic replace + short retries).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Set

_path_locks: dict[str, threading.RLock] = {}
_path_locks_guard = threading.Lock()


def default_state_path(source_dir: Path) -> Path:
    """Return the default resume state file path under the source tree."""
    return Path(source_dir) / ".unpackr-state.json"


def _lock_for(path: Path) -> threading.RLock:
    key = str(Path(path).resolve(strict=False))
    with _path_locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_locks[key] = lock
        return lock


def _read_payload(path: Path) -> dict[str, Any] | None:
    """Return parsed JSON object or None when missing/corrupt."""
    try:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            logging.warning(f"Ignoring corrupt run state (not an object): {path}")
            return None
        return payload
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logging.warning(f"Ignoring unreadable run state {path}: {exc}")
        return None


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
        state._apply_payload(_read_payload(state.path))
        return state

    def _apply_payload(self, payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        completed = payload.get("completed", [])
        if not isinstance(completed, list):
            logging.warning(f"Ignoring corrupt run state (completed not a list): {self.path}")
            return
        self.source = str(payload.get("source", "") or "") or self.source
        self.destination = str(payload.get("destination", "") or "") or self.destination
        self.completed = {str(item) for item in completed if isinstance(item, str) and item}
        self.updated_utc = str(payload.get("updated_utc", "") or "")

    def configure(self, source: Path, destination: Path) -> None:
        """Bind this state file to a source/destination pair."""
        self.source = str(Path(source).resolve(strict=False))
        self.destination = str(Path(destination).resolve(strict=False))

    def is_completed(self, folder: Path) -> bool:
        """Return True when folder was recorded as fully processed."""
        key = str(Path(folder).resolve(strict=False))
        return key in self.completed

    def mark_completed(self, folder: Path) -> None:
        """Record a folder as completed and persist immediately (merge-safe)."""
        key = str(Path(folder).resolve(strict=False))
        with _lock_for(self.path):
            # Merge any concurrent writers' completed keys before persisting.
            disk = _read_payload(self.path)
            if disk and isinstance(disk.get("completed"), list):
                self.completed |= {str(item) for item in disk["completed"] if isinstance(item, str) and item}
                if not self.source:
                    self.source = str(disk.get("source", "") or "")
                if not self.destination:
                    self.destination = str(disk.get("destination", "") or "")
            self.completed.add(key)
            self.updated_utc = datetime.now(timezone.utc).isoformat()
            self._save_unlocked()

    def clear(self) -> None:
        """Clear completed entries and remove the state file when possible."""
        with _lock_for(self.path):
            self.completed.clear()
            self.updated_utc = datetime.now(timezone.utc).isoformat()
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                logging.warning(f"Could not remove run state file {self.path}: {exc}")
                self._save_unlocked()

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
        with _lock_for(self.path):
            self._save_unlocked()

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self.to_dict(), indent=2, sort_keys=True)
        tmp.write_text(payload + "\n", encoding="utf-8")
        last_error: OSError | None = None
        for attempt in range(5):
            try:
                tmp.replace(self.path)
                return
            except OSError as exc:
                last_error = exc
                # Windows can raise WinError 5/32 when another handle still has
                # the destination open; brief backoff then retry.
                time.sleep(0.02 * (attempt + 1))
        if last_error is not None:
            raise last_error
