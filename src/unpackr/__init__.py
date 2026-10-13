"""Turn messy folders of archives into clean, working videos."""

from typing import TYPE_CHECKING, Any

from unpackr.version import __version__

if TYPE_CHECKING:
    from unpackr.cli import UnpackrApp, WorkPlan, main
    from unpackr.utils.cli_prompts import clean_path

__all__ = ["UnpackrApp", "WorkPlan", "clean_path", "main", "__version__"]


def __getattr__(name: str) -> Any:
    """Load CLI exports on demand so version metadata does not import the app."""
    if name in {"UnpackrApp", "WorkPlan", "main"}:
        from unpackr import cli

        return getattr(cli, name)
    if name == "clean_path":
        from unpackr.utils.cli_prompts import clean_path

        return clean_path
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
