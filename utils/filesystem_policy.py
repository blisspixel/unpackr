"""
Filesystem quirk policy for cross-platform safety.

Encodes the operator-facing rules for case sensitivity, symlink farms,
non-ASCII paths, and containment checks so destructive paths stay boring
and portable across local disks and NAS mounts.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional

NormalizationForm = Literal["NFC", "NFD", "NFKC", "NFKD"]

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:(/|\\)")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class FilesystemProbe:
    """Measured characteristics of a working directory."""

    path: str
    case_sensitive: bool
    supports_symlinks: bool
    supports_non_ascii_names: bool
    platform: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_member_path(member: str) -> str:
    """
    Normalize an archive or relative member path for safety checks.

    Converts Windows separators to POSIX, strips redundant dots, and keeps
    the original intent for absolute/drive detection.
    """
    value = (member or "").replace("\\", "/").strip()
    while "//" in value:
        value = value.replace("//", "/")
    return value


def is_absolute_member_path(member: str) -> bool:
    """Return True for POSIX absolute, Windows drive, or UNC-style members."""
    normalized = normalize_member_path(member)
    if not normalized:
        return False
    if normalized.startswith("/") or normalized.startswith("//"):
        return True
    if _WINDOWS_DRIVE_RE.match(normalized):
        return True
    try:
        return Path(normalized).is_absolute() or Path(member).is_absolute()
    except (OSError, ValueError):
        return True


def has_parent_traversal(member: str) -> bool:
    """Return True when a member path contains parent-directory references."""
    normalized = normalize_member_path(member)
    if not normalized:
        return False
    return ".." in Path(normalized).parts


def contains_control_characters(value: str) -> bool:
    """Return True when a path/name contains ASCII control characters."""
    return bool(_CONTROL_CHARS_RE.search(value or ""))


def normalize_unicode_name(name: str, *, form: NormalizationForm = "NFC") -> str:
    """
    Normalize Unicode filenames to a stable form.

    NFC is preferred for cross-platform interchange (especially macOS NFD vs
    Linux NFC). Callers that rewrite files should still run Windows-hostile
    character sanitization separately.
    """
    if not name:
        return name
    return unicodedata.normalize(form, name)


def looks_like_case_collision(left: str, right: str) -> bool:
    """
    Return True when two names collide under case-insensitive comparison
    but are not identical on a case-sensitive volume.
    """
    if left == right:
        return False
    return left.casefold() == right.casefold()


def find_case_collisions(names: list[str]) -> list[tuple[str, str]]:
    """Return pairs of names that would collide on case-insensitive volumes."""
    collisions: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for name in names:
        key = name.casefold()
        prior = seen.get(key)
        if prior is not None and prior != name:
            collisions.append((prior, name))
        else:
            seen[key] = name
    return collisions


def is_linklike(path: Path) -> bool:
    """Return True for symlinks and other reparse-point-like entries."""
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True

    try:
        import stat as stat_mod

        st = path.lstat()
        file_attributes = getattr(st, "st_file_attributes", 0)
        reparse_flag = getattr(stat_mod, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if reparse_flag and file_attributes & reparse_flag:
            return True
    except OSError:
        return True
    return False


def tree_contains_linklike(root: Path, *, max_entries: int = 10_000) -> bool:
    """
    Walk a tree without following links and report whether any linklike entry exists.

    Bounded by max_entries to keep preflight cheap on huge folders.
    """
    root = Path(root)
    if is_linklike(root):
        return True

    seen = 0
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            # Prune linklike directories so we never descend into foreign trees.
            keep: list[str] = []
            for name in dirnames:
                seen += 1
                if seen > max_entries:
                    return True
                child = current / name
                if is_linklike(child):
                    return True
                keep.append(name)
            dirnames[:] = keep
            for name in filenames:
                seen += 1
                if seen > max_entries:
                    return True
                if is_linklike(current / name):
                    return True
    except OSError as exc:
        logging.warning(f"Could not fully inspect tree for linklike entries at {root}: {exc}")
        return True
    return False


def probe_filesystem(path: Path | None = None) -> FilesystemProbe:
    """
    Probe case sensitivity, symlink support, and non-ASCII filename support.

    Uses a temporary subdirectory under ``path`` (or the process temp dir).
    """
    import sys

    base = Path(path) if path is not None else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)

    case_sensitive = True
    supports_symlinks = False
    supports_non_ascii = False

    with tempfile.TemporaryDirectory(prefix=".unpackr-fsprobe-", dir=str(base)) as tmp:
        root = Path(tmp)
        lower = root / "caseprobe.txt"
        lower.write_text("probe", encoding="utf-8")
        upper = root / "CASEPROBE.TXT"
        try:
            upper.write_text("other", encoding="utf-8")
            # Case-sensitive volumes keep both values; case-insensitive volumes overwrite.
            case_sensitive = (
                lower.read_text(encoding="utf-8") == "probe" and upper.read_text(encoding="utf-8") == "other"
            )
        except OSError:
            case_sensitive = False

        link = root / "link-probe"
        target = root / "link-target"
        target.write_text("t", encoding="utf-8")
        try:
            link.symlink_to(target)
            supports_symlinks = link.is_symlink()
        except OSError:
            supports_symlinks = False

        unicode_name = root / "café-тест.txt"
        try:
            unicode_name.write_text("ok", encoding="utf-8")
            supports_non_ascii = unicode_name.is_file() and unicode_name.read_text(encoding="utf-8") == "ok"
        except OSError:
            supports_non_ascii = False

    return FilesystemProbe(
        path=str(base.resolve()),
        case_sensitive=case_sensitive,
        supports_symlinks=supports_symlinks,
        supports_non_ascii_names=supports_non_ascii,
        platform=sys.platform,
    )


def containment_violation(member: str, target_folder: Path) -> Optional[str]:
    """
    Return a reason string when extracting ``member`` would escape ``target_folder``.

    Returns None when the member is safe.
    """
    if contains_control_characters(member):
        return f"control characters in path: {member!r}"
    if is_absolute_member_path(member):
        return f"absolute path: {member}"
    if has_parent_traversal(member):
        return f"parent directory reference: {member}"

    normalized = normalize_member_path(member)
    if not normalized:
        return None

    try:
        target_resolved = target_folder.resolve()
        would_extract_to = (target_folder / Path(normalized)).resolve()
        would_extract_to.relative_to(target_resolved)
    except ValueError:
        return f"would extract outside target: {member}"
    except OSError as exc:
        return f"path validation error for {member}: {exc}"
    return None
