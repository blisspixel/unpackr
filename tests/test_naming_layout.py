"""Output naming: release parsing, deobfuscation, layouts and subtitles (issue #8)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from unpackr.core.naming import is_obfuscated, parse_release_name, pick_base_name, render_layout, subtitle_suffix

REPO = Path(__file__).resolve().parent.parent

# (release name, kind, show/title, season, episode, episode_end, year)
RELEASE_NAMES = [
    ("Some.Show.S01E02.1080p.WEB-DL.DDP5.1.H.264-GRP", "episode", "Some Show", 1, 2, None, None),
    ("The.Office.US.S05E14.720p.HDTV.x264-CTU", "episode", "The Office US", 5, 14, None, None),
    ("Breaking.Bad.S02E01E02.1080p.BluRay.x265-RARBG", "episode", "Breaking Bad", 2, 1, 2, None),
    ("Show.Name.S03E07-E09.WEBRip.x264-ION10", "episode", "Show Name", 3, 7, 9, None),
    ("Doctor.Who.2005.S13E01.1080p.iP.WEB-DL.AAC2.0.H.264-NTb", "episode", "Doctor Who 2005", 13, 1, None, None),
    ("Star Trek Discovery - s04e10 - Rubicon", "episode", "Star Trek Discovery", 4, 10, None, None),
    ("the_expanse_s06e06_1080p", "episode", "the expanse", 6, 6, None, None),
    ("Archer.2009.4x05.HDTV", "episode", "Archer 2009", 4, 5, None, None),
    ("Severance.S02E10.2160p.ATVP.WEB-DL.DDP5.1.Atmos.DV.HDR.H.265-FLUX", "episode", "Severance", 2, 10, None, None),
    ("The.Last.of.Us.S01E09.Look.for.the.Light.1080p", "episode", "The Last of Us", 1, 9, None, None),
    ("Shogun.2024.S01E01.Anjin.1080p.DSNP.WEB-DL", "episode", "Shogun 2024", 1, 1, None, None),
    ("Movie.Title.2026.1080p.WEB-DL.x264-GRP", "movie", "Movie Title", None, None, None, 2026),
    ("Blade.Runner.2049.2017.2160p.UHD.BluRay.x265-TERMiNAL", "movie", "Blade Runner 2049", None, None, None, 2017),
    ("2001.A.Space.Odyssey.1968.1080p.BluRay", "movie", "2001 A Space Odyssey", None, None, None, 1968),
    ("1917.2019.1080p.BluRay.x264-SPARKS", "movie", "1917", None, None, None, 2019),
    ("Dune Part Two (2024) 2160p", "movie", "Dune Part Two", None, None, None, 2024),
    ("The.Matrix.1999.REMASTERED.1080p.BluRay.x264", "movie", "The Matrix", None, None, None, 1999),
    ("Oppenheimer_2023_1080p_WEB", "movie", "Oppenheimer", None, None, None, 2023),
    ("Spider-Man.Across.the.Spider-Verse.2023.1080p", "movie", "Spider-Man Across the Spider-Verse", None, None, None, 2023),
    ("Alien.Romulus.2024.720p.WEBRip", "movie", "Alien Romulus", None, None, None, 2024),
    ("random-home-video", "unknown", "", None, None, None, None),
    ("Concert.Live.at.Wembley.1080p", "unknown", "", None, None, None, None),
]


@pytest.mark.parametrize("name,kind,title,season,episode,episode_end,year", RELEASE_NAMES)
def test_release_name_parsing(name, kind, title, season, episode, episode_end, year):
    info = parse_release_name(name)
    assert info.kind == kind
    if kind == "episode":
        assert (info.show, info.season, info.episode, info.episode_end) == (title, season, episode, episode_end)
    if kind == "movie":
        assert (info.title, info.year) == (title, year)


class TestObfuscation:
    @pytest.mark.parametrize(
        "stem",
        ["0123456789abcdef0123456789abcdef", "abc.xyz.12345.part", "a1b2c3d4e5f6a7b8c9d0", "movie", "video"],
    )
    def test_obfuscated(self, stem):
        assert is_obfuscated(stem)

    @pytest.mark.parametrize("stem", ["Some.Show.S01E02", "The Matrix (1999)", "concert_live_2019", "Interview"])
    def test_clear_names(self, stem):
        assert not is_obfuscated(stem)

    def test_unrelated_short_name_takes_titled_release(self):
        base, renamed = pick_base_name(Path("a1b2c3d4.mkv"), "Some.Show.S01E02.1080p")
        assert (base, renamed) == ("Some.Show.S01E02.1080p", True)

    def test_related_name_is_kept(self):
        assert pick_base_name(Path("Movie.Title.mkv"), "Movie.Title.2026.1080p")[1] is False
        assert pick_base_name(Path("Movie.mkv"), "Movie.Title.2026.1080p")[1] is True  # generic name
        assert pick_base_name(Path("x9f3.mkv"), "Random.Folder")[1] is False  # folder has no title
        assert pick_base_name(Path("0123456789abcdef0123456789abcdef.mkv"), "Movie.2026", deobfuscate=False)[1] is False


class TestLayouts:
    def test_issue_acceptance_examples(self):
        video = Path("Some.Show.S01E02.1080p/a1b2c3d4.mkv")
        assert render_layout("{release}{ext}", video, "Some.Show.S01E02.1080p") == Path("Some.Show.S01E02.1080p.mkv")
        assert render_layout("tv", video, "Some.Show.S01E02.1080p") == Path(
            "TV/Some Show/Season 01/Some Show - S01E02.mkv"
        )

    def test_movies_and_auto(self):
        video = Path("x/0123456789abcdef0123456789abcdef.mkv")
        assert render_layout("movies", video, "Movie.Title.2026.1080p") == Path(
            "Movies/Movie Title (2026)/Movie Title (2026).mkv"
        )
        assert render_layout("auto", video, "Movie.Title.2026.1080p").parts[0] == "Movies"
        assert render_layout("auto", video, "Show.S02E03").parts[0] == "TV"
        assert render_layout("auto", Path("x/Home Video.mkv"), "Holiday") == Path("Home Video.mkv")

    def test_multi_episode_suffix(self):
        out = render_layout("tv", Path("x/e.mkv"), "Breaking.Bad.S02E01E02.1080p")
        assert out.name == "Breaking Bad - S02E01-E02.mkv"

    def test_unparseable_returns_none_instead_of_guessing(self):
        assert render_layout("tv", Path("x/v.mkv"), "Concert.Live.at.Wembley") is None
        assert render_layout("movies", Path("x/v.mkv"), "Show.S01E01") is None

    def test_rendered_paths_stay_inside(self):
        out = render_layout("../{release}/../../etc{ext}", Path("x/v.mkv"), "Rel")
        assert ".." not in out.parts and not out.is_absolute()
        assert render_layout('{release}<>:"|?*{ext}', Path("x/v.mkv"), "Rel") == Path("Rel.mkv")


class TestSubtitles:
    def test_suffixes(self):
        video = Path("Rel/Movie.2026.1080p.mkv")
        assert subtitle_suffix(Path("Rel/Movie.2026.1080p.en.srt"), video) == ".en"
        assert subtitle_suffix(Path("Rel/Movie.2026.1080p.srt"), video) == ""
        assert subtitle_suffix(Path("Rel/Subs/2_English.srt"), video) == ".English"
        assert subtitle_suffix(Path("Rel/Subs/Movie.2026.1080p/3_Spanish.srt"), video) == ".Spanish"
        assert subtitle_suffix(Path("Rel/Other.Thing.srt"), video) is None


FFMPEG = shutil.which("ffmpeg")
SEVENZ = shutil.which("7zz") or shutil.which("7z")


@pytest.mark.skipif(not (FFMPEG and SEVENZ), reason="needs ffmpeg and 7-Zip")
@pytest.mark.parametrize(
    "layout,expected_video,expected_sub",
    [
        ("{name}{ext}", "Some.Show.S01E02.1080p.mkv", "Some.Show.S01E02.1080p.English.srt"),
        ("tv", "TV/Some Show/Season 01/Some Show - S01E02.mkv", "TV/Some Show/Season 01/Some Show - S01E02.English.srt"),
    ],
)
def test_end_to_end_deobfuscation_layout_and_subtitles(tmp_path, layout, expected_video, expected_sub):
    src, dst = tmp_path / "src", tmp_path / "dst"
    release = src / "Some.Show.S01E02.1080p"
    (release / "Subs").mkdir(parents=True)
    dst.mkdir()
    subprocess.run(
        [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=duration=14:size=320x240:rate=25",
         "-c:v", "libx264", "-b:v", "3M", "-y", str(release / "0123456789abcdef0123456789abcdef.mkv")],
        check=True,
    )  # fmt: skip
    (release / "Subs" / "2_English.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"min_sample_size_mb": 1, "log_folder": str(tmp_path / "logs"), "output_layout": layout}))

    dry = subprocess.run(
        [sys.executable, "-m", "unpackr", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--dry-run", "--no-color"],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    assert expected_video.split("/")[-1] in dry.stdout  # the dry run shows the final destination

    result = subprocess.run(
        [sys.executable, "-m", "unpackr", "--source", str(src), "--destination", str(dst), "--config", str(config),
         "--json", "--no-color"],
        capture_output=True, text=True, timeout=300, cwd=REPO, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout[-2000:]
    summary = json.loads(result.stdout[result.stdout.index("{") :])
    codes = {i["path"]: i["reason_code"] for i in summary["items"]}
    assert codes["Some.Show.S01E02.1080p/0123456789abcdef0123456789abcdef.mkv"] == "renamed_deobfuscated"
    assert codes["Some.Show.S01E02.1080p/Subs/2_English.srt"] == "subtitle_moved"
    assert (dst / expected_video).is_file()
    assert (dst / expected_sub).read_text().startswith("1\n")
