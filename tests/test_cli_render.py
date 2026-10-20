from unpackr.utils import cli_render


def test_create_renderer_prefers_none_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert cli_render.create_renderer() is None


def test_create_renderer_respects_no_anim(monkeypatch):
    monkeypatch.setenv("UNPACKR_NO_ANIM", "1")
    assert cli_render.create_renderer() is None


def test_create_renderer_respects_no_anim_truthy_variants(monkeypatch):
    monkeypatch.setenv("UNPACKR_NO_ANIM", "true")
    assert cli_render.create_renderer() is None


def test_dashboard_renderer_update_and_stop(capsys, monkeypatch):
    monkeypatch.setattr(cli_render, "terminal_width", lambda: 60)
    renderer = cli_render.DashboardRenderer()
    renderer.start(10)
    renderer.update(
        current=1,
        total=10,
        action="Scanning folder: demo",
        verb="scanning",
        target="demo",
        stats_line="found 1",
        time_line="speed: ---",
        comment_line="comment",
    )
    renderer.stop()
    out = capsys.readouterr().out
    assert "\x1b[2J" not in out
    assert "scanning" in out
    assert "demo" in out


def test_create_renderer_off_mode():
    assert cli_render.create_renderer(mode="off") is None


def test_create_renderer_light_non_tty_returns_none(monkeypatch):
    class DummyStdout:
        def isatty(self):
            return False

    monkeypatch.setattr(cli_render.sys, "stdout", DummyStdout())
    monkeypatch.delenv("CI", raising=False)
    assert cli_render.create_renderer(mode="light") is None


def test_create_renderer_no_color_returns_none(monkeypatch):
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(cli_render.sys, "stdout", DummyStdout())
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("UNPACKR_NO_ANIM", raising=False)
    assert cli_render.create_renderer(mode="full", no_color=True) is None


def test_create_renderer_tty_returns_dashboard(monkeypatch):
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(cli_render.sys, "stdout", DummyStdout())
    monkeypatch.setenv("CI", "0")
    monkeypatch.delenv("UNPACKR_NO_ANIM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    renderer = cli_render.create_renderer(mode="light")
    assert isinstance(renderer, cli_render.DashboardRenderer)
