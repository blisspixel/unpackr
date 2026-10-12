"""
Preservation threshold matrix for pre-scan classification and deletion guards.

Contracts: docs/PRESERVATION.md
  - Music/documents: inclusive count >= min_*
  - Images: count >= min_image_files AND total size > 10 MB
  - Video/archive presence classifies as video work, not content preserve
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest

from core.config import Config
from core.file_handler import RELEASE_IMAGE_COLLECTION_FILES, FileHandler
from unpackr import UnpackrApp


@pytest.fixture
def default_config() -> Config:
    return Config()


@pytest.fixture
def app(default_config: Config) -> UnpackrApp:
    """Minimal app shell so scan_and_plan uses real Config thresholds."""
    return UnpackrApp.__new__(UnpackrApp)  # type: ignore[misc]


def _wire_app(app: UnpackrApp, config: Config) -> UnpackrApp:
    app.config = config
    app.work_plan = None
    return app


def _content_names(plan) -> set[str]:
    return {Path(item["path"]).name for item in plan.content_folders}


def _junk_names(plan) -> set[str]:
    return {Path(p).name for p in plan.junk_folders}


def _video_names(plan) -> set[str]:
    return {Path(item["path"]).name for item in plan.video_folders}


def _write_files(folder: Path, names: Iterable[str], size: int = 64) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = b"x" * size
    for name in names:
        (folder / name).write_bytes(payload)


class TestPreScanMusicThresholds:
    def test_exactly_min_music_files_is_preserved(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "album"
        n = default_config.min_music_files
        _write_files(folder, [f"track{i:02d}.mp3" for i in range(n)])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "album" in _content_names(plan)
        assert "album" not in _junk_names(plan)
        assert any("music" in item["reason"] for item in plan.content_folders if Path(item["path"]).name == "album")

    def test_one_below_min_music_is_junk(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "almost_album"
        n = default_config.min_music_files - 1
        assert n >= 0
        _write_files(folder, [f"track{i:02d}.mp3" for i in range(n)])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "almost_album" in _junk_names(plan)
        assert "almost_album" not in _content_names(plan)


class TestPreScanDocumentThresholds:
    def test_exactly_min_documents_is_preserved(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "papers"
        n = default_config.min_documents
        _write_files(folder, [f"doc{i:02d}.pdf" for i in range(n)])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "papers" in _content_names(plan)
        assert any("document" in item["reason"] for item in plan.content_folders if Path(item["path"]).name == "papers")

    def test_one_below_min_documents_is_junk(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "few_docs"
        n = default_config.min_documents - 1
        _write_files(folder, [f"doc{i:02d}.pdf" for i in range(n)])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "few_docs" in _junk_names(plan)
        assert "few_docs" not in _content_names(plan)


class TestPreScanKeepsAnyPhotosMusicOrDocuments:
    """A folder without videos or archives is kept if it holds any photos, music or documents."""

    @pytest.mark.parametrize(
        ("names", "size"),
        [
            ([f"img{i:02d}.jpg" for i in range(15)], 200 * 1024),  # small photo folder, ~3MB
            (["only.png"], 50 * 1024),  # a single picture
            (["01.mp3", "02.mp3", "03.mp3"], 10 * 1024),  # a 3-track single
            (["paper.pdf"], 10 * 1024),
        ],
    )
    def test_any_content_is_preserved(self, app, default_config, tmp_path, names, size):
        source = tmp_path / "source"
        source.mkdir()
        _write_files(source / "stuff", names, size=size)

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "stuff" in _content_names(plan)
        assert "stuff" not in _junk_names(plan)

    def test_junk_text_does_not_count_as_a_document(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        _write_files(source / "junk", ["readme.txt", "site.url", "info.nfo"])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "junk" in _junk_names(plan)

    def test_thresholds_can_be_raised(self, app, tmp_path):
        config = Config()
        config.set("min_image_files", 10)
        source = tmp_path / "source"
        source.mkdir()
        _write_files(source / "thumbs", [f"t{i}.jpg" for i in range(3)])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, config), source)

        assert "thumbs" in _junk_names(plan)


class TestPreScanPriorityAndMixed:
    def test_video_presence_classifies_as_video_not_content(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "mixed"
        n = default_config.min_music_files
        _write_files(folder, [f"track{i:02d}.mp3" for i in range(n)])
        (folder / "movie.mkv").write_bytes(b"x" * 1024)

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "mixed" in _video_names(plan)
        assert "mixed" not in _content_names(plan)
        assert "mixed" not in _junk_names(plan)

    def test_archive_presence_classifies_as_video_work(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "packed"
        folder.mkdir()
        (folder / "release.rar").write_bytes(b"x")
        _write_files(folder, [f"doc{i:02d}.pdf" for i in range(default_config.min_documents)])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "packed" in _video_names(plan)
        assert "packed" not in _content_names(plan)

    def test_emptyish_folder_is_junk(self, app, default_config, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        folder = source / "emptyish"
        _write_files(folder, ["readme.nfo", "note.txt"])

        plan = UnpackrApp.scan_and_plan(_wire_app(app, default_config), source)

        assert "emptyish" in _junk_names(plan)


class TestDeletionGuardAlignment:
    """Pre-scan image rule must match is_folder_empty_or_removable image guard."""

    def test_handler_preserves_release_image_collection(self, default_config, tmp_path):
        folder = tmp_path / "gallery"
        n = RELEASE_IMAGE_COLLECTION_FILES
        _write_files(folder, [f"img{i:02d}.jpg" for i in range(n)], size=1100 * 1024)
        handler = FileHandler(default_config)
        assert handler.is_folder_empty_or_removable(folder) is False

    def test_handler_allows_delete_when_size_not_over_10mb(self, default_config, tmp_path):
        folder = tmp_path / "thumbs"
        n = RELEASE_IMAGE_COLLECTION_FILES
        _write_files(folder, [f"thumb{i:02d}.jpg" for i in range(n)], size=500 * 1024)
        handler = FileHandler(default_config)
        assert handler.is_folder_empty_or_removable(folder) is True

    def test_handler_allows_delete_at_exactly_10mb(self, default_config, tmp_path):
        folder = tmp_path / "edge"
        n = default_config.min_image_files
        _write_files(folder, [f"img{i:02d}.jpg" for i in range(n)], size=1024 * 1024)
        handler = FileHandler(default_config)
        assert handler.is_folder_empty_or_removable(folder) is True
