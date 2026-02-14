import vhealth


def _checker():
    class Cfg:
        video_extensions = [".mp4", ".mkv", ".avi"]

        def get(self, key, default=None):
            if key == "min_sample_size_mb":
                return 1
            return default

    return vhealth.VideoHealthChecker(Cfg())


def test_check_path_dir_prompt_no_skips_delete(tmp_path, monkeypatch):
    checker = _checker()
    small = tmp_path / "small.mp4"
    small.write_bytes(b"x" * 100)
    big = tmp_path / "big.mp4"
    big.write_bytes(b"x" * (2 * 1024 * 1024))

    monkeypatch.setattr("builtins.input", lambda *_: "n")
    monkeypatch.setattr(checker, "_get_resolution", lambda _p: (1920, 1080))
    monkeypatch.setattr(checker, "_detect_duplicates", lambda _files: None)
    monkeypatch.setattr(checker, "_check_video_silent", lambda _v: "healthy")

    deleted = {"calls": 0}
    monkeypatch.setattr(checker, "_delete_videos", lambda videos: deleted.__setitem__("calls", deleted["calls"] + 1))

    checker.check_path(tmp_path, min_resolution="720p", skip_health=True, delete_bad=False)
    assert deleted["calls"] == 0


def test_check_path_dir_delete_bad_and_health(tmp_path, monkeypatch):
    checker = _checker()
    small = tmp_path / "sample.mp4"
    small.write_bytes(b"x" * 100)
    good = tmp_path / "good.mp4"
    good.write_bytes(b"x" * (2 * 1024 * 1024))
    dupe = tmp_path / "dupe copy.mp4"
    dupe.write_bytes(b"x" * (2 * 1024 * 1024))

    monkeypatch.setattr(checker, "_get_resolution", lambda _p: (1920, 1080))
    monkeypatch.setattr(checker, "_check_video_silent", lambda v: "healthy" if v == good else "CORRUPT")

    def fake_detect(files):
        checker.duplicate_videos = [(dupe, good, "pattern")]

    monkeypatch.setattr(checker, "_detect_duplicates", fake_detect)

    seen = {"deleted": []}

    def fake_delete(videos):
        seen["deleted"].append(sorted(v.name for v in videos))
        for v in videos:
            if v.exists():
                v.unlink()

    monkeypatch.setattr(checker, "_delete_videos", fake_delete)
    checker.check_path(tmp_path, min_resolution="720p", skip_health=False, delete_bad=True)

    # First deletion: sample/low-res bucket, second deletion: duplicates/corrupt bucket.
    assert any("sample.mp4" in batch for batch in seen["deleted"])
    assert any("dupe copy.mp4" in batch or "good.mp4" in batch for batch in seen["deleted"])
