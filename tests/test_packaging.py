"""Regression tests for installable command and data-file metadata."""

from pathlib import Path
import runpy

import setuptools


def test_setup_includes_cli_modules_and_bundled_config(monkeypatch):
    setup_kwargs = {}

    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: setup_kwargs.update(kwargs))
    runpy.run_path(str(Path(__file__).parents[1] / "setup.py"), run_name="__setup_test__")

    assert set(setup_kwargs["py_modules"]) == {"doctor", "unpackr", "vhealth"}
    assert "config_files" in setup_kwargs["packages"]
    assert setup_kwargs["package_data"]["config_files"] == ["comments.sample.json", "config.json"]
    assert setup_kwargs["exclude_package_data"]["config_files"] == ["comments.json"]
    assert "build_py" in setup_kwargs["cmdclass"]
    assert setup_kwargs["version"] == "1.3.1"
    assert setup_kwargs["url"] == "https://github.com/blisspixel/unpackr"
    assert "Programming Language :: Python :: 3.14" in setup_kwargs["classifiers"]
    assert (Path(__file__).parents[1] / "LICENSE").is_file()
