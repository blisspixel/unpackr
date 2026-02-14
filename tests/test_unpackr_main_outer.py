import pytest

import unpackr


def test_main_outer_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(unpackr, "build_unpackr_arg_parser", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 0


def test_main_outer_unexpected_exception(monkeypatch):
    monkeypatch.setattr(unpackr, "build_unpackr_arg_parser", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1


def test_main_config_load_failure_branch(monkeypatch, tmp_path):
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()

    monkeypatch.setattr(unpackr, "Config", lambda *_: (_ for _ in ()).throw(RuntimeError("bad cfg")))
    monkeypatch.setattr(unpackr, "setup_logging", lambda *_: tmp_path / "run.log")
    monkeypatch.setattr(unpackr.sys, "argv", ["unpackr", str(source), str(dest)])
    with pytest.raises(SystemExit) as exc:
        unpackr.main()
    assert exc.value.code == 1
