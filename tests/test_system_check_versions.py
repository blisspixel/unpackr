from utils.system_check import SystemCheck


def test_version_helpers_and_formatting():
    checker = SystemCheck()
    assert checker._extract_version_tuple("7-Zip 24.09 (x64)") == (24, 9, 0)
    assert checker._extract_version_tuple("ffmpeg version 6.1-full_build") == (6, 1, 0)
    assert checker._extract_version_tuple("none") is None

    assert checker._is_version_at_least((22, 0, 0), (22, 0))
    assert not checker._is_version_at_least((0, 7, 0), (0, 8, 1))
    assert checker._format_version((22, 0, 0)) == "22.0"
    assert checker._format_version((0, 8, 1)) == "0.8.1"


def test_evaluate_tool_version_paths(monkeypatch):
    checker = SystemCheck()
    monkeypatch.setattr(checker, "_get_tool_version", lambda key: (99, 0, 0))
    ok, msg = checker._evaluate_tool_version("7z")
    assert ok is True
    assert msg == "99.0"

    monkeypatch.setattr(checker, "_get_tool_version", lambda key: (0, 7, 0))
    ok, msg = checker._evaluate_tool_version("par2")
    assert ok is False
    assert "need 0.8.1+" in msg

    monkeypatch.setattr(checker, "_get_tool_version", lambda key: None)
    ok, msg = checker._evaluate_tool_version("ffmpeg")
    assert ok is True
    assert msg == "version unknown"
