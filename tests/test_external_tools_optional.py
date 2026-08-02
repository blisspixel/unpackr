"""Optional integration checks that run only when real external tools exist."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from utils.platform_support import resolve_first_available_tool


def _require_tool(tool_key: str) -> str:
    path = resolve_first_available_tool(tool_key)
    if not path:
        pytest.skip(f"{tool_key} not available on PATH for this runner")
    return path


def test_7z_lists_created_archive(tmp_path: Path):
    seven = _require_tool("7z")
    payload = tmp_path / "payload.txt"
    payload.write_text("unpackr-cross-platform\n", encoding="utf-8")
    archive = tmp_path / "sample.7z"

    create = subprocess.run(
        [seven, "a", "-t7z", str(archive), str(payload)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert create.returncode == 0, create.stderr or create.stdout
    assert archive.is_file()

    listing = subprocess.run(
        [seven, "l", str(archive)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert listing.returncode == 0, listing.stderr or listing.stdout
    assert "payload.txt" in listing.stdout


def test_ffmpeg_reports_version():
    ffmpeg = _require_tool("ffmpeg")
    result = subprocess.run(
        [ffmpeg, "-version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert "ffmpeg" in combined


def test_system_check_resolves_real_7z_when_present():
    seven = _require_tool("7z")
    from utils.system_check import SystemCheck

    checker = SystemCheck(config={"tool_paths": {}})
    assert checker.check_tool("7z") is True
    command = checker.get_tool_command("7z")
    assert command
    # Resolved executable should match the discovered tool basename family.
    resolved = Path(command[0]).name.lower()
    assert resolved.startswith("7z") or "7z" in resolved
    assert Path(seven).name.lower().startswith("7z") or "7z" in Path(seven).name.lower()
