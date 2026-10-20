"""Tests for unpackr-doctor behavior."""

from types import SimpleNamespace

from unpackr.doctor import UnpackrDoctor


def test_check_python_version_rejects_310(monkeypatch, capsys):
    """Doctor should fail Python 3.10. 3.11 is the oldest supported release."""
    monkeypatch.setattr("unpackr.doctor.sys.version_info", SimpleNamespace(major=3, minor=10, micro=11))
    doc = UnpackrDoctor()

    doc.check_python_version()
    output = capsys.readouterr().out

    assert "need 3.11+" in output
    assert "Python version too old" in doc.issues


def test_check_python_version_accepts_311(monkeypatch, capsys):
    """Doctor should pass Python 3.11."""
    monkeypatch.setattr("unpackr.doctor.sys.version_info", SimpleNamespace(major=3, minor=11, micro=9))
    doc = UnpackrDoctor()

    doc.check_python_version()
    output = capsys.readouterr().out

    assert "Python 3.11.9" in output
    assert "Python version" in doc.passed


def test_check_python_version_accepts_312(monkeypatch, capsys):
    """Doctor should pass Python 3.12+ without version warning."""
    monkeypatch.setattr("unpackr.doctor.sys.version_info", SimpleNamespace(major=3, minor=12, micro=9))
    doc = UnpackrDoctor()

    doc.check_python_version()
    output = capsys.readouterr().out

    assert "Python 3.12.9" in output
    assert "Python version" in doc.passed
