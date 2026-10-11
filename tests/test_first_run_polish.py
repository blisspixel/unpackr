"""Regression tests for first-run rough edges (issue #5)."""

import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import unpackr
import vhealth
from core.archive_processor import find_archive_sets
from core.config import Config
from core.logger import resolve_log_dir
from doctor import UnpackrDoctor
from utils import platform_support
from utils.system_check import SystemCheck

REPO = Path(__file__).resolve().parent.parent


class TestLogsAndHints:
    def test_relative_log_folder_goes_to_user_state_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(platform_support, "is_windows", lambda: False)
        monkeypatch.setattr(platform_support, "is_macos", lambda: False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        assert resolve_log_dir("logs") == tmp_path / "state" / "unpackr" / "logs"
        assert resolve_log_dir(str(tmp_path / "abs")) == tmp_path / "abs"

    def test_state_dir_per_platform(self, monkeypatch, tmp_path):
        monkeypatch.setattr(platform_support, "is_windows", lambda: True)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
        assert platform_support.user_state_dir() == tmp_path / "local" / "unpackr"
        monkeypatch.setattr(platform_support, "is_windows", lambda: False)
        monkeypatch.setattr(platform_support, "is_macos", lambda: True)
        assert platform_support.user_state_dir().parts[-3:] == ("Library", "Logs", "unpackr")

    def test_doctor_folds_tool_version_into_one_entry(self):
        doctor = UnpackrDoctor()
        doctor.passed = ["7-Zip"]
        with patch.object(doctor, "_get_tool_version", return_value=(25, 1, 0)):
            doctor._check_tool_min_version("7z", "7-Zip", "7z", critical=True)
        assert doctor.passed == ["7-Zip 25.1"]

    def test_doctor_asks_par2_for_its_version(self):
        doctor = UnpackrDoctor()
        with patch("doctor.subprocess.run") as run:
            run.return_value = types.SimpleNamespace(stdout="par2cmdline version 1.3.0", stderr="")
            assert doctor._get_tool_version("par2", "par2") == (1, 3, 0)
        assert run.call_args.args[0] == ["par2", "-V"]

    def test_recommended_actions_name_tools_once_and_recipe_once(self):
        doctor = UnpackrDoctor()
        doctor.issues = ["7-Zip not found - required for archive extraction"]
        doctor.warnings = ["par2cmdline not found - repair capability reduced", "ffmpeg not found - x"]
        actions = doctor._build_recommended_actions()
        recipe = platform_support.package_manager_install_hint()
        assert sum(recipe in a for a in actions) == 1


class TestPlanAccuracy:
    def test_zip_and_spanned_zip_sets(self, tmp_path):
        for name in ("single.zip", "big.z01", "big.z02", "big.zip", "gap.z01", "gap.z03", "gap.zip"):
            (tmp_path / name).write_bytes(b"x")
        sets = {s.name: s for s in find_archive_sets(tmp_path)}
        assert sets["single.zip"].kind == "zip" and not sets["single.zip"].missing
        assert sets["big.zip"].kind == "zip-spanned" and len(sets["big.zip"].volumes) == 3
        assert sets["big.zip"].first.name == "big.zip"
        assert sets["gap.zip"].missing == ["gap.z02"]

    def _app(self, tmp_path):
        app = unpackr.UnpackrApp(Config())
        app.config.set("min_documents", 10)
        return app

    def test_scan_counts_7z_and_zip_and_keeps_truthful_junk(self, tmp_path):
        src = tmp_path / "src"
        (src / "Only.7z").mkdir(parents=True)
        (src / "Only.7z" / "a.7z").write_bytes(b"x")
        (src / "Zipped").mkdir()
        (src / "Zipped" / "a.zip").write_bytes(b"x")
        (src / "Junk").mkdir()
        (src / "Junk" / "a.nfo").write_text("x")
        (src / "Papers").mkdir()
        (src / "Papers" / "manual.pdf").write_bytes(b"%PDF")
        (src / "loose.ts").write_bytes(b"x")
        app = self._app(tmp_path)
        app.config.set("video_extensions", [".mkv", ".ts"])
        plan = app.scan_and_plan(src)
        by_name = {item["path"].name: item for item in plan.video_folders}
        assert by_name["Only.7z"]["rars"] == 1 and by_name["Zipped"]["rars"] == 1
        assert {f.name for f in plan.junk_folders} == {"Junk", "Papers"}
        assert {f.name for f in plan.junk_kept} == {"Papers"}
        assert [v.name for v in plan.loose_videos] == ["loose.ts"]
        roles = {e["path"]: e["role"] for e in plan.as_plan_entries(src)}
        assert roles["Junk"] == "delete" and roles["Papers"] == "keep" and roles["loose.ts"] == "validate_video"

    def test_detailed_plan_lists_every_folder(self, tmp_path, capsys):
        plan = unpackr.WorkPlan()
        plan.add_video_folder(tmp_path / "V", 1, 2, 0)
        plan.add_junk_folder(tmp_path / "J")
        plan.add_junk_folder(tmp_path / "K")
        plan.junk_kept.add(tmp_path / "K")
        plan.add_loose_video(tmp_path / "loose.mkv")
        plan.display_detailed()
        out = capsys.readouterr().out
        for text in ("FOLDERS TO PROCESS", "FOLDERS TO REMOVE (1", "FOLDERS KEPT AS-IS (1", "LOOSE VIDEOS (1", "2 archive file(s)"):
            assert text in out, text
        assert "RAR extract" not in out


class TestDestinationAndCountdown:
    def _run(self, *args, cwd=REPO):
        return subprocess.run(
            [sys.executable, "unpackr.py", *args, "--no-color"],
            capture_output=True, text=True, timeout=120, cwd=cwd, stdin=subprocess.DEVNULL,
        )  # fmt: skip

    def test_plan_with_missing_destination_does_not_create_it(self, tmp_path):
        (tmp_path / "src" / "A").mkdir(parents=True)
        result = self._run("--source", str(tmp_path / "src"), "--destination", str(tmp_path / "new"), "--show-plan")
        assert result.returncode == 0, result.stdout
        assert "will be created on a live run" in result.stdout
        assert not (tmp_path / "new").exists()

    def test_live_run_creates_destination_and_skips_countdown(self, tmp_path):
        (tmp_path / "src" / "A").mkdir(parents=True)
        (tmp_path / "src" / "A" / "x.nfo").write_text("x")
        config = tmp_path / "c.json"
        config.write_text(json.dumps({"log_folder": str(tmp_path / "logs")}))
        result = self._run(
            "--source", str(tmp_path / "src"), "--destination", str(tmp_path / "new"), "--config", str(config)
        )
        assert result.returncode == 0, result.stdout[-1500:]
        assert (tmp_path / "new").is_dir() and "Created destination" in result.stdout
        assert "Starting processing in" not in result.stdout

    def test_missing_parent_is_an_error(self, tmp_path):
        (tmp_path / "src").mkdir()
        result = self._run("--source", str(tmp_path / "src"), "--destination", str(tmp_path / "a" / "b"), "--dry-run")
        assert result.returncode == 1 and "neither does its parent" in result.stdout


class TestProcessHandling:
    def _proc(self, pid, name, cmdline):
        proc = MagicMock()
        proc.pid = pid
        proc.info = {"pid": pid, "name": name, "cmdline": cmdline}
        return proc

    def test_only_helpers_on_this_source_are_stopped(self, tmp_path, monkeypatch):
        mine = self._proc(1, "7z", ["7z", "x", str(tmp_path / "src" / "a.rar")])
        other = self._proc(2, "ffmpeg", ["ffmpeg", "-i", "/home/me/edit.mov"])
        import psutil

        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: [mine, other])
        monkeypatch.setattr(psutil, "wait_procs", lambda procs, timeout: (procs, []))
        check = SystemCheck()
        monkeypatch.setattr(check, "check_running_processes", lambda: (True, ["7-Zip"]))
        check.source_dir = tmp_path / "src"
        assert check.warn_running_processes() is True
        mine.terminate.assert_called_once()
        other.terminate.assert_not_called()

    def test_dry_run_never_stops_processes(self, tmp_path, monkeypatch):
        mine = self._proc(1, "par2", ["par2", "r", str(tmp_path / "src" / "a.par2")])
        import psutil

        monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: [mine])
        check = SystemCheck()
        monkeypatch.setattr(check, "check_running_processes", lambda: (True, ["par2"]))
        check.source_dir = tmp_path / "src"
        check.dry_run = True
        assert check.warn_running_processes() is True
        mine.terminate.assert_not_called()


