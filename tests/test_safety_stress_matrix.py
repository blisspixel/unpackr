"""
Safety stress matrix for concurrent-path risks.

These tests encode the regression matrix required by docs/BENCHMARKS.md before
any parallel extraction/validation work. They do not enable concurrency; they
prove destructive paths stay fail-closed under races and multi-threaded access.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from core.config import Config
from core.file_handler import FileHandler
from core.safety_invariants import (
    FileOperation,
    OperationType,
    SafetyInvariants,
    ValidationCache,
    ValidationDecision,
    ValidationResult,
)
from utils.run_state import RunState


class TestDeleteRaceMatrix:
    """TOCTOU and content-change races around folder deletion."""

    def test_safe_delete_refuses_when_video_appears(self, tmp_path):
        folder = tmp_path / "work"
        folder.mkdir()
        (folder / "readme.nfo").write_text("junk", encoding="utf-8")
        handler = FileHandler(Config())
        assert handler.is_folder_empty_or_removable(folder) is True

        # Simulate another process finishing a download between check and delete.
        (folder / "movie.mkv").write_bytes(b"x" * 2048)
        assert handler.safe_delete_folder(folder) is False
        assert folder.exists()
        assert (folder / "movie.mkv").exists()

    def test_safe_delete_refuses_image_collection_race(self, tmp_path):
        folder = tmp_path / "gallery_race"
        folder.mkdir()
        (folder / "note.txt").write_text("x", encoding="utf-8")
        handler = FileHandler(Config())
        assert handler.is_folder_empty_or_removable(folder) is True

        for i in range(handler.config.min_image_files):
            (folder / f"img{i:02d}.jpg").write_bytes(b"x" * (1100 * 1024))

        assert handler.safe_delete_folder(folder) is False
        assert folder.exists()

    def test_safe_delete_refuses_symlink_root(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        (real / "keep.mkv").write_bytes(b"x")
        link = tmp_path / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks unavailable on this host")

        handler = FileHandler(Config())
        assert handler.safe_delete_folder(link) is False
        assert real.exists()
        assert (real / "keep.mkv").exists()


class TestInvariantStressMatrix:
    def test_never_delete_validated_video(self, tmp_path):
        ValidationCache.clear()
        dest_root = tmp_path / "dest"
        dest_root.mkdir()
        video = dest_root / "kept.mkv"
        video.write_bytes(b"x" * 4096)

        ValidationCache.set(
            video,
            ValidationResult(
                path=video,
                decision=ValidationDecision.PASS,
                timestamp=None,
                metadata={},
            ),
        )
        invariants = SafetyInvariants(destination_root=dest_root, config=Config())
        delete_op = FileOperation(type=OperationType.DELETE, path=video)
        assert invariants.never_delete_validated_video(delete_op) is False
        ValidationCache.clear()


class TestRunStateConcurrencyMatrix:
    def test_parallel_mark_completed_preserves_all_folders(self, tmp_path):
        state_path = tmp_path / ".unpackr-state.json"
        source = tmp_path / "src"
        dest = tmp_path / "dst"
        source.mkdir()
        dest.mkdir()

        folders = [source / f"folder_{i:03d}" for i in range(40)]
        for folder in folders:
            folder.mkdir()

        errors: list[BaseException] = []

        def worker(batch: list[Path]) -> None:
            local = RunState(path=state_path)
            local.configure(source, dest)
            try:
                for folder in batch:
                    local.mark_completed(folder)
            except BaseException as exc:  # noqa: BLE001 — collect for main thread
                errors.append(exc)

        mid = len(folders) // 2
        t1 = threading.Thread(target=worker, args=(folders[:mid],))
        t2 = threading.Thread(target=worker, args=(folders[mid:],))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        final = RunState.load(state_path)
        assert final.source
        assert final.destination
        assert all(final.is_completed(folder) for folder in folders)

    def test_sequential_rapid_marks_never_lose_entries(self, tmp_path):
        state_path = tmp_path / ".unpackr-state.json"
        state = RunState(path=state_path)
        source = tmp_path / "src"
        dest = tmp_path / "dst"
        source.mkdir()
        dest.mkdir()
        state.configure(source, dest)

        folders = [source / f"f{i}" for i in range(25)]
        for folder in folders:
            folder.mkdir()
            state.mark_completed(folder)

        reloaded = RunState.load(state_path)
        assert all(reloaded.is_completed(folder) for folder in folders)


class TestHandlerStressMatrix:
    def test_removable_then_not_under_threaded_probe(self, tmp_path):
        folder = tmp_path / "probe"
        folder.mkdir()
        (folder / "a.nfo").write_text("x", encoding="utf-8")
        handler = FileHandler(Config())

        results: list[bool] = []
        barrier = threading.Barrier(2)

        def checker() -> None:
            barrier.wait()
            results.append(handler.is_folder_empty_or_removable(folder))

        def injector() -> None:
            barrier.wait()
            (folder / "late.mkv").write_bytes(b"x" * 1024)

        t1 = threading.Thread(target=checker)
        t2 = threading.Thread(target=injector)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Regardless of race winner for the check, safe_delete must refuse once video exists.
        assert (folder / "late.mkv").exists() or results
        if (folder / "late.mkv").exists():
            assert handler.safe_delete_folder(folder) is False
            assert folder.exists()
