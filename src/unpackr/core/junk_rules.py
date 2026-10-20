"""
Rules for what is junk, what is bait, and what is still downloading.

Usenet and torrent releases are mostly not the video you wanted: verification
files, tracker spam, OS cruft, padding, samples, and sometimes malware dressed
up as a movie. These rules classify paths so the pipeline can remove the junk,
quarantine the bait and leave unfinished downloads alone.

Sources for the defaults: Sonarr/Radarr dangerous and executable extensions,
the TRaSH Guides unwanted-extension list for SABnzbd, NZBGet FakeDetector,
SABnzbd sample rules, BEP 47 padding files.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias, cast

# Executables, scripts, shortcuts and installers that a video release never needs.
DEFAULT_DANGEROUS_EXTENSIONS = (
    ".exe", ".com", ".scr", ".pif", ".bat", ".cmd", ".lnk", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".ws", ".wsc", ".hta", ".msi", ".msp", ".mst", ".msc", ".ps1", ".psm1", ".psd1", ".ps1xml", ".jar", ".reg",
    ".cpl", ".inf", ".scf", ".sct", ".shb", ".shs", ".chm", ".hlp", ".gadget", ".application", ".appref-ms",
    ".xbap", ".xll", ".dll", ".sys", ".apk", ".app", ".dmg", ".pkg", ".deb", ".rpm", ".sh", ".py", ".pyw",
    ".zipx", ".arj", ".lzh", ".iqy", ".slk", ".website",
)  # fmt: skip

# Scripts that legitimate "reverse/spiegelen" posts ship to restore names (NZBGet FakeDetector allows these).
RENAME_SCRIPTS = ("rename.bat", "rename.sh", "rename.cmd")
# Harmless anti-mirroring placeholder in genuine RARBG releases; quarantined, but it does not fail the release.
KNOWN_MARKER_EXECUTABLES = ("rarbg_do_not_mirror.exe",)

# A stray .tmp is common in finished downloads too, so it is not treated as "still downloading".
DEFAULT_INCOMPLETE_MARKERS = (".!qb", ".!ut", ".part", ".crdownload", ".partial", ".download", ".aria2")

DEFAULT_SAMPLE_FOLDER_NAMES = ("sample", "samples", "proof", "proofs", "screens", "screenshots")
SAMPLE_NAME_PATTERN = re.compile(r"(^|[\W_])(sample|proof|trailer|preview|promo)([\W_]|$)", re.IGNORECASE)

DEFAULT_JUNK_NAME_PATTERNS = (
    "rarbg*.txt", "www.*.com*", "www.*.org*", "downloaded from*", "torrent downloaded from*",
    "thumbs.db", ".ds_store", "desktop.ini", "._*", "*.url",
)  # fmt: skip
OS_CRUFT_DIRS = ("@eadir", ".appledouble", "__macosx")
PADDING_NAME = re.compile(r"^_+padding_file_\d+", re.IGNORECASE)
DISC_STRUCTURE_DIRS = ("video_ts", "bdmv")

SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".sup", ".smi")
SUBTITLE_SUSPICIOUS_BYTES = 1024 * 1024  # real text subtitles for a feature are far smaller

# Bidirectional control characters used to disguise "exe.mkv" names (U+202E right-to-left override and friends).
BIDI_CONTROLS = re.compile(r"[\u202a-\u202e\u2066-\u2069\u200e\u200f]")
MEDIA_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts", ".webm", ".flv")


# (reason_code, human-readable detail) for a video picked for removal.
SampleDecision: TypeAlias = tuple[str, str]


@dataclass(frozen=True)
class Finding:
    """A classified path. ``fails_release`` means no video from that release may be kept."""

    path: Path
    reason_code: str
    detail: str
    fails_release: bool = False


def _get(config: Any, key: str, default: Any) -> Any:
    getter = getattr(config, "get", None)
    if callable(getter):
        value = getter(key, default)
        return default if value is None else value
    return getattr(config, key, default)


def _lower_str_list(value: object, default: Iterable[str]) -> list[str]:
    """Lower-cased string entries of a config list, or the default when it is not a list."""
    if not isinstance(value, list):
        return list(default)
    items = cast(list[object], value)  # JSON list; entries are validated below
    return [item.lower() for item in items if isinstance(item, str)]


def dangerous_extensions(config: Any) -> list[str]:
    return _lower_str_list(_get(config, "dangerous_extensions", None), DEFAULT_DANGEROUS_EXTENSIONS)


def _is_binary(path: Path, probe_bytes: int = 4096) -> bool:
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(probe_bytes)
    except OSError:
        return False
    return b"\x00" in chunk


def classify_security(path: Path, config: Any, release_has_video: bool) -> Finding | None:
    """Return a security finding for bait or payload files, else None."""
    name = path.name
    lower = name.lower()
    if BIDI_CONTROLS.search(name):
        return Finding(path, "security_bidi_name", "name hides its real extension with direction controls", True)
    suffixes = [s.lower() for s in path.suffixes]
    dangerous = dangerous_extensions(config)
    if len(suffixes) >= 2 and suffixes[-1] in dangerous and suffixes[-2] in MEDIA_EXTENSIONS:
        return Finding(path, "security_double_extension", f"looks like a video but is {suffixes[-1]}", True)
    if path.suffix.lower() in dangerous:
        if lower in RENAME_SCRIPTS and release_has_video:
            return Finding(path, "security_rename_script", "rename script from a reversed-name post", False)
        if lower in KNOWN_MARKER_EXECUTABLES:
            return Finding(path, "security_known_marker", "tracker placeholder executable, quarantined", False)
        code = (
            "security_executable"
            if path.suffix.lower() in (".exe", ".com", ".bat", ".cmd", ".sh")
            else ("security_dangerous_ext")
        )
        return Finding(path, code, f"{path.suffix.lower()} has no place in a video release", True)
    if path.suffix.lower() in SUBTITLE_EXTENSIONS and path.suffix.lower() not in (".sub", ".idx", ".sup"):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > SUBTITLE_SUSPICIOUS_BYTES or _is_binary(path):
            return Finding(path, "security_suspicious_subtitle", "subtitle is oversized or contains binary data", True)
    return None


def is_incomplete_marker(path: Path, config: Any = None) -> bool:
    raw = _get(config, "incomplete_download_markers", None) if config else None
    markers = _lower_str_list(raw, DEFAULT_INCOMPLETE_MARKERS)
    lower = path.name.lower()
    return any(lower.endswith(marker) for marker in markers)


def find_incomplete_markers(folder: Path, config: Any = None, limit: int = 3) -> list[Path]:
    """Partial-download files anywhere under folder (a download that is still running)."""
    found: list[Path] = []
    for path in _walk_files(folder):
        if is_incomplete_marker(path, config):
            found.append(path)
            if len(found) >= limit:
                break
    return found


def is_padding_file(path: Path, verify_bytes: int = 1024 * 1024) -> bool:
    """BEP 47 padding: named padding files or files in a .pad folder, whose content is all zeros."""
    in_pad_dir = any(part.lower() == ".pad" for part in path.parts[:-1])
    if not (PADDING_NAME.match(path.name) or in_pad_dir):
        return False
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(verify_bytes)
    except OSError:
        return False
    return chunk.count(0) == len(chunk)


def junk_name_reason(path: Path, config: Any = None) -> str | None:
    """Reason code when the name alone marks a file as junk."""
    lower = path.name.lower()
    raw = _get(config, "junk_name_patterns", None) if config else None
    patterns = _lower_str_list(raw, DEFAULT_JUNK_NAME_PATTERNS)
    if any(part.lower() in OS_CRUFT_DIRS for part in path.parts[:-1]):
        return "junk_os_cruft"
    if any(fnmatch.fnmatch(lower, pattern) for pattern in patterns):
        return "junk_name"
    if is_padding_file(path):
        return "torrent_padding"
    try:
        if path.is_file() and path.stat().st_size == 0:
            return "empty_file"
    except OSError:
        pass
    return None


def has_disc_structure(folder: Path) -> Path | None:
    """Return a VIDEO_TS or BDMV directory under folder; such releases are kept whole."""
    try:
        for current, dirs, _files in _walk(folder):
            for d in dirs:
                if d.lower() in DISC_STRUCTURE_DIRS:
                    return Path(current) / d
    except OSError:
        return None
    return None


def sample_folder_names(config: Any) -> list[str]:
    return _lower_str_list(_get(config, "sample_folder_names", None), DEFAULT_SAMPLE_FOLDER_NAMES)


def looks_like_sample(path: Path, config: Any) -> str | None:
    """Name or folder evidence that a video is a sample/proof/trailer; returns the reason code."""
    folders = set(sample_folder_names(config))
    if any(part.lower() in folders for part in path.parts[:-1]):
        return "sample_folder"
    if SAMPLE_NAME_PATTERN.search(path.stem):
        return "sample_named"
    return None


def decide_release_samples(
    videos: Sequence[Path],
    durations: Mapping[Path, float | None],
    sizes: Mapping[Path, int],
    config: Any,
) -> dict[Path, SampleDecision]:
    """Pick the samples in one release. Returns {path: (reason_code, detail)}.

    - A video named sample/proof/trailer/preview/promo, or inside a Sample/Proof/Screens
      folder, is a sample when its duration is at most ``max_sample_duration_seconds``
      (default 300). With no duration, it must also be under ``min_sample_size_mb``.
    - Relative rule: when the release has a video of 20 minutes or more, another video
      under 10% of that duration and under 5 minutes is a sample.
    - The longest video in a release is never removed as a sample on name alone.
    """
    if not videos:
        return {}
    raw_cap = _get(config, "max_sample_duration_seconds", 300)
    cap: float = raw_cap if isinstance(raw_cap, (int, float)) else 300
    raw_min_size = _get(config, "min_sample_size_mb", 50)
    min_size_mb: float = raw_min_size if isinstance(raw_min_size, (int, float)) else 50

    def key_len(v: Path) -> float:
        return float(durations.get(v) or 0) or sizes.get(v, 0) / 1e9

    main = max(videos, key=key_len)
    main_duration = durations.get(main) or 0
    decided: dict[Path, SampleDecision] = {}
    for video in videos:
        if video == main and len(videos) > 1:
            continue
        duration = durations.get(video)
        size_mb = sizes.get(video, 0) / (1024 * 1024)
        reason = looks_like_sample(video, config)
        if reason and video != main:
            if duration is not None and duration <= cap:
                decided[video] = (reason, f"{duration:.0f}s, at most the {cap:g}s sample limit")
                continue
            if duration is None and size_mb < min_size_mb:
                decided[video] = (reason, f"{size_mb:.1f}MB, under {min_size_mb:g}MB with no readable duration")
                continue
        if main_duration >= 1200 and duration is not None and duration < 300 and duration < 0.1 * main_duration:
            decided[video] = (
                "sample_relative",
                f"{duration:.0f}s next to a {main_duration / 60:.0f} minute main video",
            )
    return decided


_RELEASE_TAGS = re.compile(
    r"\b(2160p|1080p|720p|576p|480p|4k|uhd|hdr10?|dv|x26[45]|h\.?26[45]|hevc|avc|av1|xvid|"
    r"web-?dl|webrip|bluray|blu-ray|bdrip|brrip|remux|hdtv|dvdrip|aac|ac3|dts|ddp?5\.1|atmos|"
    r"10bit|8bit|proper|repack)\b",
    re.IGNORECASE,
)


def normalized_title(path: Path) -> str:
    """Title without quality and codec tags, for spotting two encodes of the same thing."""
    stem = re.sub(r"-[A-Za-z][A-Za-z0-9]*$", "", path.stem)  # trailing release group, "-GRP"
    stem = _RELEASE_TAGS.sub(" ", stem)
    stem = re.sub(r"[\W_]+", " ", stem)
    return " ".join(stem.lower().split())


def decide_duplicate_encodes(videos: Sequence[Path], sizes: Mapping[Path, int]) -> dict[Path, SampleDecision]:
    """{path: (reason_code, detail)} for smaller copies of the same title (keeps the largest)."""
    groups: dict[str, list[Path]] = {}
    for video in videos:
        groups.setdefault(normalized_title(video), []).append(video)
    decided: dict[Path, SampleDecision] = {}
    for title, members in groups.items():
        if not title or len(members) < 2:
            continue
        keep = max(members, key=lambda v: sizes.get(v, 0))
        for video in members:
            if video != keep:
                decided[video] = ("duplicate_encode", f"smaller copy of {keep.name}")
    return decided


def _walk(folder: Path) -> Iterator[tuple[str, list[str], list[str]]]:
    import os

    return os.walk(folder)


def _walk_files(folder: Path) -> Iterable[Path]:
    for current, _dirs, files in _walk(folder):
        for name in files:
            yield Path(current) / name