class TestVhealthNonInteractive:
    def test_confirm_without_terminal_is_no(self, monkeypatch, capsys):
        checker = vhealth.VideoHealthChecker(Config())
        monkeypatch.setattr(vhealth, "_stdin_is_tty", lambda: False)
        assert checker._confirm("Delete?") is False
        assert "no terminal" in capsys.readouterr().out

    def test_confirm_on_eof_is_no(self, monkeypatch):
        checker = vhealth.VideoHealthChecker(Config())
        monkeypatch.setattr(vhealth, "_stdin_is_tty", lambda: True)

        def eof(*_a):
            raise EOFError

        monkeypatch.setattr("builtins.input", eof)
        assert checker._confirm("Delete?") is False

    def test_assume_yes(self):
        checker = vhealth.VideoHealthChecker(Config())
        checker.assume = True
        assert checker._confirm("Delete?") is True

    def test_preview_verdict_counts_as_sample_once(self, tmp_path):
        checker = vhealth.VideoHealthChecker(Config())
        video = tmp_path / "clip.mkv"
        video.write_bytes(b"\0" * (2 * 1024 * 1024))
        checker.skip_samples = True

        def fake_health(path, check_quality=False):
            from core.video_processor import VideoVerdict

            checker.video_processor.last_verdict = VideoVerdict(False, "preview", "video_too_short", "8.0s is under")
            return (False, False, None, None)

        checker.video_processor.check_video_health = fake_health
        assert "SAMPLE" in checker._check_video_silent(video)
        checker._check_video_silent(video)
        assert checker.sample_videos == [video] and checker.corrupt_videos == []

    def test_json_mode_prints_only_json(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        result = subprocess.run(
            [sys.executable, "vhealth.py", str(tmp_path), "--json"],
            capture_output=True, text=True, timeout=120, cwd=REPO, stdin=subprocess.DEVNULL,
        )  # fmt: skip
        payload = json.loads(result.stdout)
        assert payload["tool"] == "vhealth" and payload["exit_code"] == 0


@pytest.mark.parametrize("flag", ["--yes", "--no", "--no-color", "--json"])
def test_vhealth_parser_accepts_new_flags(flag):
    args = vhealth.build_vhealth_arg_parser().parse_args(["/tmp", flag])
    assert args.path == "/tmp"
