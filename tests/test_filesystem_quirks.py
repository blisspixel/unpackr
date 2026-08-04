"""Filesystem quirk matrix regressions for cross-platform safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Config
from core.file_handler import FileHandler
from utils import filesystem_policy as fsp


def test_normalize_member_path_unifies_separators():
    assert fsp.normalize_member_path(r"a\b\c.txt") == "a/b/c.txt"
    assert fsp.normalize_member_path("a//b///c") == "a/b/c"


@pytest.mark.parametrize(
    "member",
    [
        r"C:\Windows\evil.txt",
        "/etc/passwd",
        "//server/share/file.bin",
        r"D:/absolute/path.mkv",
    ],
)
def test_absolute_member_detection(member):
    assert fsp.is_absolute_member_path(member) is True
    assert fsp.containment_violation(member, Path.cwd()) is not None


@pytest.mark.parametrize(
    "member",
    [
        r"..\evil.txt",
        "../evil.txt",
        "nested/../../evil.txt",
        r"a\..\..\b.txt",
    ],
)
def test_parent_traversal_detection(member):
    assert fsp.has_parent_traversal(member) is True
    assert fsp.containment_violation(member, Path.cwd()) is not None


def test_safe_relative_member_passes_containment(tmp_path):
    assert fsp.containment_violation("subdir/video.mkv", tmp_path) is None
    assert fsp.containment_violation(r"subdir\video.mkv", tmp_path) is None


def test_control_characters_are_rejected():
    assert fsp.contains_control_characters("bad\x00name.mkv") is True
    assert fsp.containment_violation("bad\x00name.mkv", Path.cwd()) is not None


def test_unicode_normalization_is_stable():
    nfd = "cafe\u0301"
    nfc = "café"
    assert fsp.normalize_unicode_name(nfd) == fsp.normalize_unicode_name(nfc)


def test_case_collision_detection():
    assert fsp.looks_like_case_collision("Show.S01E01.mkv", "show.s01e01.mkv") is True
    assert fsp.looks_like_case_collision("a.mkv", "a.mkv") is False
    collisions = fsp.find_case_collisions(["A.mkv", "b.mkv", "a.mkv"])
    assert ("A.mkv", "a.mkv") in collisions


def test_sanitize_filename_handles_non_ascii_and_windows_hostile_chars():
    handler = FileHandler(Config())
    cleaned = handler.sanitize_filename('Мой Фильм: "best?"/*.mkv')
    assert "<" not in cleaned and ">" not in cleaned
    assert ":" not in cleaned
    assert "*" not in cleaned and "?" not in cleaned
    assert cleaned.lower().endswith(".mkv")
    # Cyrillic should be transliterated to ASCII-safe characters.
    assert all(ord(ch) < 128 for ch in cleaned)


def test_symlink_root_is_linklike(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    assert fsp.is_linklike(link) is True
    assert fsp.tree_contains_linklike(tmp_path) is True


def test_tree_contains_nested_symlink_file(tmp_path):
    root = tmp_path / "tree"
    nested = root / "nested"
    nested.mkdir(parents=True)
    real = nested / "payload.txt"
    real.write_text("x", encoding="utf-8")
    link = nested / "alias.txt"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    assert fsp.tree_contains_linklike(root) is True


def test_safe_delete_refuses_symlink_root(tmp_path):
    handler = FileHandler(Config())
    real = tmp_path / "real"
    real.mkdir()
    (real / "keep.txt").write_text("keep", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable on this host")

    assert handler.safe_delete_folder(link, max_attempts=1) is False
    assert (real / "keep.txt").exists()


def test_probe_filesystem_returns_coherent_flags(tmp_path):
    probe = fsp.probe_filesystem(tmp_path)
    assert probe.path
    assert isinstance(probe.case_sensitive, bool)
    assert isinstance(probe.supports_symlinks, bool)
    assert isinstance(probe.supports_non_ascii_names, bool)
    assert probe.platform
    assert "case_sensitive" in probe.to_dict()


def test_probe_non_ascii_roundtrip_when_supported(tmp_path):
    probe = fsp.probe_filesystem(tmp_path)
    if not probe.supports_non_ascii_names:
        pytest.skip("filesystem rejected non-ASCII names")
    sample = tmp_path / "字幕-тест.mkv"
    sample.write_text("ok", encoding="utf-8")
    assert sample.read_text(encoding="utf-8") == "ok"
