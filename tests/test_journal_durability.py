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
    list_runs,
    load_run_entries,
    purge_quarantine,
    restore_run,
)
from unpackr.utils.cli_subcommands import run_subcommand


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


def _quarantine_record(source: Path, run_id: str, name: str, kind: str) -> Path:
    """A synthetic quarantined file. ``kind`` is ``jsonl``, ``prepared``, or ``complete``."""
    held = source / QUARANTINE_DIR / run_id / name
    held.parent.mkdir(parents=True, exist_ok=True)
    held.write_bytes(name.encode())
    record = {
        "id": f"id-{name}",
        "state": "prepared" if kind == "prepared" else "complete",
        "op": "quarantined",
        "src": str(source / name),
        "dst": str(held),
    }
    if kind == "jsonl":
        journal = source / RUNS_DIR / f"{run_id}.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(json.dumps(record) + "\n", encoding="utf-8")
    else:
        pending = source / RUNS_DIR / f"{run_id}.pending"
        pending.mkdir(parents=True, exist_ok=True)
        filename = "id.json" if kind == "prepared" else "id.complete.json"
        (pending / filename).write_text(json.dumps(record), encoding="utf-8")
    return held


def test_jsonl_runs_stay_newest_first(tmp_path: Path):
    _quarantine_record(tmp_path, "20261020-010000", "old.nfo", "jsonl")
    _quarantine_record(tmp_path, "20261020-020000", "new.nfo", "jsonl")
    assert [info.run_id for info in list_runs(tmp_path)] == ["20261020-020000", "20261020-010000"]


def test_a_run_with_a_journal_and_sidecars_is_listed_once(tmp_path: Path):
    _quarantine_record(tmp_path, "20261020-010000", "note.nfo", "jsonl")
    _quarantine_record(tmp_path, "20261020-010000", "note.nfo", "prepared")
    infos = list_runs(tmp_path)
    assert [info.run_id for info in infos] == ["20261020-010000"]
    assert infos[0].counts == {"quarantined": 1}


@pytest.mark.parametrize("kind", ["prepared", "complete"])
def test_restore_latest_prefers_a_newer_sidecar_only_run(tmp_path: Path, capsys, kind: str):
    older = _quarantine_record(tmp_path, "20261020-010000", "old.nfo", "jsonl")
    newer = _quarantine_record(tmp_path, "20261020-020000", "new.nfo", kind)
    before = {path: path.read_bytes() for path in (older, newer)}

    assert run_subcommand(["runs", "--source", str(tmp_path), "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["run_id"] for item in listed] == ["20261020-020000", "20261020-010000"]

    assert run_subcommand(["restore", "latest", "--source", str(tmp_path), "--dry-run", "--json"]) == 0
    latest = json.loads(capsys.readouterr().out)
    assert run_subcommand(["restore", "20261020-020000", "--source", str(tmp_path), "--dry-run", "--json"]) == 0
    explicit = json.loads(capsys.readouterr().out)

    assert latest["run_id"] == "20261020-020000"
    assert latest == explicit
    assert latest["restored"] == [str(tmp_path / "new.nfo")]
    assert not (tmp_path / "new.nfo").exists()
    assert {path: path.read_bytes() for path in (older, newer)} == before


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
