"""
Output naming for Unpackr: release-name parsing, deobfuscation and layout templates.

Release folders usually carry the real title ("Some.Show.S01E02.1080p.WEB-DL-GRP")
while the video inside may be generic or obfuscated ("a1b2c3d4.mkv"). This module
picks a good name and an optional folder layout for the destination, without any
network lookups. When a template needs fields the name does not provide, the
caller falls back to the flat layout instead of guessing.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LAYOUT_PRESETS = {
    "flat": "{name}{ext}",
    "release": "{release}{ext}",
    "movies": "Movies/{title} ({year})/{title} ({year}){ext}",
    "tv": "TV/{show}/Season {season:02}/{show} - S{season:02}E{episode:02}{episode_suffix}{ext}",
    "auto": "{kind_folder}",
}
DEFAULT_LAYOUT = "{name}{ext}"

_EPISODE = re.compile(
    r"^(?P<show>.+?)[\s._-]+[Ss](?P<season>\d{1,2})[\s._-]?[Ee](?P<episode>\d{1,3})"
    r"(?:(?:[\s._-]?[Ee]|-[Ee]?)(?P<episode_end>\d{1,3}))?(?!\d)",
)
_EPISODE_X = re.compile(r"^(?P<show>.+?)[\s._-]+(?P<season>\d{1,2})x(?P<episode>\d{2,3})(?!\d)")
_YEAR = re.compile(r"[\s._(\[-]+(?P<year>(?:19|20)\d{2})(?![\dp])")
_SEPARATORS = re.compile(r"[._]+")

# SABnzbd's obfuscation heuristics (sabnzbd/deobfuscate_filenames.py)
_HEX32 = re.compile(r"^[a-f0-9]{32}$")
_HEX_DOTS = re.compile(r"^[a-f0-9.]{40,}$")
_HEX_TAGS = re.compile(r"[a-f0-9]{30}.*(\[\w+\]){2,}")
_ABC_XYZ = re.compile(r"^abc\.xyz", re.IGNORECASE)
GENERIC_STEMS = {"movie", "video", "file", "output", "unnamed", "untitled", "main", "feature", "film"}


@dataclass(frozen=True)
class ReleaseInfo:
    kind: str  # "episode", "movie" or "unknown"
    title: str = ""
    year: int | None = None
    show: str = ""
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None


def _clean(text: str) -> str:
    text = _SEPARATORS.sub(" ", text).strip(" -_")
    return re.sub(r"\s+", " ", text)


def parse_release_name(name: str) -> ReleaseInfo:
    """Parse "Show.S01E02", "Show 1x02", "Title.2026" style names; unknown otherwise."""
    stem = name
    for pattern in (_EPISODE, _EPISODE_X):
        m = pattern.search(stem)
        if m:
            episode_end = m.groupdict().get("episode_end")
            return ReleaseInfo(
                kind="episode",
                show=_clean(m.group("show")),
                season=int(m.group("season")),
                episode=int(m.group("episode")),
                episode_end=int(episode_end) if episode_end else None,
            )
    # The last year wins, so a year inside the title ("Blade.Runner.2049.2017") stays in the title.
    years = list(_YEAR.finditer(stem))
    if years:
        last = years[-1]
        title = _clean(stem[: last.start()])
        if title:
            return ReleaseInfo(kind="movie", title=title, year=int(last.group("year")))
    return ReleaseInfo(kind="unknown")


def is_obfuscated(stem: str) -> bool:
    """True for hash-like or meaningless names (SABnzbd rules plus generic names)."""
    lower = stem.lower()
    if lower in GENERIC_STEMS:
        return True
    if _HEX32.match(lower) or _HEX_DOTS.match(lower) or _HEX_TAGS.search(lower) or _ABC_XYZ.match(stem):
        return True
    # Clear-name signals: separators between words, or mixed case with letters.
    separators = sum(stem.count(c) for c in " ._-")
    has_upper = any(c.isupper() for c in stem)
    has_lower = any(c.islower() for c in stem)
    if separators >= 2 or (has_upper and has_lower and separators >= 1):
        return False
    # Long run of letters and digits with no structure at all.
    alnum = sum(c in string.ascii_letters + string.digits for c in stem)
    digits = sum(c.isdigit() for c in stem)
    return len(stem) >= 16 and alnum == len(stem) and digits >= 4


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[\W_]+", text.lower()) if len(w) >= 3}


def pick_base_name(video: Path, release_name: str | None, deobfuscate: bool = True) -> tuple[str, bool]:
    """(stem to use, whether it came from the release name).

    The release folder name replaces the video name when the video name is obfuscated,
    or when the folder has a recognizable title and the video name shares no word with it.
    """
    stem = video.stem
    if not (deobfuscate and release_name) or is_obfuscated(release_name):
        return stem, False
    if is_obfuscated(stem):
        return release_name, True
    unrelated = not (_words(stem) & _words(release_name))
    if unrelated and parse_release_name(release_name).kind != "unknown" and parse_release_name(stem).kind == "unknown":
        return release_name, True
    return stem, False


class _Fields(dict[str, Any]):
    """format_map dict that raises KeyError for missing fields instead of inventing them."""

    def __missing__(self, key: str) -> Any:
        raise KeyError(key)


_UNSAFE_COMPONENT = re.compile(r'[<>:"|?*\x00-\x1f]')


def _safe_component(text: str) -> str:
    text = _UNSAFE_COMPONENT.sub("", text).strip().strip(".")
    return text or "_"


def render_layout(template: str, video: Path, release_name: str | None, deobfuscate: bool = True) -> Path | None:
    """Relative destination path for a video, or None when the template cannot be filled.

    Fields: name, ext, release, title, year, show, season, episode, episode_suffix, kind_folder.
    Every rendered path component is sanitized; ".." and absolute paths are never produced.
    """
    template = LAYOUT_PRESETS.get(template, template)
    base, _ = pick_base_name(video, release_name, deobfuscate)
    source_for_parse = release_name or video.stem
    info = parse_release_name(source_for_parse)
    if info.kind == "unknown" and release_name:
        info = parse_release_name(video.stem)

    fields: dict[str, Any] = _Fields(name=base, ext=video.suffix.lower(), release=release_name or base)
    if info.kind == "movie":
        fields.update(title=info.title, year=info.year)
    if info.kind == "episode":
        suffix = f"-E{info.episode_end:02}" if info.episode_end and info.episode_end != info.episode else ""
        fields.update(show=info.show, season=info.season, episode=info.episode, episode_suffix=suffix)
    if template == "{kind_folder}":
        if info.kind == "episode":
            template = LAYOUT_PRESETS["tv"]
        elif info.kind == "movie":
            template = LAYOUT_PRESETS["movies"]
        else:
            template = DEFAULT_LAYOUT
    try:
        rendered = template.format_map(fields)
    except (KeyError, ValueError, IndexError):
        return None
    parts = [p for p in re.split(r"[\\/]+", rendered) if p not in ("", ".", "..")]
    if not parts:
        return None
    return Path(*[_safe_component(p) for p in parts])


SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx", ".sup", ".smi")


def subtitle_suffix(subtitle: Path, video: Path) -> str | None:
    """Part of a subtitle's name to keep after the video's new name (language tag), or None if unrelated.

    Matches "<video stem>.en.srt" next to the video, and RARBG-style
    "Subs/<video stem>/2_English.srt" or "Subs/2_English.srt" for a single-video release.
    """
    vstem = video.stem.lower()
    sstem = subtitle.stem
    if sstem.lower().startswith(vstem):
        return sstem[len(video.stem) :]
    parent = subtitle.parent.name.lower()
    if parent == vstem or parent in ("subs", "subtitles", "sub"):
        tag = re.sub(r"^\d+[_\s.-]*", "", sstem)
        return f".{tag}" if tag else ""
    return None
