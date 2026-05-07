"""CLI prompting and presentation helpers for Unpackr."""

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, cast

from colorama import Fore, Style

from core.config import Config
from utils.cli_render import AnimationMode


def clean_path(path_str: str) -> str:
    """Clean path string by removing quotes and extra whitespace."""
    cleaned = path_str.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def get_user_input(prompt: str) -> Path:
    """Prompt user for directory path with validation."""
    while True:
        user_input = input(prompt).strip()
        cleaned = clean_path(user_input)
        path = Path(cleaned)

        if path.is_dir():
            return path

        print(Fore.RED + "Invalid path. Please enter a valid directory path." + Style.RESET_ALL)
        if user_input != cleaned:
            print(Fore.YELLOW + f"Tip: Path was cleaned to: {cleaned}" + Style.RESET_ALL)


def quick_preflight(config: object, source_dir: Path, destination_dir: Path) -> bool:
    """
    Quick pre-flight check before processing starts.
    Silent if everything is OK; only shows output if issues are found.
    """
    advisories: list[str] = []
    confirmation_warnings: list[str] = []

    try:
        import shutil

        _total, _used, free = shutil.disk_usage(destination_dir)
        free_gb = free // (2**30)
        if free_gb < 5:
            confirmation_warnings.append(f"Very low disk space: {free_gb}GB available (may run out)")
        elif free_gb < 10:
            advisories.append(f"Low disk space: {free_gb}GB available")
    except OSError:
        pass

    try:
        dir_list = list(source_dir.iterdir())
        if not dir_list:
            confirmation_warnings.append("Source directory is empty - nothing to process")
    except Exception as e:
        confirmation_warnings.append(f"Cannot read source directory: {e}")

    warnings = confirmation_warnings + advisories
    if warnings:
        print(f"\n{Fore.YELLOW}Pre-flight Check:{Style.RESET_ALL}")
        for warning in warnings:
            print(f"  {Fore.YELLOW}⚠{Style.RESET_ALL} {warning}")

    if confirmation_warnings:
        print(f"\n{Fore.YELLOW}Continue anyway?{Style.RESET_ALL} {Style.DIM}[y/N]{Style.RESET_ALL}: ", end="")
        try:
            response = input().strip().lower()
            if response not in ("y", "yes"):
                print(Fore.RED + "Aborted by user." + Style.RESET_ALL)
                return False
        except KeyboardInterrupt:
            print(Fore.RED + "\nAborted by user." + Style.RESET_ALL)
            return False
        except EOFError:
            print(Fore.RED + "\nAborted (no interactive input available)." + Style.RESET_ALL)
            return False

    return True


def countdown_prompt(seconds: int = 10, operation_label: str = "processing") -> bool:
    """Display a short countdown before starting work."""
    try:
        inline_output = sys.stdout.isatty()
        for i in range(seconds, 0, -1):
            message = f"{Fore.GREEN}Starting {operation_label} in {i} seconds... (Press Ctrl+C to cancel) {Style.RESET_ALL}"
            if inline_output:
                sys.stdout.write(f"\r{message}")
            else:
                sys.stdout.write(f"{message}\n")
            sys.stdout.flush()
            time.sleep(1)
        if inline_output:
            sys.stdout.write("\r" + " " * 60 + "\r")
        return True
    except KeyboardInterrupt:
        print(Fore.RED + "\n\nOperation cancelled by user." + Style.RESET_ALL)
        return False


def resolve_cli_presentation(args: Any, config: Config) -> tuple[AnimationMode, bool]:
    """
    Resolve CLI presentation settings with precedence:
    CLI args > environment variables > config > defaults.
    """

    def _normalize_mode(value: Any) -> Optional[AnimationMode]:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"auto", "off", "light", "full"}:
                return cast(AnimationMode, normalized)
        return None

    def _is_truthy_env(value: Optional[str]) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "on"}

    cfg_get = getattr(config, "get", None)
    config_mode = _normalize_mode(cfg_get("animations", "auto")) or "auto" if callable(cfg_get) else "auto"
    env_mode = _normalize_mode(os.getenv("UNPACKR_ANIMATIONS"))
    arg_mode = _normalize_mode(getattr(args, "animations", None))
    mode = arg_mode or env_mode or config_mode

    env_no_color = _is_truthy_env(os.getenv("UNPACKR_NO_COLOR")) or os.getenv("NO_COLOR") is not None
    config_no_color = bool(cfg_get("no_color", False)) if callable(cfg_get) else False
    no_color = bool(getattr(args, "no_color", False) or env_no_color or config_no_color)
    return mode, no_color
