"""Presentation stays inside the colour and wording contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "unpackr"


def test_source_has_no_magenta_or_forced_white():
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "MAGENTA" in text or "Fore.WHITE" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_sample_comments_are_dim():
    sample = json.loads((SRC / "config_files" / "comments.sample.json").read_text(encoding="utf-8"))
    colours = [item.get("color") for item in sample["rarities"].values()]
    assert colours
    assert set(colours) == {"dim"}


def test_receipt_uses_measured_bytes_and_a_real_restore_command():
    from unpackr.utils.presentation import receipt_lines

    rows = receipt_lines(
        folders=2,
        freed_bytes=1536 * 1024,
        source=str(Path.home() / "Downloads"),
        videos_moved=1,
        destination=str(Path.home() / "Videos"),
        redownload=1,
        mode="quarantine",
        restore_command="unpackr restore latest --source ~/Downloads",
        retention_days=14,
        dry_run=False,
        width=60,
    )
    text = " ".join(row[1] for row in rows)
    assert "1.5 MB" in text
    assert "unpackr restore latest --source ~/Downloads" in text
    assert "14 days" in text
    assert "saved" not in text.lower()
    assert rows[2][2] == "info"


def test_permanent_undo_is_a_warning():
    from unpackr.utils.presentation import receipt_lines

    rows = receipt_lines(
        folders=1,
        freed_bytes=10,
        source="C:/Downloads",
        videos_moved=0,
        destination="C:/Videos",
        redownload=0,
        mode="permanent",
        restore_command="",
        retention_days=14,
        dry_run=False,
        width=60,
    )
    assert rows[2][1] == "removed permanently (delete_mode)"
    assert rows[2][2] == "warning"


def test_powershell_force_delete_rejects_a_newline():
    from unpackr.utils.platform_support import _force_delete_windows, build_powershell_delete_command

    nasty = Path("C:/Downloads/ok\nRemove-Item C:/")
    try:
        build_powershell_delete_command(nasty)
    except ValueError as exc:
        assert "newline" in str(exc)
    else:
        raise AssertionError("a newline in the path must be refused")
    assert _force_delete_windows(nasty) is False
