"""Tests for machine-readable run summaries and exit-code contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils import run_summary
from utils.cli_runtime import build_unpackr_arg_parser


def test_build_unpackr_run_summary_shape():
    summary = run_summary.build_unpackr_run_summary(
        status="completed",
        exit_code=0,
        source="/tmp/in",
        destination="/tmp/out",
        dry_run=True,
        stats={"videos_moved": 3, "folders_processed": 2},
        version="1.4.0",
    )
    assert summary["tool"] == "unpackr"
    assert summary["version"] == "1.4.0"
    assert summary["status"] == "completed"
    assert summary["exit_code"] == 0
    assert summary["dry_run"] is True
    assert summary["paths"]["source"] == "/tmp/in"
    assert summary["counts"]["videos_moved"] == 3
    assert summary["recommended_actions"]
    assert "timestamp_utc" in summary
    payload = json.loads(run_summary.dumps_run_summary(summary))
    assert payload["counts"]["folders_processed"] == 2


def test_failed_status_forces_failed_when_exit_nonzero():
    summary = run_summary.build_unpackr_run_summary(status="completed", exit_code=1)
    assert summary["status"] == "failed"


def test_cancelled_status_normalization():
    summary = run_summary.build_unpackr_run_summary(status="completed", exit_code=0, cancelled=True)
    assert summary["status"] == "cancelled"
    assert summary["cancelled"] is True


def test_unpackr_parser_exposes_json_flag():
    parser = build_unpackr_arg_parser()
    args = parser.parse_args(["--source", "A", "--destination", "B", "--json", "--dry-run"])
    assert args.json is True
    assert args.dry_run is True


def test_exit_codes_doc_exists_and_covers_all_tools():
    text = (Path(__file__).parents[1] / "docs" / "EXIT_CODES.md").read_text(encoding="utf-8")
    for needle in ("unpackr", "unpackr-doctor", "vhealth", "--json", "status"):
        assert needle in text


def test_doctor_json_exit_matches_issue_counts(monkeypatch):
    import doctor

    class Ready:
        def __init__(self, config_path=None):
            pass

        def run(self):
            self.passed = ["Python version"]
            self.warnings = []
            self.issues = []
            return 0

        def to_dict(self, exit_code=None):
            return {
                "timestamp_utc": "t",
                "exit_code": 0 if not self.issues else 1,
                "status": "ready" if not self.issues else "blocked",
                "counts": {"passed": 1, "warnings": 0, "issues": 0},
                "passed": self.passed,
                "warnings": self.warnings,
                "issues": self.issues,
                "recommended_actions": [],
            }

    monkeypatch.setattr(doctor.sys, "argv", ["unpackr-doctor", "--json"])
    monkeypatch.setattr(doctor, "UnpackrDoctor", Ready)
    with pytest.raises(SystemExit) as exc:
        doctor.main()
    assert exc.value.code == 0
