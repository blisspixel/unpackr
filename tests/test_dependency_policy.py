from doctor import UnpackrDoctor
from utils.system_check import SystemCheck


def test_system_check_marks_par2_as_non_critical():
    checker = SystemCheck()
    assert checker.REQUIRED_TOOLS["7z"]["critical"] is True
    assert checker.REQUIRED_TOOLS["par2"]["critical"] is False
    assert checker.REQUIRED_TOOLS["ffmpeg"]["critical"] is False


def test_doctor_treats_missing_par2_and_ffmpeg_as_warnings(monkeypatch, capsys):
    doc = UnpackrDoctor()

    def fake_check_tool(tool_name, commands, critical=True):
        if tool_name == "7z":
            return True, "7z"
        return False, None

    monkeypatch.setattr(doc, "check_tool", fake_check_tool)
    doc.check_external_tools()
    capsys.readouterr()

    assert "7-Zip" in doc.passed
    assert "par2cmdline not found - repair capability reduced" in doc.warnings
    assert "ffmpeg not found - video validation will be skipped" in doc.warnings
    assert all("par2cmdline not found" not in issue for issue in doc.issues)

    actions = doc._build_recommended_actions()
    assert any("Install par2cmdline" in action for action in actions)


def test_doctor_version_helpers_extract_and_compare():
    doc = UnpackrDoctor()
    assert doc._extract_version_tuple("7-Zip 24.09 (x64)") == (24, 9, 0)
    assert doc._extract_version_tuple("par2cmdline version 0.8.1") == (0, 8, 1)
    assert doc._extract_version_tuple("ffmpeg version 6.1-full_build") == (6, 1, 0)
    assert doc._extract_version_tuple("no version here") is None

    assert doc._is_version_at_least((24, 9, 0), (22, 0))
    assert doc._is_version_at_least((4, 4, 0), (4, 4))
    assert not doc._is_version_at_least((0, 7, 0), (0, 8, 1))


def test_doctor_versions_old_7z_blocks_old_par2_ffmpeg_warn(monkeypatch):
    doc = UnpackrDoctor()

    def fake_check_tool(tool_name, commands, critical=True):
        return True, tool_name

    def fake_get_version(tool_name, tool_path):
        versions = {
            "7z": (21, 7, 0),      # too old -> issue
            "par2": (0, 7, 0),     # too old -> warning
            "ffmpeg": (4, 3, 0),   # too old -> warning
        }
        return versions.get(tool_name)

    monkeypatch.setattr(doc, "check_tool", fake_check_tool)
    monkeypatch.setattr(doc, "_get_tool_version", fake_get_version)
    doc.check_external_tools()

    assert any("7-Zip version too old" in issue for issue in doc.issues)
    assert any("par2cmdline version too old" in warning for warning in doc.warnings)
    assert any("ffmpeg version too old" in warning for warning in doc.warnings)

    actions = doc._build_recommended_actions()
    assert any("Upgrade 7-Zip" in action for action in actions)
    assert any("Upgrade par2cmdline" in action for action in actions)
    assert any("Upgrade ffmpeg" in action for action in actions)


def test_system_check_old_critical_version_blocks(monkeypatch):
    checker = SystemCheck()

    monkeypatch.setattr(checker, "check_tool", lambda key: key == "7z")
    monkeypatch.setattr(checker, "_evaluate_tool_version", lambda key: (False, "21.7 (need 22.0+)"))
    result = checker.check_all_tools()

    assert result["7z"] is False
    assert checker._version_status["7z"][0] is False


def test_system_check_old_noncritical_version_warns_not_blocks(monkeypatch, capsys):
    checker = SystemCheck()
    status = {"7z": True, "par2": True, "ffmpeg": True}
    checker._version_status = {
        "7z": (True, "24.0"),
        "par2": (False, "0.7 (need 0.8.1+)"),
        "ffmpeg": (True, "6.1"),
    }

    can_proceed = checker.display_tool_status(status)
    out = capsys.readouterr().out
    assert can_proceed is True
    assert "par2cmdline: OLD" in out
