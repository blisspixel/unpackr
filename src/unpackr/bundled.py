"""Locate bundled config shipped inside the unpackr package."""

from importlib import resources
from pathlib import Path


def config_dir() -> Path:
    """Directory of bundled config files, via importlib.resources."""
    packaged = resources.files("unpackr.config_files")
    with resources.as_file(packaged) as path:
        return Path(path)


def config_file(name: str = "config.json") -> Path:
    """Path of one bundled config file."""
    return config_dir() / name
