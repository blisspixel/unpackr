"""
Per-item run report for Unpackr.

Every decision a run makes about a file (moved, deleted, extracted, kept,
skipped, blocked) is recorded with a reason code. When the run ends, files that
were present at the start but never recorded explicitly are reconciled, so each
of them carries exactly one terminal action.

The report feeds the ``items`` array of ``--json`` and the ``--report`` JSONL
file. It never deletes or moves anything itself.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ACTIONS = ("moved", "deleted", "extracted", "kept", "skipped", "blocked")

# Names Unpackr itself maintains in the source tree; never reported as content.
INTERNAL_PREFIXES = (".unpackr-",)

_ARCHIVE_VOLUME = re.compile(r"(\.7z(\.\d{3})?|\.rar|\.r\d{2}|\.part\d+\.rar)$", re.IGNORECASE)


@dataclass
class ReportItem:
    """One decision about one path."""

    path: str
    folder: str
    action: str
    reason_code: str
    detail: str = ""
    bytes: Optional[int] = None
    destination: Optional[str] = None
    planned: bool = False
    inferred: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v not in (None, "") or k in ("path", "action", "reason_code")}


@dataclass
class _PendingRemoval:
    reason_code: str
    detail: str = ""


@dataclass
class RunReport:
    """Collects ReportItems for one run; safe to call from the worker thread only."""

    planned: bool = False
    root: Optional[Path] = None
    _items: Dict[str, ReportItem] = field(default_factory=dict)
    _inventory: Dict[str, int] = field(default_factory=dict)
    _removed_folders: Dict[str, _PendingRemoval] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------------ setup

    def begin(self, source_dir: Path) -> None:
        """Take an inventory of every regular file under the source."""
        self.root = source_dir
        self._inventory.clear()
        try:
            candidates = list(source_dir.rglob("*"))
        except OSError:
            candidates = []
        for path in candidates:
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                rel = self._rel(path)
                if self._internal(rel):
                    continue
                self._inventory[rel] = path.stat().st_size
            except OSError:
                continue

    # ---------------------------------------------------------------- record

    def _rel(self, path: Path) -> str:
        if self.root is not None:
            try:
                return path.relative_to(self.root).as_posix()
            except ValueError:
                pass
        return path.as_posix()

    @staticmethod
    def _internal(rel: str) -> bool:
        return any(part.startswith(INTERNAL_PREFIXES) for part in rel.split("/"))

    def record(
        self,
        path: Path,
        action: str,
        reason_code: str,
        detail: str = "",
        *,
        destination: Optional[Path] = None,
        size: Optional[int] = None,
    ) -> None:
        """Record the terminal action for a path (the latest record wins)."""
        if action not in ACTIONS:
            raise ValueError(f"unknown report action: {action}")
        rel = self._rel(path)
        folder = rel.split("/", 1)[0] if "/" in rel else ""
        if size is None:
            size = self._inventory.get(rel)
            if size is None:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = None
        item = ReportItem(
            path=rel,
            folder=folder,
            action=action,
            reason_code=reason_code,
            detail=detail,
            bytes=size,
            destination=str(destination) if destination is not None else None,
            planned=self.planned,
        )
        with self._lock:
            self._items[rel] = item

    def record_many(self, paths: Iterable[Path], action: str, reason_code: str, detail: str = "") -> None:
        for path in paths:
            self.record(path, action, reason_code, detail)

    def record_folder_removed(self, folder: Path, reason_code: str = "folder_cleanup", detail: str = "") -> None:
        """Note that a folder (and everything left in it) was, or would be, removed."""
        with self._lock:
            self._removed_folders[self._rel(folder)] = _PendingRemoval(reason_code, detail)

    # -------------------------------------------------------------- finalize

    def _removed_by_folder(self, rel: str) -> Optional[_PendingRemoval]:
        parts = rel.split("/")
        for depth in range(len(parts) - 1, 0, -1):
            hit = self._removed_folders.get("/".join(parts[:depth]))
            if hit is not None:
                return hit
        return None

    @staticmethod
    def _reason_for_extension(rel: str, removable_extensions: Iterable[str]) -> str:
        lower = rel.lower()
        if lower.endswith(".par2"):
            return "par2_cleanup"
        if _ARCHIVE_VOLUME.search(lower):
            return "archive_cleanup"
        suffix = Path(lower).suffix
        if suffix in set(removable_extensions):
            return "junk_extension"
        if suffix == "":
            return "junk_no_extension"
        return "folder_cleanup"

    def finalize(self, removable_extensions: Iterable[str] = ()) -> List[ReportItem]:
        """Give every inventoried file one terminal action and return all items."""
        removable = [e.lower() for e in removable_extensions]
        with self._lock:
            for rel, size in self._inventory.items():
                item = self._items.get(rel)
                path = (self.root / rel) if self.root is not None else Path(rel)
                exists = path.exists()
                if item is not None:
                    # A volume whose set failed is removed only if its folder was cleaned up.
                    if item.action == "skipped" and not exists and not self.planned:
                        item.action = "deleted"
                    continue
                removal = self._removed_by_folder(rel)
                # A plan removes what lies in folders it would delete; a live run removed what is gone.
                gone = removal is not None if self.planned else not exists
                action = "deleted" if gone else "kept"
                if action == "kept":
                    reason = "not_processed" if removal is None else "folder_kept"
                    detail = ""
                elif removal is not None:
                    reason = self._reason_for_extension(rel, removable)
                    detail = f"removed with folder ({removal.reason_code})"
                else:
                    reason = self._reason_for_extension(rel, removable)
                    detail = "removed during processing"
                self._items[rel] = ReportItem(
                    path=rel,
                    folder=rel.split("/", 1)[0] if "/" in rel else "",
                    action=action,
                    reason_code=reason,
                    detail=detail,
                    bytes=size,
                    planned=self.planned,
                    inferred=True,
                )
            return sorted(self._items.values(), key=lambda i: i.path)

    # ---------------------------------------------------------------- output

    def items(self) -> List[ReportItem]:
        with self._lock:
            return sorted(self._items.values(), key=lambda i: i.path)

    @staticmethod
    def counts(items: Iterable[ReportItem]) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for item in items:
            totals[item.action] = totals.get(item.action, 0) + 1
        return totals

    @staticmethod
    def write_jsonl(items: Iterable[ReportItem], destination: Path, summary: Optional[Dict[str, Any]] = None) -> None:
        """Write one JSON object per item, then an optional summary line."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps({"type": "item", **item.to_dict()}, sort_keys=True) + "\n")
            if summary is not None:
                handle.write(json.dumps({"type": "summary", **summary}, sort_keys=True) + "\n")
