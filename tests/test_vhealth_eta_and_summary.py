import vhealth


def _checker():
    class Cfg:
        video_extensions = [".mp4"]

        def get(self, key, default=None):
            if key == "min_sample_size_mb":
                return 0
            return default

    return vhealth.VideoHealthChecker(Cfg())


def test_check_path_eta_and_spinner_branches(tmp_path, monkeypatch):
    checker = _checker()
    files = []
    for i in range(10):
        p = tmp_path / f"v{i}.mp4"
        p.write_bytes(b"x")
        files.append(p)

    # Force one early bad result so spinner branch with bad_count executes on later iterations.
    calls = {"n": 0}

    def check_silent(_v):
        calls["n"] += 1
        return "bad" if calls["n"] == 1 else "healthy"

    checker._check_video_silent = check_silent
    checker._detect_duplicates = lambda _files: None
    checker._find_videos = lambda _path: files

    # Deterministic one-shot spinner execution.
    class OneShotEvent:
        def __init__(self):
            self._seen = False

        def is_set(self):
            if not self._seen:
                self._seen = True
                return False
            return True

        def set(self):
            self._seen = True

    class InlineThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

        def join(self, timeout=None):
            pass

    monkeypatch.setattr("threading.Event", OneShotEvent)
    monkeypatch.setattr("threading.Thread", InlineThread)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    # Large elapsed times to trigger ETA hour/minute branches.
    t = {"v": 0.0}

    def fake_time():
        t["v"] += 1000.0
        return t["v"]

    monkeypatch.setattr("time.time", fake_time)
    checker.check_path(tmp_path, skip_samples=True, skip_health=False, delete_bad=False)


def test_print_summary_prompt_and_delete_branches(tmp_path, monkeypatch, capsys):
    checker = _checker()
    corrupt = tmp_path / "c.mp4"
    sample = tmp_path / "s.mp4"
    low = tmp_path / "l.mp4"
    dup = tmp_path / "d.mp4"
    keep = tmp_path / "k.mp4"
    for p in [corrupt, sample, low, dup, keep]:
        p.write_bytes(b"x")

    checker.corrupt_videos = [corrupt]
    checker.sample_videos = [sample]
    checker.low_res_videos = [(low, (640, 480))]
    checker.duplicate_videos = [(dup, keep, "same hash")]
    checker.potential_duplicates = [(dup, keep, 0.9)]

    seen = {"deleted": None, "prompted": 0}

    def fake_delete(videos):
        seen["deleted"] = sorted(v.name for v in videos)

    def fake_prompt(videos):
        seen["prompted"] += 1

    checker._delete_videos = fake_delete
    checker._prompt_delete = fake_prompt
    checker.print_summary(auto_delete=False)
    assert seen["prompted"] == 1

    checker.print_summary(auto_delete=True)
    assert seen["deleted"] is not None
    out = capsys.readouterr().out
    assert "Potential duplicates" in out

    # Prompt helper direct yes/no branches.
    checker2 = _checker()
    checker2._delete_videos = fake_delete
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    checker2._prompt_delete([corrupt])
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    checker2._prompt_delete([corrupt])
