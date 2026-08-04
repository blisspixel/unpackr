"""Tests for interrupt/resume run state."""

from __future__ import annotations

import json
from pathlib import Path

from utils.run_state import RunState, default_state_path


def test_default_state_path_is_under_source(tmp_path):
    assert default_state_path(tmp_path).name == ".unpackr-state.json"
    assert default_state_path(tmp_path).parent == tmp_path


def test_mark_completed_persists_and_loads(tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    folder = source / "show"
    source.mkdir()
    dest.mkdir()
    folder.mkdir()

    state = RunState(path=default_state_path(source))
    state.configure(source, dest)
    state.mark_completed(folder)

    reloaded = RunState.load(default_state_path(source))
    assert reloaded.is_completed(folder)
    assert reloaded.source.endswith("src") or "src" in reloaded.source


def test_corrupt_state_is_ignored(tmp_path):
    path = tmp_path / ".unpackr-state.json"
    path.write_text("{not-json", encoding="utf-8")
    state = RunState.load(path)
    assert state.completed == set()


def test_clear_removes_file(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    folder = source / "a"
    folder.mkdir()
    state = RunState(path=default_state_path(source))
    state.configure(source, tmp_path / "dst")
    state.mark_completed(folder)
    assert default_state_path(source).is_file()
    state.clear()
    assert not default_state_path(source).is_file()


def test_parser_exposes_resume_flag():
    from utils.cli_runtime import build_unpackr_arg_parser

    args = build_unpackr_arg_parser().parse_args(["--source", "A", "--destination", "B", "--resume"])
    assert args.resume is True
