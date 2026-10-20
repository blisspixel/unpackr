"""The decision matrix in SAFETY.md is the contract for a manual run."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFETY = ROOT / "docs" / "SAFETY.md"

EXPECTED = {
    "download_incomplete": "removed",
    "video_still_writing": "kept",
    "archive_volume_missing": "removed",
    "archive_password": "removed",
    "video_ok": "moved",
}


def test_safety_matrix_names_every_manual_run_outcome():
    text = SAFETY.read_text(encoding="utf-8")
    assert "## Decision matrix" in text
    found = dict(re.findall(r"\| `([a-z0-9_]+)` \| ([a-z]+) \|", text))
    for reason, action in EXPECTED.items():
        assert found.get(reason) == action, reason
