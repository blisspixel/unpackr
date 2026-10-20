"""The Windows gate fails when a required tool was skipped, not on every skip."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "assert_junit_executed.py"
_spec = importlib.util.spec_from_file_location("assert_junit_executed", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gate)


def _report(path: Path, body: str) -> None:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuite tests="2">{body}</testsuite>',
        encoding="utf-8",
    )


def test_required_tool_skip_fails_the_gate(tmp_path: Path):
    report = tmp_path / "report.xml"
    _report(
        report,
        '<testcase name="repair"><skipped message="needs 7-Zip, par2 and ffmpeg"/></testcase>'
        '<testcase name="other"/>',
    )
    assert _gate.main(str(report)) == 1


def test_tool_missing_from_path_fails_the_gate(tmp_path: Path):
    report = tmp_path / "report.xml"
    _report(
        report,
        '<testcase name="version"><skipped message="ffmpeg not available on PATH for this runner"/></testcase>',
    )
    assert _gate.main(str(report)) == 1


def test_platform_skip_does_not_fail_the_gate(tmp_path: Path):
    report = tmp_path / "report.xml"
    _report(
        report,
        '<testcase name="trash"><skipped message="freedesktop trash"/></testcase>'
        '<testcase name="linux"><skipped message="hides par2 by narrowing PATH"/></testcase>',
    )
    assert _gate.main(str(report)) == 0


def test_empty_report_fails_the_gate(tmp_path: Path):
    report = tmp_path / "report.xml"
    report.write_text('<testsuite tests="0"></testsuite>', encoding="utf-8")
    assert _gate.main(str(report)) == 1
