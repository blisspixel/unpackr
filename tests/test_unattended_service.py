"""Unattended runs and the systemd user service (issue #9)."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.unattended import RunLock, notification_text, send_notification, settling_entries
from utils import service as svc
from utils.cli_subcommands import run_subcommand

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Lock, settling, notifications
# ---------------------------------------------------------------------------


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


class TestSettling:
    def test_recent_entries_are_settling(self, tmp_path):
        old, fresh, deep = tmp_path / "Old.Release", tmp_path / "Fresh.Release", tmp_path / "Deep.Release"
        for folder in (old, fresh, deep):
            (folder / "sub").mkdir(parents=True)
            (folder / "sub" / "a.mkv").write_bytes(b"x")
        (tmp_path / ".unpackr-runs").mkdir()
        now = time.time()
        for path in [*old.rglob("*"), old, *deep.rglob("*"), deep, tmp_path / ".unpackr-runs"]:
            os.utime(path, (now - 3600, now - 3600))
        os.utime(deep / "sub" / "a.mkv", (now - 10, now - 10))  # a file deep inside is still growing
        assert settling_entries(tmp_path, 120, now=now) == {fresh, deep}
        assert settling_entries(tmp_path, 0, now=now) == set()


class TestNotifications:
    def test_quiet_runs_send_nothing(self):
        assert notification_text({"videos_moved": 0}, []) is None

    def test_text(self):
        title, body = notification_text({"videos_moved": 3, "archives_extracted": 1}, ["[x] Rel/a: bad"])
        assert title == "unpackr"
        assert body.startswith("3 videos moved, 1 archive extracted, 1 item needs attention")
        assert "[x] Rel/a: bad" in body

    def test_send_uses_notify_send_when_present(self, monkeypatch):
        calls = []
        monkeypatch.setattr("core.unattended.shutil.which", lambda _name: "/usr/bin/notify-send")
        assert send_notification("t", "b", runner=lambda args, **_k: calls.append(args))
        assert calls[0][:2] == ["/usr/bin/notify-send", "--app-name=unpackr"]
        monkeypatch.setattr("core.unattended.shutil.which", lambda _name: None)
        assert not send_notification("t", "b", runner=lambda *_a, **_k: pytest.fail("should not run"))


# ---------------------------------------------------------------------------
# Service units
# ---------------------------------------------------------------------------


class FakeSystemctl:
    def __init__(self):
        self.calls = []

    def __call__(self, args, **_kwargs):
        self.calls.append(args[2:])
        out = ""
        if args[2] == "is-enabled":
            out = "enabled\n"
        elif args[2] == "is-active":
            out = "active\n"
        elif args[2] == "show" and args[3].endswith(".timer"):
            out = "NextElapseUSecRealtime=Sun 2026-10-11 05:00:00 UTC\n"
        elif args[2] == "show":
            out = "Result=success\nExecMainStatus=0\nExecMainExitTimestamp=Sun 2026-10-11 04:45:00 UTC\n"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(svc, "systemd_available", lambda runner=None: None)
    monkeypatch.setattr(svc.shutil, "which", lambda name: f"/usr/bin/{name}")
    return tmp_path


def _dirs(tmp_path):
    src, dst = tmp_path / "My Downloads", tmp_path / "Videos"
    src.mkdir()
    dst.mkdir()
    return src, dst


class TestUnits:
    def test_plan_contents(self, tmp_path):
        src, dst = _dirs(tmp_path)
        plan = svc.build_plan(src, dst, every="30m", config=tmp_path / "100%.json")
        service = plan.units[f"{plan.name}.service"]
        assert "Type=oneshot" in service and "SuccessExitStatus=3" in service
        assert f'--source "{src}"' in service  # spaces quoted for systemd
        assert "100%%.json" in service  # % escaped
        assert service.rstrip().splitlines()[-4].endswith("--notify") or "--notify" in service
        timer = plan.units[f"{plan.name}.timer"]
        assert "OnUnitInactiveSec=30m" in timer and "OnActiveSec=1min" in timer
        assert f"{plan.name}.path" not in plan.units
        assert plan.activations() == [f"{plan.name}.timer"]
        on_change = svc.build_plan(src, dst, on_change=True, notify=False)
        assert f"PathChanged={src}" in on_change.units[f"{on_change.name}.path"]
        assert "--notify" not in on_change.units[f"{on_change.name}.service"]

    def test_name_is_stable_per_source(self, tmp_path):
        assert svc.unit_name(tmp_path / "a") == svc.unit_name(tmp_path / "a") != svc.unit_name(tmp_path / "b")

    @pytest.mark.parametrize("span,ok", [("15m", True), ("1h", True), ("30min", True), ("90", True), ("soon", False), ("1w", False)])
    def test_timespans(self, span, ok):
        assert svc.valid_timespan(span) is ok

    def test_unsupported_platform_explains(self, monkeypatch):
        monkeypatch.setattr(svc.sys, "platform", "darwin")
        assert "launchd" in svc.systemd_available()


class TestInstallLifecycle:
    def test_requires_confirmation(self, home):
        src, dst = _dirs(home)
        out = []
        code = svc.install(svc.build_plan(src, dst), write=out.append, interactive=False, runner=FakeSystemctl())
        assert code == 1 and "--yes" in out[-1]
        assert not (home / "config" / "systemd").exists()
        declined = svc.install(svc.build_plan(src, dst), write=out.append, interactive=True, ask=lambda _q: "n", runner=FakeSystemctl())
        assert declined == 1 and not (home / "config" / "systemd").exists()

    def test_install_status_uninstall(self, home):
        src, dst = _dirs(home)
        fake = FakeSystemctl()
        plan = svc.build_plan(src, dst, on_change=True)
        out = []
        assert svc.install(plan, assume_yes=True, write=out.append, runner=fake) == 0
        written = [Path(line.removeprefix("Wrote ")) for line in out if line.startswith("Wrote ")]
        assert len(written) == 4 and all(p.is_file() for p in written)  # service, timer, path, manifest
        assert ["daemon-reload"] in fake.calls
        assert ["enable", "--now", f"{plan.name}.timer", f"{plan.name}.path"] in fake.calls

        status_out = []
        assert svc.status(as_json=True, write=status_out.append, runner=fake) == 0
        row = json.loads(status_out[0])["services"][0]
        assert row["source"] == str(src) and row[f"{plan.name}.timer"] == {"enabled": "enabled", "active": "active"}
        assert row["last_run"]["exit_status"] == "0" and row["next_run"].startswith("Sun")

        removed = []
        assert svc.uninstall(source=src, write=removed.append, runner=fake) == 0
        assert sorted(Path(line.removeprefix("Removed ")) for line in removed) == sorted(written)
        assert not any(p.exists() for p in written)
        assert not (home / "config" / "unpackr").exists()  # empty folders install created are gone too
        assert ["disable", "--now", f"{plan.name}.timer", f"{plan.name}.path"] in fake.calls

    def test_cli_install_and_uninstall(self, home, monkeypatch, capsys):
        src, dst = _dirs(home)
        monkeypatch.setattr(svc.subprocess, "run", FakeSystemctl())
        assert run_subcommand(["service", "install", "--source", str(src), "--destination", str(dst), "--every", "5m", "--yes"]) == 0
        assert "OnUnitInactiveSec=5m" in capsys.readouterr().out
        assert run_subcommand(["service", "status"]) == 0
        assert str(src) in capsys.readouterr().out
        assert run_subcommand(["service", "uninstall", "--all"]) == 0
        assert not (home / "config" / "unpackr").exists()

    def test_cli_rejects_bad_interval(self, home):
        src, dst = _dirs(home)
        with pytest.raises(SystemExit):
            run_subcommand(["service", "install", "--source", str(src), "--destination", str(dst), "--every", "soon"])


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")


def _video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=duration=14:size=320x240:rate=25",
         "-c:v", "libx264", "-b:v", "3M", "-y", str(path)],
        check=True,
    )  # fmt: skip


def _age(path: Path, seconds: float) -> None:
    then = time.time() - seconds
    for p in [*path.rglob("*"), path]:
        os.utime(p, (then, then))


def _run(src, dst, config, *extra):
    return subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--json", *extra],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
    )  # fmt: skip


def _summary(result):
    return json.loads(result.stdout[result.stdout.index("{\n") :])


@pytest.fixture
def six(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    dst.mkdir()
    for i in range(1, 7):
        _video(src / f"Rel.{i}" / f"Rel.{i}.mkv")
        (src / f"Rel.{i}" / f"Rel.{i}.nfo").write_text("info")
    _age(src, 3600)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs"), "settle_minutes": 1}))
    return src, dst, config


@needs_ffmpeg
def test_unattended_run_is_quick_and_plain(six):
    src, dst, config = six
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "unpackr.py", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--unattended"],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    elapsed = time.monotonic() - start
    assert result.returncode == 0, result.stdout[-2000:]
    assert len(list(dst.iterdir())) == 6
    assert "\r" not in result.stdout and "\x1b[" not in result.stdout  # nothing redrawn: clean in a journal
    assert re.search(r"^\[6/6\] Rel\.\d$", result.stdout, re.MULTILINE)  # one plain line per folder
    assert elapsed < 10  # about 1.5 s locally (#9 target: under 2 s); generous for CI runners


@needs_ffmpeg
def test_growing_folder_is_skipped_then_processed(six):
    src, dst, config = six
    (src / "Rel.3" / "Rel.3.nfo").write_text("still arriving")  # fresh write inside one release
    first = _summary(_run(src, dst, config, "--unattended"))
    assert any("folder_still_growing" in w for w in first["warnings"])
    assert (src / "Rel.3" / "Rel.3.mkv").exists() and len(list(dst.iterdir())) == 5
    _age(src / "Rel.3", 3600)
    second = _run(src, dst, config, "--unattended")
    assert second.returncode == 0 and (dst / "Rel.3.mkv").exists()


@needs_ffmpeg
def test_overlapping_run_exits_cleanly(six):
    src, dst, config = six
    lock = RunLock(src)
    assert lock.acquire()
    try:
        unattended = _run(src, dst, config, "--unattended")
        assert unattended.returncode == 0 and _summary(unattended)["status"] == "skipped"
        manual = _run(src, dst, config)
        assert manual.returncode == 1 and any("run_locked" in e for e in _summary(manual)["errors"])
        assert not list(dst.iterdir())
    finally:
        lock.release()
