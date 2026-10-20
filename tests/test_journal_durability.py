"""Recovery records are prepared before a byte moves, and survive a failed completion."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from unpackr.core.remover import (
    QUARANTINE_DIR,
    RUNS_DIR,
    RecoveryPrepareError,
    Remover,
    load_run_entries,
    purge_quarantine,
    restore_run,
)


def test_prepare_failure_leaves_the_original(tmp_path: Path):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
    assert remover.journal is not None
    remover.journal.failures.append("prepare")
    with pytest.raises(RecoveryPrepareError):
        remover.remove(source, "junk_extension")
    assert source.read_bytes() == b"keep"
    assert not (tmp_path / QUARANTINE_DIR).exists()
    assert remover.recovery_unconfirmed is False


def test_complete_failure_after_move_still_restores(tmp_path: Path):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
    assert remover.journal is not None
    remover.journal.failures.append("complete")
    assert remover.remove(source, "junk_extension") == "quarantine"
    assert not source.exists()
    assert remover.recovery_unconfirmed is True
    held = next((tmp_path / QUARANTINE_DIR / "r1").rglob("note.nfo"))
    assert held.read_bytes() == b"keep"
    result = restore_run(tmp_path, "r1")
    assert result.restored == [str(source)]
    assert source.read_bytes() == b"keep"


def test_append_failure_restores_once_and_does_not_double_count(tmp_path: Path):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
    assert remover.journal is not None
    remover.journal.failures.append("complete-append")
    remover.remove(source, "junk_extension")
    entries = load_run_entries(tmp_path, "r1")
    assert [entry["op"] for entry in entries] == ["quarantined"]
    restore_run(tmp_path, "r1")
    assert source.read_bytes() == b"keep"
    again = restore_run(tmp_path, "r1")
    assert again.restored == []


def test_truncated_jsonl_line_does_not_hide_the_sidecar(tmp_path: Path):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
    remover.remove(source, "junk_extension")
    journal = tmp_path / RUNS_DIR / "r1.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    entries = load_run_entries(tmp_path, "r1")
    assert len(entries) == 1
    assert entries[0]["op"] == "quarantined"


def test_symlink_quarantine_refuses_and_leaves_the_file(tmp_path: Path):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    quarantine = tmp_path / QUARANTINE_DIR
    try:
        quarantine.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"this environment cannot create a directory symlink: {exc}")
    remover = Remover("quarantine", source_root=tmp_path, run_id="r1")
    with pytest.raises(RecoveryPrepareError):
        remover.remove(source, "junk_extension")
    assert source.read_bytes() == b"keep"
    assert list(outside.iterdir()) == []


def test_unresolved_prepared_record_survives_retention(tmp_path: Path):
    run_id = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d-%H%M%S")
    held = tmp_path / QUARANTINE_DIR / run_id / "note.nfo"
    held.parent.mkdir(parents=True)
    held.write_bytes(b"keep-me")
    pending = tmp_path / RUNS_DIR / f"{run_id}.pending"
    pending.mkdir(parents=True)
    (pending / "abc.json").write_text(
        json.dumps({"id": "abc", "state": "prepared", "op": "quarantined", "src": "note.nfo", "dst": str(held)}),
        encoding="utf-8",
    )
    removed, freed = purge_quarantine(tmp_path, 14)
    assert (removed, freed) == (0, 0)
    assert held.read_bytes() == b"keep-me"


def test_completed_old_run_is_still_purged(tmp_path: Path):
    run_id = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d-%H%M%S")
    held = tmp_path / QUARANTINE_DIR / run_id / "note.nfo"
    held.parent.mkdir(parents=True)
    held.write_bytes(b"0123456789")
    pending = tmp_path / RUNS_DIR / f"{run_id}.pending"
    pending.mkdir(parents=True)
    (pending / "abc.complete.json").write_text(
        json.dumps({"id": "abc", "state": "complete", "op": "quarantined"}),
        encoding="utf-8",
    )
    removed, freed = purge_quarantine(tmp_path, 14)
    assert removed == 1
    assert freed == 10
    assert not held.exists()


def test_permanent_prepare_failure_does_not_delete(tmp_path: Path):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    remover = Remover("permanent", source_root=tmp_path, run_id="r1")
    assert remover.journal is not None
    remover.journal.failures.append("prepare")
    with pytest.raises(RecoveryPrepareError):
        remover.remove(source, "junk_extension")
    assert source.read_bytes() == b"keep"


def test_relocation_failure_aborts_only_while_the_source_remains(tmp_path: Path, monkeypatch):
    source = tmp_path / "note.nfo"
    source.write_bytes(b"keep")
    remover = Remover("quarantine", source_root=tmp_path, run_id="r1")

    def explode(_src: str, _dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("unpackr.core.remover.shutil.move", explode)
    with pytest.raises(OSError, match="disk full"):
        remover.remove(source, "junk_extension")
    assert source.read_bytes() == b"keep"
    assert load_run_entries(tmp_path, "r1") == []
    assert remover.recovery_unconfirmed is False
