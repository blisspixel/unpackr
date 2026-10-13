"""Regression tests for installable command and data-file metadata."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_wheel_exposes_only_the_unpackr_package(tmp_path):
    wheel_dir = tmp_path / "wheels"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheel_dir), str(ROOT)]
    )
    wheels = list(wheel_dir.glob("unpackr-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = wheel.read(metadata_name).decode()
    tops = {Path(name).parts[0] for name in names}
    assert "unpackr" in tops
    assert all(top == "unpackr" or top.endswith(".dist-info") for top in tops)
    assert any(name.endswith("unpackr/config_files/config.json") for name in names)
    assert any(name.endswith("unpackr/config_files/comments.sample.json") for name in names)
    assert not any(name.endswith("/comments.json") or name == "comments.json" for name in names)
    forbidden = ("core/", "utils/", "doctor.py", "vhealth.py", "unpackr.py", "version.py")
    assert not any(name.startswith(forbidden) for name in names)
    assert "Version: 1.6.2" in metadata
    assert "Requires-Python: >=3.12" in metadata
    assert "https://github.com/blisspixel/unpackr" in metadata
    assert "Apache 2.0 with Commons Clause" in metadata
    assert "Programming Language :: Python :: 3.15" in metadata
    assert "Programming Language :: Python :: 3.11" not in metadata
    assert "Operating System :: POSIX :: Linux" in metadata
    assert "Operating System :: MacOS" in metadata
    assert "setuptools>=68" in metadata
    assert (ROOT / "LICENSE").is_file()


def test_uv_tool_install_exposes_commands(tmp_path):
    """The documented isolated install must expose the three commands and bundled config."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    tool_dir = tmp_path / "tools"
    bin_dir = tmp_path / "bin"
    env = os.environ.copy()
    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    env["TMPDIR"] = str(tmp_path)
    subprocess.check_call([uv, "tool", "install", "--force", str(ROOT)], env=env)
    for command in ("unpackr", "unpackr-doctor", "vhealth"):
        result = subprocess.run([str(bin_dir / command), "--help"], check=True, capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip()
    pythons = [path for path in tool_dir.rglob("python*") if path.is_file() and os.access(path, os.X_OK)]
    assert pythons, "uv tool install did not create an environment"
    loaded = subprocess.run(
        [str(pythons[0]), "-c", "from unpackr.bundled import config_file; print(config_file().is_file())"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert loaded.stdout.strip() == "True"
