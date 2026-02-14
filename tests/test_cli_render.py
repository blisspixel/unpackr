from utils import cli_render


def test_create_renderer_prefers_plain_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    renderer = cli_render.create_renderer()
    assert renderer is None


def test_create_renderer_respects_no_anim(monkeypatch):
    monkeypatch.setenv("UNPACKR_NO_ANIM", "1")
    renderer = cli_render.create_renderer()
    assert renderer is None


def test_create_renderer_respects_no_anim_truthy_variants(monkeypatch):
    monkeypatch.setenv("UNPACKR_NO_ANIM", "true")
    renderer = cli_render.create_renderer()
    assert renderer is None


def test_plain_renderer_update_and_stop():
    renderer = cli_render.PlainRenderer()
    renderer.start(10)
    renderer.update(
        current=1,
        total=10,
        action="Scanning folder: demo",
        verb="scanning",
        target="demo",
        stats_line="stats",
        time_line="time",
        comment_line="comment",
    )
    renderer.stop()


def test_create_renderer_off_mode():
    assert cli_render.create_renderer(mode="off") is None


def test_create_renderer_light_non_tty_returns_none(monkeypatch):
    class DummyStdout:
        def isatty(self):
            return False

    monkeypatch.setattr(cli_render.sys, "stdout", DummyStdout())
    monkeypatch.delenv("CI", raising=False)
    renderer = cli_render.create_renderer(mode="light")
    assert renderer is None


def test_create_renderer_rich_failure_falls_back_plain(monkeypatch):
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(cli_render.sys, "stdout", DummyStdout())
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("UNPACKR_NO_ANIM", raising=False)
    monkeypatch.setattr(cli_render, "RichRenderer", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    renderer = cli_render.create_renderer(mode="full")
    assert isinstance(renderer, cli_render.PlainRenderer)


def test_create_renderer_ci_zero_does_not_force_disable(monkeypatch):
    class DummyStdout:
        def isatty(self):
            return True

    class DummyRenderer:
        pass

    monkeypatch.setattr(cli_render.sys, "stdout", DummyStdout())
    monkeypatch.setenv("CI", "0")
    monkeypatch.delenv("UNPACKR_NO_ANIM", raising=False)
    monkeypatch.setattr(cli_render, "RichRenderer", lambda **_kwargs: DummyRenderer())
    renderer = cli_render.create_renderer(mode="light")
    assert isinstance(renderer, DummyRenderer)
