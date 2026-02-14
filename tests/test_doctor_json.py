"""Tests for unpackr-doctor JSON output mode."""

import json

import pytest

import doctor


def test_doctor_json_mode_ready(monkeypatch, capsys):
    """`unpackr-doctor --json` should emit structured JSON and exit 0 when ready."""
    monkeypatch.setattr(doctor.sys, "argv", ["unpackr-doctor", "--json"])

    class ReadyDoctor:
        def run(self):
            self.passed = ["Python version"]
            self.warnings = []
            self.issues = []
            return 0

        def to_dict(self, exit_code=None):
            return {
                "timestamp_utc": "2026-01-01T00:00:00+00:00",
                "exit_code": exit_code,
                "status": "ready",
                "counts": {"passed": 1, "warnings": 0, "issues": 0},
                "passed": self.passed,
                "warnings": self.warnings,
                "issues": self.issues,
                "recommended_actions": ["Re-run `unpackr-doctor` and confirm zero issues before live run."],
            }

    monkeypatch.setattr(doctor, "UnpackrDoctor", ReadyDoctor)

    with pytest.raises(SystemExit) as exc:
        doctor.main()

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert exc.value.code == 0
    assert payload["status"] == "ready"
    assert payload["counts"]["issues"] == 0


def test_doctor_json_mode_blocked(monkeypatch, capsys):
    """`unpackr-doctor --json` should keep non-zero exit for blocking issues."""
    monkeypatch.setattr(doctor.sys, "argv", ["unpackr-doctor", "--json"])

    class BlockedDoctor:
        def run(self):
            self.passed = []
            self.warnings = []
            self.issues = ["Python version too old"]
            return 1

        def to_dict(self, exit_code=None):
            return {
                "timestamp_utc": "2026-01-01T00:00:00+00:00",
                "exit_code": exit_code,
                "status": "blocked",
                "counts": {"passed": 0, "warnings": 0, "issues": 1},
                "passed": self.passed,
                "warnings": self.warnings,
                "issues": self.issues,
                "recommended_actions": ["Install Python 3.11+ and run doctor again."],
            }

    monkeypatch.setattr(doctor, "UnpackrDoctor", BlockedDoctor)

    with pytest.raises(SystemExit) as exc:
        doctor.main()

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert exc.value.code == 1
    assert payload["status"] == "blocked"
    assert payload["counts"]["issues"] == 1
