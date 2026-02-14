from utils.progress import ProgressTracker


class DummyTqdm:
    def __init__(self, total=None, desc=None, unit=None):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.updated = 0
        self.closed = False
        self.descriptions = []

    def update(self, n):
        self.updated += n

    def close(self):
        self.closed = True

    def set_description(self, desc):
        self.descriptions.append(desc)


def test_progress_tracker_start_update_close(monkeypatch):
    monkeypatch.setattr("utils.progress.tqdm", DummyTqdm)
    tracker = ProgressTracker()

    tracker.start(total=10, desc="Processing", unit="item")
    assert tracker.pbar is not None
    assert tracker.pbar.total == 10

    tracker.update(3, desc="Step 1")
    assert tracker.pbar.updated == 3
    assert tracker.pbar.descriptions == ["Step 1"]

    tracker.close()
    assert tracker.pbar is None


def test_progress_tracker_noop_when_not_started():
    tracker = ProgressTracker()
    tracker.update(1, desc="ignored")
    tracker.close()
    assert tracker.pbar is None


def test_progress_tracker_context_manager_closes(monkeypatch):
    monkeypatch.setattr("utils.progress.tqdm", DummyTqdm)

    with ProgressTracker() as tracker:
        tracker.start(total=2)
        tracker.update()
        internal = tracker.pbar
        assert internal is not None
        assert internal.updated == 1

    assert internal.closed is True
    assert tracker.pbar is None
