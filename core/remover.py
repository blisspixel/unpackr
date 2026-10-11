"""
Reversible removal for Unpackr.

Every file or folder a run removes goes through a ``Remover``. Depending on
``delete_mode`` it is moved to ``<source>/.unpackr-quarantine/<run_id>/`` (the
default), sent to the desktop trash, or deleted permanently. Each removal, and
each video moved to the destination, is appended to the run journal
``<source>/.unpackr-runs/<run_id>.jsonl`` so ``unpackr restore`` can put
quarantined files back and reverse moves.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from utils.trash import send_to_trash

DELETE_MODES = ("quarantine", "trash", "permanent")
QUARANTINE_DIR = ".unpackr-quarantine"
RUNS_DIR = ".unpackr-runs"
INTERNAL_PREFIX = ".unpackr-"
RUN_ID_FORMAT = "%Y%m%d-%H%M%S"


def is_internal(path: Path) -> bool:
    """True for Unpackr's own state under the source (quarantine, journals, resume state)."""
    return any(part.startswith(INTERNAL_PREFIX) for part in path.parts)


def new_run_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime(RUN_ID_FORMAT)


def _tree_size(path: Path) -> tuple[int, int]:
    """(files, bytes) under path, without following links."""
    if path.is_symlink() or path.is_file():
        try:
            return 1, path.lstat().st_size
        except OSError:
            return 1, 0
    files = total = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            files += 1
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
    return files, total


