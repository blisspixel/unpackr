"""Two runs never process the same downloads folder at once."""

import json
import os
import subprocess
import sys
from pathlib import Path

from core.run_lock import RunLock

REPO = Path(__file__).resolve().parent.parent


class TestRunLock:
    def test_second_holder_is_refused_until_release(self, tmp_path):
        first, second = RunLock(tmp_path), RunLock(tmp_path)
        assert first.acquire()
        assert not second.acquire()
        assert first.holder() == str(os.getpid())
        first.release()
        assert not (tmp_path / ".unpackr-lock").exists()
        assert second.acquire()
        second.release()

    def test_lock_left_by_dead_process_does_not_block(self, tmp_path):
        (tmp_path / ".unpackr-lock").write_text("99999\n")  # file exists but nobody holds it
        lock = RunLock(tmp_path)
        assert lock.acquire()
        lock.release()


def test_second_run_on_the_same_source_exits_cleanly(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "Rel.1").mkdir(parents=True)
    (src / "Rel.1" / "Rel.1.mkv").write_bytes(b"\0" * 100)
    dst.mkdir()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"log_folder": str(tmp_path / "logs")}))
    lock = RunLock(src)
    assert lock.acquire()
    try:
        result = subprocess.run(
            [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(config),
             "--json", "--no-color"],
            capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
        )  # fmt: skip
        summary = json.loads(result.stdout)
        assert result.returncode == 1
        assert any("run_locked" in e for e in summary["errors"])
        assert (src / "Rel.1" / "Rel.1.mkv").exists()
        assert not list(dst.iterdir())
    finally:
        lock.release()


def test_removed_service_command_explains_itself():
    result = subprocess.run(
        [sys.executable, "unpackr.py", "service", "install"], capture_output=True, text=True, timeout=60, cwd=REPO
    )
    assert result.returncode == 2
    assert "removed in 1.6.0" in result.stderr
