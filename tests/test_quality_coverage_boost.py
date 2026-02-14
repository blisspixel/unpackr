"""Targeted coverage boosts for low-covered application modules."""

import logging
import types

from core import logger as core_logger
from doctor import UnpackrDoctor
from utils.dry_run_summary import DryRunPlan
from utils.system_check import SystemCheck


def test_dry_run_plan_format_size_boundaries():
    plan = DryRunPlan()
    assert plan.format_size(10) == "10 B"
    assert plan.format_size(1024) == "1.0 KB"
    assert plan.format_size(1024 * 1024) == "1.0 MB"
    assert plan.format_size(1024 * 1024 * 1024) == "1.00 GB"


def test_dry_run_plan_summary_prints_sections(capsys, tmp_path):
    plan = DryRunPlan()
    archive = tmp_path / "a.rar"
    video = tmp_path / "v.mkv"
    junk = tmp_path / "info.nfo"
    folder = tmp_path / "keep"
    plan.add_par2_process(tmp_path, 2)
    plan.add_archive_extract(archive, 2048)
    plan.add_archive_skip(archive, "bad")
    plan.add_video_move(video, 4096, "1920x1080")
    plan.add_video_delete(video, "sample")
    plan.add_video_skip(video, "corrupt")
    plan.add_junk_file(junk)
    plan.add_folder_delete(tmp_path)
    plan.add_folder_keep(folder, "music collection")

    plan.print_summary()
    out = capsys.readouterr().out
    assert "DRY RUN SUMMARY" in out
    assert "PAR2 VERIFICATION/REPAIR" in out
    assert "ARCHIVES" in out
    assert "VIDEOS" in out
    assert "CLEANUP" in out
    assert "SUMMARY:" in out


def test_doctor_recommended_actions_and_to_dict():
    doctor = UnpackrDoctor()
    doctor.issues = [
        "Python version too old",
        "7-Zip not found - required for RAR extraction",
        "Missing packages: colorama",
    ]
    doctor.warnings = ["ffmpeg not found - video validation will be skipped"]
    doctor.passed = ["Config"]

    actions = doctor._build_recommended_actions()
    assert any("Python 3.11+" in a for a in actions)
    assert any("7-Zip" in a for a in actions)
    assert any("pip install -e ." in a for a in actions)
    assert any("ffmpeg" in a for a in actions)
    assert actions[-1].startswith("Re-run `unpackr-doctor`")

    payload = doctor.to_dict(exit_code=1)
    assert payload["status"] == "blocked"
    assert payload["exit_code"] == 1
    assert payload["counts"]["issues"] == 3


def test_system_check_tool_command_and_display(capsys):
    checker = SystemCheck(config={"tool_paths": {"7z": ["C:/x/7z.exe"]}})
    checker._working_paths = {"7z": "7z"}

    assert checker.get_tool_command("7z") == ["7z"]
    assert checker.get_tool_command("par2") == ["par2"]
    assert checker.get_tool_command("missing") == []

    can_continue = checker.display_tool_status({"7z": True, "par2": False, "ffmpeg": False})
    out = capsys.readouterr().out
    assert can_continue is True
    assert "SKIP" in out
    assert "Critical tools missing" not in out


def test_system_check_process_conflicts_linux(monkeypatch):
    checker = SystemCheck()
    monkeypatch.setattr("utils.system_check.sys.platform", "linux")
    monkeypatch.setattr(
        "utils.system_check.subprocess.run",
        lambda *args, **kwargs: types.SimpleNamespace(stdout="7z something\npar2 doing work"),
    )

    has_conflicts, running = checker.check_running_processes()
    assert has_conflicts is True
    assert "7-Zip" in running
    assert "par2" in running


def test_system_check_kill_processes_windows(monkeypatch):
    checker = SystemCheck()
    monkeypatch.setattr("utils.system_check.sys.platform", "win32")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("utils.system_check.subprocess.run", fake_run)
    assert checker.kill_processes(["7-Zip", "par2"]) is True
    assert any("taskkill" in c[0].lower() for c in calls)


def test_logger_setup_cleanup_and_subprocess_error(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    # Create old logs and ensure cleanup trims count.
    for idx in range(4):
        (logs_dir / f"unpackr-20200101-00000{idx}.log").write_text("x", encoding="utf-8")
    core_logger.cleanup_old_logs(logs_dir, max_files=2)
    assert len(list(logs_dir.glob("unpackr-*.log"))) == 2

    # setup_logging should create a file and register handler.
    log_file = core_logger.setup_logging(str(logs_dir), max_log_files=3)
    assert log_file.exists()

    # log_subprocess_error should log details without raising.
    class FakeErr:
        returncode = 2
        cmd = ["tool", "--arg"]
        output = "boom"

    core_logger.log_subprocess_error(FakeErr(), "tool")

    # Prevent handler accumulation across tests.
    root_logger = logging.getLogger()
    root_logger.handlers = []