class RunJournal:
    """Append-only JSON Lines record of one run's removals and moves."""

    def __init__(self, source_root: Path, run_id: str) -> None:
        self.path = source_root / RUNS_DIR / f"{run_id}.jsonl"
        self.run_id = run_id

    def write(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"time": datetime.now().isoformat(timespec="seconds"), **entry}
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()

    @staticmethod
    def read(path: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                entry = None
            if isinstance(entry, dict):
                entries.append(cast(dict[str, Any], entry))
            else:
                logging.warning(f"Skipping unreadable journal line in {path}")
        return entries


@dataclass
class Remover:
    """Removes files and folders according to ``mode`` and journals every action."""

    mode: str = "permanent"
    source_root: Path | None = None
    run_id: str = field(default_factory=new_run_id)
    journal: RunJournal | None = None
    quarantined_files: int = 0
    quarantined_bytes: int = 0
    trashed_files: int = 0

    def __post_init__(self) -> None:
        if self.mode not in DELETE_MODES:
            raise ValueError(f"unknown delete_mode: {self.mode}")
        if self.mode == "quarantine" and self.source_root is None:
            raise ValueError("quarantine mode needs a source root")
        if self.journal is None and self.source_root is not None:
            self.journal = RunJournal(self.source_root, self.run_id)

    @property
    def quarantine_dir(self) -> Path | None:
        if self.source_root is None:
            return None
        return self.source_root / QUARANTINE_DIR / self.run_id

    def _relative(self, path: Path) -> Path:
        if self.source_root is not None:
            try:
                return path.absolute().relative_to(self.source_root.absolute())
            except ValueError:
                pass
        return Path("_outside") / path.name

    def _quarantine_target(self, path: Path) -> Path:
        if self.quarantine_dir is None:
            raise ValueError("quarantine mode needs a source root")
        target = self.quarantine_dir / self._relative(path)
        counter = 1
        while os.path.lexists(target):
            target = target.with_name(f"{target.stem}.{counter}{target.suffix}")
            counter += 1
        return target

    def _journal(self, op: str, path: Path, reason_code: str, **extra: Any) -> None:
        if self.journal is None:
            return
        try:
            self.journal.write({"op": op, "src": str(path), "reason": reason_code, **extra})
        except OSError as e:
            logging.warning(f"Could not write run journal {self.journal.path}: {e}")

    def remove(
        self,
        path: Path,
        reason_code: str,
        permanent: Callable[[Path], None] | None = None,
    ) -> str:
        """Remove a file or folder. Returns the disposal used ("quarantine", "trash" or "permanent").

        ``permanent`` performs a permanent delete for this kind of path; it is used in
        permanent mode. Raises OSError (including PermissionError) when the path stays.
        """
        files, size = _tree_size(path)
        if self.mode == "quarantine":
            target = self._quarantine_target(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            self.quarantined_files += files
            self.quarantined_bytes += size
            self._journal("quarantined", path, reason_code, dst=str(target), files=files, bytes=size)
            return "quarantine"
        if self.mode == "trash":
            target = send_to_trash(path)
            self.trashed_files += files
            self._journal("trashed", path, reason_code, dst=str(target), files=files, bytes=size)
            return "trash"
        if permanent is not None:
            permanent(path)
        elif path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        self._journal("deleted", path, reason_code, files=files, bytes=size)
        return "permanent"

    def record_move(self, source: Path, destination: Path) -> None:
        """Journal a video moved to the destination so restore can reverse it."""
        try:
            stat = destination.stat()
            self._journal("moved", source, "video_moved", dst=str(destination), bytes=stat.st_size, mtime=stat.st_mtime)
        except OSError:
            self._journal("moved", source, "video_moved", dst=str(destination))


# ---------------------------------------------------------------------------
# Runs, restore and retention
# ---------------------------------------------------------------------------


@dataclass
class RunInfo:
    run_id: str
    journal: Path
    counts: dict[str, int]
    quarantine_files: int
    quarantine_bytes: int


def list_runs(source_root: Path) -> list[RunInfo]:
    runs_dir = source_root / RUNS_DIR
    if not runs_dir.is_dir():
        return []
    infos: list[RunInfo] = []
    for journal in sorted(runs_dir.glob("*.jsonl"), reverse=True):
        counts: dict[str, int] = {}
        for entry in RunJournal.read(journal):
            counts[entry.get("op", "?")] = counts.get(entry.get("op", "?"), 0) + 1
        qdir = source_root / QUARANTINE_DIR / journal.stem
        qfiles, qbytes = _tree_size(qdir) if qdir.exists() else (0, 0)
        infos.append(RunInfo(journal.stem, journal, counts, qfiles, qbytes))
    return infos


@dataclass
class RestoreResult:
    restored: list[str] = field(default_factory=list[str])
    skipped: list[str] = field(default_factory=list[str])


def restore_run(source_root: Path, run_id: str, path_glob: str | None = None, dry_run: bool = False) -> RestoreResult:
    """Put quarantined files back and reverse moves for one run, newest action first."""
    journal = source_root / RUNS_DIR / f"{run_id}.jsonl"
    if not journal.is_file():
        raise FileNotFoundError(f"No journal for run {run_id} in {source_root / RUNS_DIR}")
    quarantine_root = (source_root / QUARANTINE_DIR).resolve()
    result = RestoreResult()

    for entry in reversed(RunJournal.read(journal)):
        op = entry.get("op")
        src = Path(entry.get("src", ""))
        dst = Path(entry["dst"]) if entry.get("dst") else None
        label = str(src)
        if path_glob and not fnmatch.fnmatch(src.as_posix(), path_glob) and not fnmatch.fnmatch(src.name, path_glob):
            continue
        if op == "quarantined" and dst is not None:
            try:
                dst.resolve().relative_to(quarantine_root)
            except ValueError:
                result.skipped.append(f"{label}: quarantine path is outside {QUARANTINE_DIR}")
                continue
            if not os.path.lexists(dst):
                result.skipped.append(f"{label}: no longer in quarantine (purged?)")
                continue
            if os.path.lexists(src):
                result.skipped.append(f"{label}: something already exists at the original path")
                continue
            if not dry_run:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
            result.restored.append(label)
        elif op == "moved" and dst is not None:
            if not dst.exists():
                result.skipped.append(f"{label}: no longer at {dst}")
                continue
            stat = dst.stat()
            if ("bytes" in entry and stat.st_size != entry["bytes"]) or (
                "mtime" in entry and abs(stat.st_mtime - entry["mtime"]) > 2
            ):
                result.skipped.append(f"{label}: {dst} changed since the run")
                continue
            if os.path.lexists(src):
                result.skipped.append(f"{label}: something already exists at the original path")
                continue
            if not dry_run:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
            result.restored.append(label)
        elif op == "trashed":
            result.skipped.append(f"{label}: in the system trash; restore it from there")
        elif op == "deleted":
            result.skipped.append(f"{label}: deleted permanently")
    if not dry_run:
        qdir = source_root / QUARANTINE_DIR / run_id
        _prune_empty_dirs(qdir)
    return result


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        return
    for current, _dirs, _files in os.walk(root, topdown=False):
        with contextlib.suppress(OSError):
            Path(current).rmdir()


def _run_time(run_dir: Path) -> float:
    try:
        return datetime.strptime(run_dir.name[: len("YYYYmmdd-HHMMSS")], RUN_ID_FORMAT).timestamp()
    except ValueError:
        try:
            return run_dir.stat().st_mtime
        except OSError:
            return time.time()


def purge_quarantine(source_root: Path, retention_days: int, now: datetime | None = None) -> tuple[int, int]:
    """Delete quarantined runs older than ``retention_days`` (0 keeps everything).

    Only direct children of ``<source>/.unpackr-quarantine`` are considered, and
    symlinks are never followed. Returns (runs_removed, bytes_freed).
    """
    qroot = source_root / QUARANTINE_DIR
    if retention_days <= 0 or not qroot.is_dir() or qroot.is_symlink():
        return 0, 0
    cutoff = ((now or datetime.now()) - timedelta(days=retention_days)).timestamp()
    removed = freed = 0
    for run_dir in qroot.iterdir():
        if run_dir.is_symlink() or not run_dir.is_dir():
            continue
        if _run_time(run_dir) >= cutoff:
            continue
        _files, size = _tree_size(run_dir)
        shutil.rmtree(run_dir)
        removed += 1
        freed += size
        logging.info(f"Purged quarantined run {run_dir.name} ({size / (1024 * 1024):.1f}MB)")
    return removed, freed


def iter_quarantine(source_root: Path) -> Iterator[Path]:
    qroot = source_root / QUARANTINE_DIR
    if qroot.is_dir():
        yield from (p for p in qroot.iterdir() if p.is_dir() and not p.is_symlink())
