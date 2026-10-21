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
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from unpackr.utils.trash import send_to_trash

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


class RecoveryPrepareError(OSError):
    """The recovery record could not be prepared. The original path was not touched."""


class RunJournal:
    """Append-only JSON Lines record of one run's removals and moves.

    A prepared sidecar is written and fsynced before any byte moves. The JSONL
    line is the completed record. If that append fails, the sidecar is enough
    for ``restore`` to replay the action. A partial JSONL line is ignored;
    it never hides a sidecar that was already written.
    """

    def __init__(self, source_root: Path, run_id: str) -> None:
        self.path = source_root / RUNS_DIR / f"{run_id}.jsonl"
        self.pending_dir = source_root / RUNS_DIR / f"{run_id}.pending"
        self.run_id = run_id
        self.source_root = source_root
        # Test hook: names of the next operations that should raise OSError.
        self.failures: list[str] = []

    def _take(self, kind: str) -> bool:
        if self.failures and self.failures[0] == kind:
            self.failures.pop(0)
            return True
        return False

    def _refuse_symlink(self, path: Path) -> None:
        """Refuse to write recovery state through a symlink that could leave the source tree."""
        if path.exists() and path.is_symlink():
            raise RecoveryPrepareError(f"refusing to use symlink for recovery state: {path}")
        root = self.source_root.resolve()
        if path.exists():
            resolved = path.resolve()
            if os.path.commonpath([str(resolved), str(root)]) != str(root):
                raise RecoveryPrepareError(f"recovery path escapes the source tree: {path}")

    def _atomic_write(self, path: Path, entry: dict[str, Any]) -> None:
        self._refuse_symlink(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._refuse_symlink(path.parent)
        temporary = path.with_name(path.name + ".tmp")
        payload = json.dumps(entry, sort_keys=True) + "\n"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def prepare(self, entry: dict[str, Any]) -> str:
        """Durably record an action before the bytes move. Raises if nothing was stored."""
        if self._take("prepare"):
            raise RecoveryPrepareError("injected prepare failure")
        action_id = str(entry.get("id") or uuid.uuid4().hex)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            **entry,
            "id": action_id,
            "state": "prepared",
        }
        self._atomic_write(self.pending_dir / f"{action_id}.json", record)
        return action_id

    def complete(self, action_id: str, entry: dict[str, Any]) -> None:
        """Record that the relocation finished. The prepared sidecar stays if this cannot."""
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            **entry,
            "id": action_id,
            "state": "complete",
        }
        if self._take("complete"):
            raise OSError("injected complete failure")
        self._atomic_write(self.pending_dir / f"{action_id}.complete.json", record)
        if self._take("complete-append"):
            raise OSError("injected complete-append failure")
        self._append(record)
        prepared = self.pending_dir / f"{action_id}.json"
        with contextlib.suppress(OSError):
            prepared.unlink(missing_ok=True)

    def abort(self, action_id: str) -> None:
        """Forget a prepared action whose relocation did not happen."""
        note = {"id": action_id, "state": "aborted", "time": datetime.now().isoformat(timespec="seconds")}
        with contextlib.suppress(OSError):
            self._atomic_write(self.pending_dir / f"{action_id}.aborted.json", note)
            (self.pending_dir / f"{action_id}.json").unlink(missing_ok=True)

    def _append(self, entry: dict[str, Any]) -> None:
        self._refuse_symlink(self.path.parent)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def write(self, entry: dict[str, Any]) -> None:
        """Append one completed record. Used by callers that already relocated nothing sensitive."""
        self._append({"time": datetime.now().isoformat(timespec="seconds"), "state": "complete", **entry})

    @staticmethod
    def read(path: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return entries
        for line in text.splitlines():
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

    def read_sidecars(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not self.pending_dir.is_dir():
            return entries
        for path in sorted(self.pending_dir.glob("*.json")):
            if path.name.endswith(".tmp"):
                continue
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logging.warning(f"Skipping unreadable recovery sidecar {path}")
                continue
            if isinstance(entry, dict):
                entries.append(cast(dict[str, Any], entry))
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
    removed_files: int = 0
    removed_bytes: int = 0
    recovery_unconfirmed: bool = False

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

    def _count_removed(self, files: int, size: int) -> None:
        self.removed_files += files
        self.removed_bytes += size

    def _prepare(self, entry: dict[str, Any]) -> str | None:
        if self.journal is None:
            return None
        return self.journal.prepare(entry)

    def _finish(self, action_id: str | None, entry: dict[str, Any]) -> None:
        if self.journal is None or action_id is None:
            return
        try:
            self.journal.complete(action_id, entry)
        except OSError as exc:
            self.recovery_unconfirmed = True
            logging.error(f"Recovery record for {entry.get('src')} is incomplete: {exc}")

    def prepare_move(self, source: Path, destination: Path) -> str | None:
        """Record a destination move before it happens. Raises RecoveryPrepareError on failure."""
        try:
            stat = source.stat()
            extra: dict[str, Any] = {"bytes": stat.st_size, "mtime": stat.st_mtime}
        except OSError:
            extra = {}
        return self._prepare(
            {"op": "moved", "src": str(source), "reason": "video_moved", "dst": str(destination), **extra}
        )

    def finish_move(self, action_id: str | None, source: Path, destination: Path) -> None:
        extra: dict[str, Any] = {"dst": str(destination)}
        try:
            stat = destination.stat()
            extra["bytes"] = stat.st_size
            extra["mtime"] = stat.st_mtime
        except OSError:
            pass
        self._finish(action_id, {"op": "moved", "src": str(source), "reason": "video_moved", **extra})

    def abort_move(self, action_id: str | None) -> None:
        if self.journal is not None and action_id is not None:
            self.journal.abort(action_id)

    def _fail_relocation(self, action_id: str | None, path: Path) -> None:
        """Abort only while the original is still in place.

        Once the original is gone the prepared record is the only way restore can
        replay the action, so it stays and the run is marked unconfirmed.
        """
        if path.exists():
            self.abort_move(action_id)
            return
        self.recovery_unconfirmed = True
        logging.error(
            f"Recovery record for {path} is unconfirmed: the original is gone and the completion record was not written"
        )

    def remove(
        self,
        path: Path,
        reason_code: str,
        permanent: Callable[[Path], None] | None = None,
    ) -> str:
        """Remove a file or folder. Returns the disposal used ("quarantine", "trash" or "permanent").

        The recovery record is prepared before anything is relocated. A prepare
        failure leaves the original untouched and raises RecoveryPrepareError.
        If the relocation finishes and the completion record cannot be written,
        the prepared record stays so restore can replay it, and
        ``recovery_unconfirmed`` is set.

        ``permanent`` performs a permanent delete for this kind of path; it is used in
        permanent mode. Raises OSError (including PermissionError) when the path stays.
        """
        files, size = _tree_size(path)
        if self.mode == "quarantine":
            if self.source_root is not None:
                quarantine_root = self.source_root / QUARANTINE_DIR
                if quarantine_root.is_symlink():
                    raise RecoveryPrepareError(f"refusing to quarantine through symlink {quarantine_root}")
            target = self._quarantine_target(path)
            action_id = self._prepare(
                {
                    "op": "quarantined",
                    "src": str(path),
                    "reason": reason_code,
                    "dst": str(target),
                    "files": files,
                    "bytes": size,
                }
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(path), str(target))
            except Exception:
                if path.exists() and target.exists():
                    _discard_partial(target)
                self._fail_relocation(action_id, path)
                raise
            self.quarantined_files += files
            self.quarantined_bytes += size
            self._count_removed(files, size)
            self._finish(
                action_id,
                {
                    "op": "quarantined",
                    "src": str(path),
                    "reason": reason_code,
                    "dst": str(target),
                    "files": files,
                    "bytes": size,
                },
            )
            return "quarantine"
        if self.mode == "trash":
            action_id = self._prepare(
                {"op": "trashed", "src": str(path), "reason": reason_code, "files": files, "bytes": size}
            )
            try:
                target = send_to_trash(path)
            except Exception:
                self._fail_relocation(action_id, path)
                raise
            self.trashed_files += files
            self._count_removed(files, size)
            self._finish(
                action_id,
                {
                    "op": "trashed",
                    "src": str(path),
                    "reason": reason_code,
                    "dst": str(target),
                    "files": files,
                    "bytes": size,
                },
            )
            return "trash"
        action_id = self._prepare(
            {"op": "deleted", "src": str(path), "reason": reason_code, "files": files, "bytes": size}
        )
        try:
            if permanent is not None:
                permanent(path)
            elif path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except Exception:
            self._fail_relocation(action_id, path)
            raise
        self._count_removed(files, size)
        self._finish(
            action_id, {"op": "deleted", "src": str(path), "reason": reason_code, "files": files, "bytes": size}
        )
        return "permanent"

    def record_move(self, source: Path, destination: Path) -> None:
        """Journal a video that has already been moved. Prefer prepare_move before the move."""
        try:
            action_id = self.prepare_move(source, destination)
        except RecoveryPrepareError as exc:
            self.recovery_unconfirmed = True
            logging.error(f"Could not prepare recovery record for {source}: {exc}")
            return
        self.finish_move(action_id, source, destination)


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


def _run_id_time(run_id: str, hint: Path | None = None) -> float:
    """Chronology of a run id. Timestamp ids use their clock; anything else uses mtime."""
    try:
        return datetime.strptime(run_id, RUN_ID_FORMAT).timestamp()
    except ValueError:
        if hint is not None:
            try:
                return hint.stat().st_mtime
            except OSError:
                return 0.0
        return 0.0


def list_runs(source_root: Path) -> list[RunInfo]:
    """Newest run id first, whether its records are a journal, sidecars, or both."""
    runs_dir = source_root / RUNS_DIR
    if not runs_dir.is_dir():
        return []
    found: dict[str, Path] = {}
    hints: dict[str, Path] = {}
    for journal in runs_dir.glob("*.jsonl"):
        found[journal.stem] = journal
        hints[journal.stem] = journal
    for pending in runs_dir.glob("*.pending"):
        if not pending.is_dir() or pending.is_symlink():
            continue
        run_id = pending.name[: -len(".pending")]
        found.setdefault(run_id, runs_dir / f"{run_id}.jsonl")
        hints.setdefault(run_id, pending)
    ordered = sorted(found, key=lambda run_id: (_run_id_time(run_id, hints.get(run_id)), run_id), reverse=True)
    infos: list[RunInfo] = []
    for run_id in ordered:
        counts: dict[str, int] = {}
        for entry in load_run_entries(source_root, run_id):
            op = str(entry.get("op", "?"))
            counts[op] = counts.get(op, 0) + 1
        qdir = source_root / QUARANTINE_DIR / run_id
        qfiles, qbytes = _tree_size(qdir) if qdir.exists() else (0, 0)
        infos.append(RunInfo(run_id, found[run_id], counts, qfiles, qbytes))
    return infos


@dataclass
class RestoreResult:
    restored: list[str] = field(default_factory=list[str])
    skipped: list[str] = field(default_factory=list[str])


def restore_run(source_root: Path, run_id: str, path_glob: str | None = None, dry_run: bool = False) -> RestoreResult:
    """Put quarantined files back and reverse moves for one run, newest action first."""
    journal = source_root / RUNS_DIR / f"{run_id}.jsonl"
    pending = source_root / RUNS_DIR / f"{run_id}.pending"
    if not journal.is_file() and not pending.is_dir():
        raise FileNotFoundError(f"No journal for run {run_id} in {source_root / RUNS_DIR}")
    quarantine_root = (source_root / QUARANTINE_DIR).resolve()
    result = RestoreResult()

    for entry in reversed(load_run_entries(source_root, run_id)):
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
        datetime.strptime(run_dir.name, RUN_ID_FORMAT)
    except ValueError:
        try:
            return run_dir.stat().st_mtime
        except OSError:
            return time.time()
    return _run_id_time(run_dir.name)


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
        if run_recovery_unresolved(source_root, run_dir.name):
            logging.warning(f"Keeping quarantined run {run_dir.name}: its recovery record is incomplete")
            continue
        _files, size = _tree_size(run_dir)
        shutil.rmtree(run_dir)
        removed += 1
        freed += size
        logging.info(f"Purged quarantined run {run_dir.name} ({size / (1024 * 1024):.1f}MB)")
    return removed, freed


def _discard_partial(path: Path) -> None:
    """Remove a copy left behind when a relocation fails and the original is still in place."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    except OSError as exc:
        logging.error(f"Could not remove partial relocation {path}: {exc}")


def _sidecar_entries(pending_dir: Path) -> list[dict[str, Any]]:
    if not pending_dir.is_dir() or pending_dir.is_symlink():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(pending_dir.glob("*.json")):
        if path.name.endswith(".tmp") or path.is_symlink():
            continue
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logging.warning(f"Skipping unreadable recovery sidecar {path}")
            continue
        if isinstance(entry, dict):
            entries.append(cast(dict[str, Any], entry))
    return entries


def load_run_entries(source_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Completed and still-prepared actions for one run, one record each.

    A prepared sidecar wins when the JSONL line never landed. An aborted
    action is omitted. Legacy lines without an id are kept as-is.
    """
    journal = source_root / RUNS_DIR / f"{run_id}.jsonl"
    raw = RunJournal.read(journal) if journal.is_file() else []
    raw.extend(_sidecar_entries(source_root / RUNS_DIR / f"{run_id}.pending"))
    rank = {"prepared": 1, "complete": 2, "aborted": 3}
    legacy: list[dict[str, Any]] = []
    chosen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for entry in raw:
        action_id = entry.get("id")
        if not isinstance(action_id, str) or not action_id:
            if entry.get("state") != "aborted":
                legacy.append(entry)
            continue
        state = str(entry.get("state") or "complete")
        if action_id not in chosen:
            order.append(action_id)
            chosen[action_id] = {**entry, "state": state}
            continue
        current = chosen[action_id]
        if rank.get(state, 0) >= rank.get(str(current.get("state")), 0):
            chosen[action_id] = {**current, **entry, "state": state}
    actions = list(legacy)
    actions.extend(chosen[action_id] for action_id in order if chosen[action_id].get("state") != "aborted")
    return actions


def run_recovery_unresolved(source_root: Path, run_id: str) -> bool:
    """True when a prepared record has no completed or aborted partner.

    Those quarantined bytes must not be purged: restore can still replay them.
    A quarantine directory with no pending record keeps the historical purge.
    """
    pending = source_root / RUNS_DIR / f"{run_id}.pending"
    if not pending.is_dir() or pending.is_symlink():
        return False
    prepared: set[str] = set()
    done: set[str] = set()
    for path in pending.glob("*.json"):
        name = path.name
        if name.endswith(".complete.json"):
            done.add(name[: -len(".complete.json")])
        elif name.endswith(".aborted.json"):
            done.add(name[: -len(".aborted.json")])
        elif name.endswith(".json"):
            prepared.add(name[: -len(".json")])
    return bool(prepared - done)


def iter_quarantine(source_root: Path) -> Iterator[Path]:
    qroot = source_root / QUARANTINE_DIR
    if qroot.is_dir():
        yield from (p for p in qroot.iterdir() if p.is_dir() and not p.is_symlink())
