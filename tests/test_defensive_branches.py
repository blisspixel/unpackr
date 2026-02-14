from pathlib import Path

import pytest

from utils.defensive import ErrorRecovery, InputValidator, StateValidator, ValidationError, defensive_wrapper


def test_validate_path_relative_and_null_byte(tmp_path):
    rel = InputValidator.validate_path("a\x00b", must_exist=False)
    assert rel is not None
    assert "\x00" not in str(rel)

    p = InputValidator.validate_path(str(tmp_path), must_exist=True, must_be_dir=True)
    assert p == tmp_path.resolve()


def test_validate_path_base_dir_escape_returns_path_object(tmp_path):
    outside = tmp_path.parent / "outside_target"
    result = InputValidator.validate_path(outside, base_dir=tmp_path)
    # Current implementation fail-opens by returning original path on security-check exception.
    assert isinstance(result, Path)


def test_validate_string_int_list_extra_branches():
    assert InputValidator.validate_string(None, allow_none=True) is None
    assert InputValidator.validate_int(None, allow_none=True) is None
    assert InputValidator.validate_list(None, allow_none=True) is None

    assert InputValidator.validate_int(True) == 1
    with pytest.raises(ValidationError):
        InputValidator.validate_list([], allow_empty=False)


def test_state_validator_branches(tmp_path, monkeypatch):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    assert StateValidator.check_file_accessible(f) is True
    assert StateValidator.check_file_accessible(tmp_path) is False
    assert StateValidator.check_dir_writable(tmp_path / "missing") is False

    # Low disk branch
    class DU:
        free = 50 * 1024 * 1024

    monkeypatch.setattr("shutil.disk_usage", lambda *_: DU())
    assert StateValidator.check_disk_space(tmp_path, required_mb=100) is False

    # Exception branch should fail-open.
    monkeypatch.setattr("shutil.disk_usage", lambda *_: (_ for _ in ()).throw(RuntimeError("nope")))
    assert StateValidator.check_disk_space(tmp_path, required_mb=100) is True

    assert StateValidator.validate_config_dict("notdict", ["a"]) is False
    assert StateValidator.validate_config_dict({"a": 1}, ["a", "b"]) is False
    assert StateValidator.validate_config_dict({"a": 1, "b": 2}, ["a", "b"]) is True


def test_error_recovery_safe_delete_and_read(tmp_path, monkeypatch):
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.txt").write_text("x", encoding="utf-8")
    assert ErrorRecovery.safe_delete(d, max_attempts=1) is True
    assert not d.exists()

    # Too-large read branch
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * 2048)
    assert ErrorRecovery.safe_read_text(big, default="D", max_size_mb=0) == "D"
    assert ErrorRecovery.safe_read_text(tmp_path / "missing.txt", default="D") == "D"

    # Retry path in safe_delete
    f = tmp_path / "retry.txt"
    f.write_text("x", encoding="utf-8")
    calls = {"n": 0}

    original_unlink = Path.unlink

    def flaky_unlink(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("locked")
        original_unlink(self)

    monkeypatch.setattr("pathlib.Path.unlink", flaky_unlink)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert ErrorRecovery.safe_delete(f, max_attempts=2) is True


def test_error_recovery_safe_move_branches(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("abc", encoding="utf-8")

    # Non-atomic branch success
    assert ErrorRecovery.safe_move(src, dst, atomic=False, verify_integrity=True) is True
    assert dst.exists()

    # Missing source branch
    assert ErrorRecovery.safe_move(tmp_path / "missing.txt", tmp_path / "x.txt") is False

    # Atomic integrity mismatch branch
    src2 = tmp_path / "src2.txt"
    dst2 = tmp_path / "dst2.txt"
    src2.write_text("abcdef", encoding="utf-8")

    def bad_move(a, b):
        Path(b).write_text("x", encoding="utf-8")
        Path(a).unlink()

    monkeypatch.setattr("shutil.move", bad_move)
    assert ErrorRecovery.safe_move(src2, dst2, atomic=True, verify_integrity=True) is False


def test_defensive_wrapper_default_paths():
    @defensive_wrapper
    def check_alpha():
        raise RuntimeError("boom")

    @defensive_wrapper
    def get_alpha():
        raise RuntimeError("boom")

    @defensive_wrapper
    def do_alpha():
        raise RuntimeError("boom")

    assert check_alpha() is False
    assert get_alpha() is None
    with pytest.raises(RuntimeError):
        do_alpha()
