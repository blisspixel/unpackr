"""
Unpackr: Your Digital Declutterer
Automate, Organize, and Streamline Your Downloads with Ease

A specialized tool for cleaning up download folders from Usenet/newsgroups.
Extracts archives, repairs files, validates videos, and removes garbage.
"""

import atexit
import json
import logging
import os
import random
import re
import signal
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn, TypedDict, cast

from colorama import Fore, Style, init

from core import Config, setup_logging
from core.archive_processor import (
    BROKEN_SET_REASONS,
    ArchiveOutcome,
    ArchiveProcessor,
    ArchiveSet,
    Par2Outcome,
    find_archive_sets,
    is_archive_related,
)
from core.file_handler import FileHandler
from core.junk_rules import (
    classify_security,
    decide_duplicate_encodes,
    decide_release_samples,
    has_disc_structure,
    is_incomplete_marker,
)
from core.naming import DEFAULT_LAYOUT, SUBTITLE_EXTENSIONS, pick_base_name, render_layout, subtitle_suffix
from core.remover import Remover, is_internal, new_run_id, purge_quarantine
from core.run_lock import RunLock
from core.run_report import ReportItem, RunReport
from core.safety_invariants import InvariantEnforcer
from core.video_processor import VideoProcessor
from utils.cli_prompts import clean_path, countdown_prompt, get_user_input, quick_preflight, resolve_cli_presentation
from utils.cli_render import create_renderer
from utils.cli_runtime import build_unpackr_arg_parser, configure_windows_console_utf8, resolve_unpackr_paths
from utils.cli_subcommands import SUBCOMMANDS, run_subcommand
from utils.defensive import InputValidator, StateValidator, ValidationError
from utils.dry_run_summary import DryRunPlan
from utils.run_state import RunState, default_state_path
from utils.run_summary import build_unpackr_run_summary, dumps_run_summary
from utils.safety import LoopSafety, OperationTimer, RecursionSafety, StuckDetector
from utils.system_check import SystemCheck
from version import __version__

# Set UTF-8 encoding for Windows console to handle special characters in easter eggs
configure_windows_console_utf8()


# Live run finished, but some items need attention (held archive sets, blocked archives).
EXIT_COMPLETED_WITH_ERRORS = 3


class ThreadSafeStats:
    """Thread-safe statistics tracking with atomic operations."""

    def __init__(self) -> None:
        """Initialize statistics with thread safety."""
        self._lock = threading.Lock()
        self._stats: dict[str, int] = {
            "folders_processed": 0,
            "folders_deleted": 0,
            "folders_preserved": 0,
            "empty_folders_deleted": 0,
            "videos_found": 0,  # Total videos discovered (before processing)
            "videos_moved": 0,
            "videos_healthy": 0,
            "videos_corrupt": 0,
            "videos_sample": 0,
            "videos_failed": 0,
            "files_sanitized": 0,
            "rars_extracted": 0,
            "par2s_repaired": 0,
            "junk_files_deleted": 0,
            "safety_stops": 0,
        }

    def increment(self, key: str, value: int = 1) -> None:
        """Atomically increment a statistic."""
        with self._lock:
            if key in self._stats:
                self._stats[key] += value

    def __getitem__(self, key: str) -> int:
        """Thread-safe get operation."""
        with self._lock:
            return self._stats.get(key, 0)

    def __setitem__(self, key: str, value: int) -> None:
        """
        Thread-safe set operation.

        Note: self.stats['key'] += 1 is NOT fully atomic (involves get+set).
        Use increment() method for true atomic increments if needed.
        However, since only the main thread modifies stats and the spinner
        only reads, this is safe for current architecture.
        """
        with self._lock:
            self._stats[key] = value

    def get_snapshot(self) -> dict[str, int]:
        """Get a thread-safe snapshot of all statistics."""
        with self._lock:
            return self._stats.copy()


# ASCII Art
ASCII_ART = r"""
                               _
  _   _ _ __  _ __   __ _  ___| | ___ __
 | | | | '_ \| '_ \ / _` |/ __| |/ / '__|
 | |_| | | | | |_) | (_| | (__|   <| |
  \__,_|_| |_| .__/ \__,_|\___|_|\_\_|
             |_|

"""


# "video.mkv.1", "video.mp4.2": duplicate-download suffixes left by downloaders.
_NUMBERED_VIDEO_SUFFIX = re.compile(
    r"(\.(?:mp4|mkv|avi|mov|wmv|flv|webm|m4v|mpg|mpeg|ts|m2ts))\.\d{1,3}$", re.IGNORECASE
)


class VideoFolderEntry(TypedDict):
    """A folder the run processes: videos, archive files and PAR2 files found in pre-scan."""

    path: Path
    videos: int
    rars: int
    par2s: int


class ContentFolderEntry(TypedDict):
    """A folder kept because it holds music, images or documents."""

    path: Path
    reason: str


# comments.json: either a flat list of comments (old format) or a dict with
# "rarities" and per-rarity "comments" (new format). Values come from JSON.
type CommentsData = list[str] | dict[str, Any]
# A comment ready to show: (text, rarity, colour, effect).
type CommentDisplay = tuple[str, str | None, str, str]
# What the progress display accepts: a CommentDisplay, or a plain string (old flat format).
type ShownComment = CommentDisplay | str


class WorkPlan:
    """Represents the work plan from pre-scan analysis."""

    def __init__(self) -> None:
        self.video_folders: list[VideoFolderEntry] = []
        self.content_folders: list[ContentFolderEntry] = []
        self.junk_folders: list[Path] = []  # Folders with only junk files - to be deleted
        self.junk_kept: set[Path] = set()  # Junk-classified folders the run will keep (non-removable files inside)
        self.loose_videos: list[Path] = []
        self.total_videos = 0
        self.total_rars = 0
        self.total_par2s = 0
        self.estimated_time = 0

    def add_video_folder(self, folder: Path, videos: int, rars: int, par2s: int) -> None:
        """Add a video folder to the plan."""
        self.video_folders.append({"path": folder, "videos": videos, "rars": rars, "par2s": par2s})
        self.total_videos += videos
        self.total_rars += rars
        self.total_par2s += par2s

    def add_content_folder(self, folder: Path, reason: str = "") -> None:
        """Add a content folder to keep."""
        self.content_folders.append({"path": folder, "reason": reason})

    def add_junk_folder(self, folder: Path) -> None:
        """Add a junk folder to delete."""
        self.junk_folders.append(folder)

    def add_loose_video(self, video: Path) -> None:
        """Add a loose video file."""
        self.loose_videos.append(video)
        # Counted already: the source root is a video folder whenever it holds loose videos.

    def as_plan_entries(self, source_dir: Path) -> list[dict[str, Any]]:
        """Folder-level plan for --show-plan --json (per-file items come from --dry-run --json)."""

        def rel(path: Path) -> str:
            try:
                return path.relative_to(source_dir).as_posix()
            except ValueError:
                return str(path)

        entries: list[dict[str, Any]] = []
        for item in self.video_folders:
            entries.append(
                {
                    "path": rel(item["path"]),
                    "role": "process",
                    "videos": item["videos"],
                    "archives": item["rars"],
                    "par2": item["par2s"],
                    "planned": True,
                }
            )
        for content in self.content_folders:
            entries.append({"path": rel(content["path"]), "role": "keep", "reason": content["reason"], "planned": True})
        for folder in self.junk_folders:
            if folder in self.junk_kept:
                entries.append({"path": rel(folder), "role": "keep", "reason": "non_removable_files", "planned": True})
            else:
                entries.append({"path": rel(folder), "role": "delete", "reason": "junk_folder", "planned": True})
        for video in self.loose_videos:
            entries.append({"path": rel(video), "role": "validate_video", "planned": True})
        return sorted(entries, key=lambda e: e["path"])

    def calculate_time_estimate(self) -> int:
        """Calculate estimated processing time."""
        # More realistic estimates:
        # - 10 seconds per video check (FFmpeg can be slow)
        # - 3 seconds per RAR (usually just extracts first .part001)
        # - 5 seconds per PAR2 set (usually just verifies, rarely repairs)
        # - 2 seconds per folder operation

        time_estimate = 0
        time_estimate += self.total_videos * 10  # Video health checks
        time_estimate += self.total_rars * 3  # RAR extractions (only .part001)
        time_estimate += self.total_par2s * 5  # PAR2 verify (not full repair)
        time_estimate += len(self.video_folders) * 2  # Folder operations

        self.estimated_time = time_estimate
        return time_estimate

    def display(self) -> None:
        """Display the work plan."""
        # Compact single-line summary
        eta = timedelta(seconds=self.estimated_time)
        eta_str = str(eta).split(".")[0]

        print(
            f"{Fore.YELLOW}{len(self.video_folders)}{Style.RESET_ALL} folders, "
            f"{Fore.YELLOW}{self.total_videos}{Style.RESET_ALL} videos, "
            f"{Fore.YELLOW}{self.total_rars}{Style.RESET_ALL} RARs, "
            f"{Fore.YELLOW}{self.total_par2s}{Style.RESET_ALL} PAR2s | "
            f"ETA: {Fore.CYAN}{eta_str}{Style.RESET_ALL} | "
            f"{Fore.GREEN}{len(self.content_folders)}{Style.RESET_ALL} folders preserved"
        )

    def display_detailed(self) -> None:
        """Display detailed pre-flight plan showing what will happen to each folder."""
        print(f"\n{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}PRE-FLIGHT CHECK - Detailed Plan{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")

        # Video folders to process
        if self.video_folders:
            print(f"{Fore.YELLOW}FOLDERS TO PROCESS ({len(self.video_folders)} folders):{Style.RESET_ALL}")
            print(
                f"{Fore.WHITE}Each is processed: PAR2 verify/repair (if present) -> extract archive sets -> "
                f"validate videos -> move good videos -> remove what is left{Style.RESET_ALL}\n"
            )
            for item in self.video_folders:
                folder = item["path"]
                videos = item["videos"]
                rars = item["rars"]
                par2s = item["par2s"]

                actions: list[str] = []
                if par2s > 0:
                    actions.append(f"{par2s} PAR2")
                if rars > 0:
                    actions.append(f"{rars} archive file(s)")
                if videos > 0:
                    actions.append(f"{videos} video(s)")

                action_str = " -> ".join(actions) if actions else "scan only"
                print(f"  {Fore.GREEN}+{Style.RESET_ALL} {folder.name[:60]:<60} | {action_str}")
            print()

        # Content folders to preserve
        if self.content_folders:
            print(f"{Fore.GREEN}FOLDERS TO PRESERVE ({len(self.content_folders)} folders):{Style.RESET_ALL}")
            print(f"{Fore.WHITE}These will NOT be deleted (contain music/images/documents){Style.RESET_ALL}\n")
            for content in self.content_folders:
                folder = content["path"]
                reason = content.get("reason", "content detected")
                print(f"  {Fore.BLUE}*{Style.RESET_ALL} {folder.name[:60]:<60} | {reason}")
            print()

        removable_junk = [f for f in self.junk_folders if f not in self.junk_kept]
        kept_junk = [f for f in self.junk_folders if f in self.junk_kept]
        if removable_junk:
            print(f"{Fore.RED}FOLDERS TO REMOVE ({len(removable_junk)} folders):{Style.RESET_ALL}")
            print(f"{Fore.WHITE}Only junk was found (NFO, SFV, URL, small images and similar){Style.RESET_ALL}\n")
            for folder in removable_junk:
                print(f"  {Fore.RED}-{Style.RESET_ALL} {folder.name[:60]}")
            print()
        if kept_junk:
            print(f"{Fore.GREEN}FOLDERS KEPT AS-IS ({len(kept_junk)} folders):{Style.RESET_ALL}")
            print(f"{Fore.WHITE}No videos, but they hold files Unpackr does not remove{Style.RESET_ALL}\n")
            for folder in kept_junk:
                print(f"  {Fore.BLUE}*{Style.RESET_ALL} {folder.name[:60]}")
            print()

        if self.loose_videos:
            print(f"{Fore.YELLOW}LOOSE VIDEOS ({len(self.loose_videos)}):{Style.RESET_ALL}")
            print(f"{Fore.WHITE}Videos directly in the source folder are validated and moved{Style.RESET_ALL}\n")
            for video in self.loose_videos:
                print(f"  {Fore.GREEN}+{Style.RESET_ALL} {video.name[:60]}")
            print()

        # Summary
        eta = timedelta(seconds=self.estimated_time)
        eta_str = str(eta).split(".")[0]
        print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}SUMMARY:{Style.RESET_ALL}")
        print(
            f"  Process: {len(self.video_folders)} folders -> {self.total_videos} videos -> Estimated time: {eta_str}"
        )
        print(f"  Preserve: {len(self.content_folders)} folders (will NOT be deleted)")
        print(
            f"  Remove: {len(self.junk_folders) - len(self.junk_kept)} junk-only folders  |  "
            f"Keep as-is: {len(self.junk_kept)}  |  Loose videos: {len(self.loose_videos)}"
        )
        print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")


def _config_get(config: object, key: str, default: object) -> Any:
    """``config.get(key, default)`` for a Config or a dict; ``default`` when there is no ``get``.

    Tests pass bare stand-ins without ``get``. Config values come from JSON, hence ``Any``.
    """
    getter = getattr(config, "get", None)
    if getter is None:
        return default
    return getter(key, default)


def _comment_text(comment: ShownComment) -> str:
    """The text of a comment: the first field of a rarity tuple, or an old-format plain string."""
    if isinstance(comment, tuple):
        return str(comment[0])
    return str(comment)


def _comment_terminal_line(comment: ShownComment) -> str:
    """The easter-egg comment line for the full-screen progress display (before sanitizing)."""
    # Unpack rarity info
    if isinstance(comment, tuple) and len(comment) >= 3:
        text, color = comment[0], comment[2]
        effect = comment[3] if len(comment) > 3 else ""

        # Apply visual effects based on rarity
        if effect == "legendary":
            # Special legendary effect: markers + gold/yellow + bright (1% drop!)
            return f"  {Style.DIM}│{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}[!] {text[:71]} [!]{Style.RESET_ALL}\033[K\n"
        # Normal rarity effects
        style = ""
        if effect == "dim":
            style = Style.DIM
        elif effect == "bright" or effect == "bright_bold":
            style = Style.BRIGHT
        elif effect == "normal":
            style = Style.NORMAL
        return f"  {Style.DIM}│{Style.RESET_ALL} {color}{style}{text[:75]}{Style.RESET_ALL}\033[K\n"
    # Old format fallback
    return f"  {Style.DIM}│{Style.RESET_ALL} {Fore.YELLOW}{comment[:75]}{Style.RESET_ALL}\033[K\n"


class UnpackrApp:
    """Main application class for Unpackr."""

    def __init__(self, config: Config) -> None:
        """
        Initialize the application.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.stats = ThreadSafeStats()  # Thread-safe statistics tracking
        # Initialize handlers with stats tracking
        self.file_handler = FileHandler(config, self.stats)
        self.archive_processor = ArchiveProcessor(config, process_tracker=self)
        self.video_processor = VideoProcessor(config, process_tracker=self)
        self.dry_run = False  # Set to True for dry-run mode
        self.dry_run_plan: DryRunPlan | None = None  # DryRunPlan for collecting operations in dry-run mode
        self.start_time: float | None = None
        self.work_plan: WorkPlan | None = None
        self.destination_dir: Path | None = None  # Store for display_summary tip
        # MEMORY FIX: Use bounded deque to prevent unbounded memory growth in 24+ hour runs
        # Keeps last 1000 failed deletions (oldest are dropped automatically)
        self.failed_deletions: deque[tuple[Path, bool, bool]] = deque(
            maxlen=1000
        )  # Track folders that couldn't be deleted
        self.run_state: RunState | None = None
        self.resume_enabled: bool = False
        self.recursion_guard = RecursionSafety(config.max_subfolder_depth, "Subfolder processing")
        self.stuck_detector = StuckDetector(timeout=config.stuck_timeout_hours * 3600, check_interval=60)
        self.runtime_limit: OperationTimer | None = None  # Will be initialized when processing starts
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]  # Modern spinner
        self.spinner_index = 0
        self.first_progress_update = True  # Track if this is the first render
        self.current_action = ""  # Current action text
        self.progress_current = 0  # Current progress
        self.progress_total = 0  # Total progress
        self.current_comment_display: CommentDisplay | None = None  # Store current comment to persist across updates
        self.spinner_thread: threading.Thread | None = None  # Background spinner thread
        self.spinner_running = False  # Control flag for spinner thread
        self.spinner_lock = threading.Lock()  # Thread safety for spinner updates
        self.renderer = create_renderer()

        # Cancellation support
        self.cancellation_requested = False
        self.active_process = None  # Track current subprocess for termination
        # Problems a person should look at; errors make a live run exit non-zero.
        self.run_errors: list[str] = []
        self.run_warnings: list[str] = []
        # Damaged downloads removed or left as junk this run: worth re-downloading.
        self.damaged: list[str] = []
        self.last_renamed_from: str | None = None
        self.plain_progress = False  # one plain line per folder instead of redrawing (no terminal)
        self._last_plain_progress = 0
        # Per-file decisions for --json items and --report.
        self.report = RunReport()
        self.file_handler.report = self.report

        # Load snarky comments for easter eggs
        self.comments = self._load_comments()
        self.last_comment_folder = -10  # Track when we last showed a comment (start at -10 so first folder shows)

        # Debug: Log if comments loaded successfully
        if self.comments:
            if isinstance(self.comments, dict):
                num_categories = len(self.comments.get("comments", {}))
                logging.debug(f"Loaded rarity-based comments with {num_categories} categories")
            else:
                logging.debug(f"Loaded {len(self.comments)} flat comments")
        else:
            logging.warning("No comments loaded - easter eggs disabled")

    def scan_and_plan(self, source_dir: Path) -> WorkPlan:
        """
        Scan source directory and create a work plan.

        Args:
            source_dir: Source directory to scan

        Returns:
            WorkPlan instance
        """
        plan = WorkPlan()
        # Process root folder FIRST (if it has videos), then subdirectories (oldest first)
        # This ensures videos in the source root are handled before diving into subfolders
        folders: list[Path] = []

        # Enumerate root entries once; unreadable paths should not crash planning.
        try:
            # Unpackr's own state (.unpackr-quarantine, .unpackr-runs, resume state) is never content.
            root_entries = [entry for entry in source_dir.iterdir() if not is_internal(Path(entry.name))]
        except (PermissionError, OSError) as e:
            logging.warning(f"Cannot read source directory during pre-scan: {source_dir} ({e})")
            root_entries = []

        # Add source directory itself as first item if it has any files
        has_files_in_root = False
        for entry in root_entries:
            try:
                if entry.is_file():
                    has_files_in_root = True
                    break
            except (PermissionError, OSError):
                continue
        if has_files_in_root:
            folders.append(source_dir)

        # Then add subdirectories, sorted by modification time (oldest first)
        # Oldest first = completed downloads processed before ongoing ones
        subfolders: list[Path] = []
        for entry in root_entries:
            try:
                if entry.is_dir():
                    subfolders.append(entry)
            except (PermissionError, OSError):
                continue

        def _safe_mtime(path_obj: Path) -> float:
            try:
                return path_obj.stat().st_mtime
            except (PermissionError, OSError):
                # Push unreadable folders to the end without failing pre-scan.
                return float("inf")

        subfolders.sort(key=_safe_mtime)
        folders.extend(subfolders)

        # Show progress during scan
        for i, folder in enumerate(folders, 1):
            # Emit progress at stable checkpoints to avoid log spam in captured output.
            if (i == 1 or i == len(folders) or i % 50 == 0) and not getattr(self, "plain_progress", False):
                sys.stdout.write(f"\r[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
                sys.stdout.flush()

            # First pass: Fix misnamed video files (.mp4.1, .wmv.1, etc.)
            # This must happen BEFORE counting, so renamed files are detected as videos
            try:
                folder_entries = list(folder.iterdir())
            except (PermissionError, OSError) as e:
                logging.warning(f"Skipping unreadable folder during pre-scan: {folder} ({e})")
                continue

            for file in folder_entries:
                try:
                    is_regular_file = file.is_file()
                except (PermissionError, OSError):
                    continue

                # Only duplicate-download suffixes such as "video.mp4.1" are renamed. Anything else
                # after a video extension ("x.mkv.part" still downloading, "x.mkv.exe" bait) is left
                # as is, and a dry run renames nothing.
                if is_regular_file and not getattr(self, "dry_run", False):
                    match = _NUMBERED_VIDEO_SUFFIX.search(file.name)
                    if match:
                        new_name = file.name[: match.start(1) + len(match.group(1))]
                        new_path = file.parent / new_name
                        try:
                            if not new_path.exists():
                                file.rename(new_path)
                                logging.info(f"Renamed misnamed video: {file.name} -> {new_name}")
                            else:
                                logging.warning(f"Cannot rename {file.name} - target already exists: {new_name}")
                        except Exception as e:
                            logging.error(f"Failed to rename {file.name}: {e}")

            # Count videos, RARs, 7z, PAR2s, and content files (optimized single-pass)
            video_extensions = set(self.config.video_extensions)
            music_extensions = set(self.config.music_extensions)
            image_extensions = set(self.config.image_extensions)
            document_extensions = set(self.config.document_extensions)
            rar_pattern = re.compile(r"\.r\d{2}$")
            zip_volume_pattern = re.compile(r"\.z\d{2}$")

            videos: list[Path] = []
            rars: list[Path] = []
            sevenz: list[Path] = []
            zips: list[Path] = []
            par2s: list[Path] = []
            unknown_files = 0  # no known extension: possibly obfuscated archive volumes
            removable_exts = {str(e).lower() for e in getattr(self.config, "removable_extensions", []) or []}
            music_files = 0
            image_files = 0
            image_total_bytes = 0
            document_files = 0

            # PERFORMANCE: Use os.scandir recursively for cached stat() calls (2-3x faster)
            # os.scandir returns DirEntry objects with cached stat info, avoiding repeated stat() calls
            def scan_recursive(path: str | Path) -> Iterator[os.DirEntry[str]]:
                """Recursively scan directory using os.scandir for performance."""
                try:
                    with os.scandir(path) as entries:
                        for entry in entries:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    # Recurse into subdirectories
                                    yield from scan_recursive(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    yield entry
                            except (PermissionError, OSError):
                                # Skip files/folders we can't access
                                continue
                except (PermissionError, OSError):
                    # Skip folders we can't access
                    pass

            # The source root's own files only: its subfolders are releases counted on their own.
            scanned_entries = (
                (e for e in os.scandir(folder) if e.is_file(follow_symlinks=False))
                if folder == source_dir
                else scan_recursive(folder)
            )
            for scanned in scanned_entries:
                ext_lower = Path(scanned.name).suffix.lower()
                filename_lower = scanned.name.lower()
                file_path = Path(scanned.path)

                if ext_lower in video_extensions:
                    videos.append(file_path)
                elif ext_lower == ".rar" or rar_pattern.match(ext_lower):
                    rars.append(file_path)
                elif ext_lower == ".7z" or ".7z." in filename_lower:  # Catch .7z and .7z.001 etc
                    sevenz.append(file_path)
                elif ext_lower == ".zip" or zip_volume_pattern.match(ext_lower):
                    zips.append(file_path)
                elif ext_lower == ".par2":
                    par2s.append(file_path)
                elif ext_lower in music_extensions:
                    music_files += 1
                elif ext_lower in image_extensions:
                    image_files += 1
                    with suppress(OSError, FileNotFoundError):
                        # PERFORMANCE: Use cached stat from DirEntry (no extra syscall)
                        image_total_bytes += scanned.stat(follow_symlinks=False).st_size
                elif ext_lower in document_extensions and ext_lower not in removable_exts:
                    document_files += 1
                elif ext_lower not in removable_exts and ext_lower not in document_extensions:
                    unknown_files += 1

            # Determine if this is a video folder or content folder to preserve
            if videos or rars or sevenz or zips or (par2s and unknown_files):
                # A video folder: videos, archives that might contain them, or a PAR2 set next to
                # unrecognised files (an obfuscated post: .par2 files and randomly named volumes)
                plan.add_video_folder(folder, len(videos), len(rars) + len(sevenz) + len(zips), len(par2s))
            else:
                # No videos or archives: music, photos and documents are what is worth keeping,
                # however few (a 3-track single, a small photo folder). Thresholds default to 1.
                image_total_mb = image_total_bytes / (1024 * 1024)
                has_images = image_files > 0 and image_files >= self.config.min_image_files

                if (
                    (music_files > 0 and music_files >= self.config.min_music_files)
                    or has_images
                    or (document_files > 0 and document_files >= self.config.min_documents)
                ):
                    reasons: list[str] = []
                    if music_files > 0 and music_files >= self.config.min_music_files:
                        reasons.append(f"{music_files} music files")
                    if has_images:
                        reasons.append(f"{image_files} images ({image_total_mb:.1f}MB)")
                    if document_files > 0 and document_files >= self.config.min_documents:
                        reasons.append(f"{document_files} documents")
                    reason_str = ", ".join(reasons)
                    plan.add_content_folder(folder, reason_str)
                else:
                    # Not a video folder and not enough content to preserve by threshold
                    plan.add_junk_folder(folder)
                    file_handler = getattr(self, "file_handler", None)
                    if file_handler is not None and not file_handler.is_folder_empty_or_removable(folder):
                        # It still holds files Unpackr never removes (a few PDFs, MP3s); the run keeps it.
                        plan.junk_kept.add(folder)

        # Check for loose video files (optimized single-pass)
        video_extensions = set(self.config.video_extensions)
        for item in root_entries:
            try:
                is_regular_file = item.is_file()
            except (PermissionError, OSError):
                continue
            if is_regular_file and item.suffix.lower() in video_extensions:
                plan.add_loose_video(item)

        if not getattr(self, "plain_progress", False):
            sys.stdout.write("\r" + " " * 80 + "\r")

        plan.calculate_time_estimate()
        self.work_plan = plan
        return plan

    def _longer_than_sample_cap(self, video: Path) -> bool:
        """True when the video's duration is known and exceeds max_sample_duration_seconds."""
        probe = getattr(getattr(self, "video_processor", None), "probe_duration", None)
        if not callable(probe):
            return False
        duration = probe(video)
        cap = _config_get(getattr(self, "config", None), "max_sample_duration_seconds", 300)
        cap = cap if isinstance(cap, (int, float)) else 300
        if isinstance(duration, (int, float)) and duration > cap:
            logging.info(f"Keeping {video.name}: {duration:.0f}s is longer than a sample ({cap}s cap)")
            return True
        return False

    def _remove_sample_videos(self, video_files: list[Path]) -> list[Path]:
        """
        Remove sample/preview videos if full version exists.

        Detects videos with 'sample', 'preview', 'trailer' in filename and checks
        if a larger full version exists (same base name without sample keyword).

        Args:
            video_files: List of video file paths

        Returns:
            Filtered list with samples removed
        """
        if not video_files:
            return video_files

        sample_keywords = ["sample", "preview", "trailer", "promo"]
        to_delete: list[Path] = []

        # Group videos by folder for efficient comparison
        by_folder: dict[Path, list[Path]] = {}
        for video in video_files:
            folder = video.parent
            if folder not in by_folder:
                by_folder[folder] = []
            by_folder[folder].append(video)

        # For each folder, find sample videos and check if full version exists
        for _folder, videos in by_folder.items():
            for video in videos:
                video_name_lower = video.stem.lower()

                # Check if this is a sample video
                is_sample = any(keyword in video_name_lower for keyword in sample_keywords)

                if is_sample:
                    # Try to find the full version by removing sample keywords and normalizing
                    base_name = video_name_lower
                    for keyword in sample_keywords:
                        # Remove keyword and surrounding separators
                        base_name = base_name.replace(f"-{keyword}", "").replace(f"_{keyword}", "")
                        base_name = base_name.replace(f".{keyword}", "").replace(f"{keyword}-", "")
                        base_name = base_name.replace(f"{keyword}_", "").replace(f"{keyword}.", "")
                        base_name = base_name.replace(keyword, "")

                    # Clean up multiple separators and normalize
                    base_name = base_name.replace("..", ".").replace("--", "-").replace("__", "_")
                    base_name = base_name.replace(".", " ").replace("-", " ").replace("_", " ")
                    base_name = " ".join(base_name.split())  # Normalize whitespace

                    # Extract meaningful words (skip very short words)
                    base_words = {w for w in base_name.split() if len(w) > 2}

                    # Look for a larger video with similar name (without sample keyword)
                    try:
                        sample_size = video.stat().st_size

                        for other_video in videos:
                            if other_video == video:
                                continue

                            other_name_lower = other_video.stem.lower()
                            other_size = other_video.stat().st_size

                            # Check if other video is NOT a sample and is larger
                            other_is_sample = any(keyword in other_name_lower for keyword in sample_keywords)

                            if not other_is_sample and other_size > sample_size:
                                # Normalize other video name
                                other_normalized = (
                                    other_name_lower.replace(".", " ").replace("-", " ").replace("_", " ")
                                )
                                other_words = {w for w in other_normalized.split() if len(w) > 2}

                                if base_words and other_words:
                                    common_words = base_words & other_words
                                    # Calculate match ratio from both sides for better accuracy
                                    match_ratio_1 = len(common_words) / len(base_words) if base_words else 0
                                    match_ratio_2 = len(common_words) / len(other_words) if other_words else 0
                                    avg_ratio = (match_ratio_1 + match_ratio_2) / 2

                                    # If >50% average match, consider it the same video; a long
                                    # "preview" or "promo" episode is real content, not a sample.
                                    if avg_ratio > 0.5 and not UnpackrApp._longer_than_sample_cap(self, video):
                                        to_delete.append(video)
                                        logging.info(
                                            f"Sample video detected: {video.name} ({sample_size / (1024 * 1024):.1f}MB) - full version: {other_video.name} ({other_size / (1024 * 1024):.1f}MB)"
                                        )
                                        self.stats["videos_sample"] += 1
                                        break

                    except (OSError, FileNotFoundError) as e:
                        logging.warning(f"Error checking sample video {video}: {e}")
                        continue

        # Delete sample videos
        for sample_video in to_delete:
            try:
                if not self.dry_run:
                    size = sample_video.stat().st_size
                    file_handler = getattr(self, "file_handler", None)
                    if file_handler is not None:
                        removed = file_handler.remove_file(sample_video, "sample_with_full_version")
                    else:
                        sample_video.unlink()
                        removed = True
                    if removed:
                        logging.info(f"Removed sample video: {sample_video.name}")
                        self._record(sample_video, "deleted", "sample_with_full_version", size=size)
                else:
                    if self.dry_run_plan:
                        try:
                            self.dry_run_plan.add_video_delete(sample_video, "sample/preview file")
                        except Exception as e:
                            logging.debug(f"Dry-run plan sample delete entry failed for {sample_video}: {e}")
                            self.dry_run_plan.add_video_delete(sample_video, "sample/preview file")
                    logging.info(f"[DRY-RUN] Would delete sample video: {sample_video.name}")
                    self._record(sample_video, "deleted", "sample_with_full_version")
            except Exception as e:
                logging.error(f"Failed to delete sample video {sample_video}: {e}")

        # Return filtered list
        return [v for v in video_files if v not in to_delete]

    def _prepare_removal(self, source_dir: Path) -> None:
        """Set up reversible removal for a live run and purge expired quarantine."""
        self.run_id = new_run_id()
        self.remover = None
        if getattr(self, "dry_run", False):
            return
        config = getattr(self, "config", None)
        mode = getattr(config, "delete_mode", "quarantine")
        if not isinstance(mode, str):
            mode = "quarantine"
        self.remover = Remover(mode=mode, source_root=source_dir, run_id=self.run_id)
        for component in (getattr(self, "file_handler", None), getattr(self, "archive_processor", None)):
            if component is not None:
                component.remover = self.remover
        report = getattr(self, "report", None)
        if report is not None:
            report.disposal = mode
        retention = getattr(config, "quarantine_retention_days", 14)
        if isinstance(retention, int) and retention > 0:
            try:
                runs, freed = purge_quarantine(source_dir, retention)
                if runs:
                    logging.info(f"Purged {runs} quarantined run(s) older than {retention} days ({freed / 1e6:.1f}MB)")
            except OSError as e:
                logging.warning(f"Could not purge old quarantine: {e}")

    def _record(self, path: Path, action: str, reason_code: str, detail: str = "", **kwargs: Any) -> None:
        """Record a per-file decision on the run report (no-op without one)."""
        report = getattr(self, "report", None)
        if report is not None:
            report.record(path, action, reason_code, detail, **kwargs)
        if getattr(self, "dry_run", False) and action in ("moved", "deleted", "extracted"):
            assume_gone = getattr(getattr(self, "file_handler", None), "assume_gone", None)
            if callable(assume_gone):
                assume_gone(path)

    def _record_folder_removed(self, folder: Path, reason_code: str) -> None:
        report = getattr(self, "report", None)
        if report is not None:
            report.record_folder_removed(folder, reason_code)

    def _note(self, level: str, folder: Path, item: str, reason_code: str, detail: str) -> None:
        """Record a problem for the summary, the log and the --json errors/warnings."""
        message = f"[{reason_code}] {folder.name}/{item}: {detail}"
        (self.run_errors if level == "error" else self.run_warnings).append(message)

    def _process_archives(
        self,
        folder: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
        archive_sets: list[ArchiveSet] | None = None,
    ) -> tuple[bool, int]:
        """Extract the archive sets in one folder.

        Returns (archive_error, number_of_sets). Sets that are incomplete, unreadable,
        password-protected or interrupted are kept in place and the folder is not
        removed, so the user can fetch the missing part and run again.
        """
        if archive_sets is None:
            archive_sets = find_archive_sets(folder)
        if not archive_sets:
            return False, 0

        if self.dry_run:
            # Same read-only checks as the live run (missing volume, listing, password,
            # unsafe contents), so the plan keeps and blocks the same sets.
            outcomes: list[ArchiveOutcome] = []
            for archive_set in archive_sets:
                outcome = self.archive_processor.preflight_set(archive_set, folder)
                if outcome is None:
                    outcome = ArchiveOutcome(
                        archive_set.name, "extracted", "archive_extracted", "", list(archive_set.volumes)
                    )
                    if self.dry_run_plan and archive_set.first is not None:
                        try:
                            size = sum(v.stat().st_size for v in archive_set.volumes)
                        except OSError:
                            size = 0
                        self.dry_run_plan.add_archive_extract(archive_set.first, size)
                elif self.dry_run_plan:
                    self.dry_run_plan.add_archive_skip(folder / archive_set.name, outcome.detail)
                outcomes.append(outcome)
            UnpackrApp._apply_archive_outcomes(self, folder, outcomes)
            logging.info(f"[DRY-RUN] Would extract {len(archive_sets)} archive set(s) in {folder}")
            extracted = sum(1 for o in outcomes if o.status == "extracted")
            return extracted == 0, len(archive_sets)

        if progress_callback is not None:
            success = self.archive_processor.process_rar_files(folder, progress_callback=progress_callback)
        else:
            success = self.archive_processor.process_rar_files(folder)
        if success:
            self.stats["rars_extracted"] += 1
        UnpackrApp._apply_archive_outcomes(self, folder, self.archive_processor.last_outcomes)
        return not success, len(archive_sets)

    def _apply_archive_outcomes(self, folder: Path, outcomes: list[ArchiveOutcome]) -> None:
        """Record each set's outcome, hold what must stay and note what needs a look."""
        for outcome in outcomes:
            broken = outcome.status == "failed" or (
                outcome.status == "held" and outcome.reason_code in BROKEN_SET_REASONS
            )
            if broken:
                # A manual run means "clean now": a set that cannot be unpacked is junk.
                UnpackrApp._remove_broken_set(self, folder, outcome)
                continue
            action = {"extracted": "extracted", "held": "kept", "blocked": "blocked"}.get(outcome.status, "skipped")
            for volume in outcome.volumes:
                self._record(volume, action, outcome.reason_code, outcome.detail)
            if outcome.status == "held":
                hold = getattr(getattr(self, "file_handler", None), "hold_paths", None)
                if callable(hold):
                    hold(outcome.volumes, outcome.reason_code)
                self._note("error", folder, outcome.name, outcome.reason_code, f"{outcome.detail} (kept for retry)")
            elif outcome.status == "blocked":
                self._note("error", folder, outcome.name, outcome.reason_code, outcome.detail)

    def _remove_broken_set(self, folder: Path, outcome: ArchiveOutcome) -> None:
        """Remove the volumes of a set that cannot be unpacked and list it for re-download."""
        remove = getattr(getattr(self, "file_handler", None), "remove_file", None)
        for volume in outcome.volumes:
            if getattr(self, "dry_run", False) or (callable(remove) and remove(volume, outcome.reason_code)):
                self._record(volume, "deleted", outcome.reason_code, outcome.detail)
            else:
                self._record(volume, "kept", outcome.reason_code, f"{outcome.detail}; could not be removed")
        self._note("warning", folder, outcome.name, outcome.reason_code, f"{outcome.detail}; removed, re-download it")
        damaged: list[str] | None = getattr(self, "damaged", None)
        if damaged is not None:
            damaged.append(f"{folder.name}/{outcome.name}: {outcome.detail}")

    def _verify_par2(self, folder: Path) -> Par2Outcome | None:
        """Verify/repair a folder's PAR2 sets before extraction. Never blocks extraction."""
        try:
            count = sum(1 for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".par2")
        except OSError:
            return None
        if not count:
            return None
        if self.dry_run:
            if self.dry_run_plan:
                self.dry_run_plan.add_par2_process(folder, count)
            logging.info(f"[DRY-RUN] Would verify/repair {count} PAR2 files in {folder}")
            return Par2Outcome("verified", "par2_verified", "dry run")
        stuck = getattr(self, "stuck_detector", None)
        if stuck is not None:
            stuck.mark_progress()
        self.archive_processor.process_par2_files(folder)
        if stuck is not None:
            stuck.mark_progress()
        outcome = self.archive_processor.last_par2
        if outcome.status == "repaired":
            self.stats["par2s_repaired"] += 1
        return outcome

    def _finish_par2(self, folder: Path, par2: Par2Outcome | None, archive_error: bool, had_sets: bool) -> bool:
        """Settle a folder's .par2 files after extraction; return True when PAR2 did not clear the folder.

        - With archives, 7-Zip's CRC check decides: a set PAR2 could not verify but that
          extracted cleanly is good, and its .par2 files are removed with the volumes.
        - PAR2 said the data is damaged beyond repair (it scanned every file): the download
          is broken, so it is junk like any damaged video, listed under "re-download".
        - PAR2 could not judge (tool error, not installed) and the folder holds files Unpackr
          does not recognise (possibly obfuscated volumes): everything is kept for a look.
        """
        if par2 is None:
            return False
        if getattr(self, "dry_run", False) and not had_sets:
            # PAR2 may rename unrecognised files back into archive volumes during the live run;
            # a dry run cannot know, so it keeps them in the plan instead of calling them junk.
            suspects = UnpackrApp._unrecognised_files(self, folder)
            if suspects:
                try:
                    par2_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".par2"]
                except OSError:
                    par2_files = []
                hold = getattr(getattr(self, "file_handler", None), "hold_paths", None)
                if callable(hold):
                    hold(par2_files + suspects, "par2_rename_pending")
                detail = "PAR2 will try to match renamed volumes; decided during the live run"
                for path in par2_files + suspects:
                    self._record(path, "kept", "par2_rename_pending", detail)
                self._note(
                    "warning", folder, "", "par2_rename_pending", f"{len(suspects)} unrecognised file(s): {detail}"
                )
                return True
        if had_sets:
            content_ok = not archive_error
        elif par2.ok:
            content_ok = True
        elif par2.status == "damaged":
            message = f"{folder.name}: {par2.detail}"
            if hasattr(self, "damaged"):
                self.damaged.append(message)
            self._note("warning", folder, "", par2.reason_code, f"{par2.detail}; re-download it")
            return True
        else:
            suspects = UnpackrApp._unrecognised_files(self, folder)
            if suspects:
                try:
                    par2_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".par2"]
                except OSError:
                    par2_files = []
                hold = getattr(getattr(self, "file_handler", None), "hold_paths", None)
                if callable(hold):
                    hold(par2_files + suspects, par2.reason_code)
                for path in par2_files + suspects:
                    self._record(path, "kept", par2.reason_code, par2.detail)
                fix = "install par2 and run again" if par2.status == "unavailable" else "check the log"
                self._note(
                    "error",
                    folder,
                    "",
                    par2.reason_code,
                    f"{par2.detail}; {len(suspects)} unrecognised file(s) kept, {fix}",
                )
                return True
            content_ok = True
        if not content_ok:
            return True
        if not par2.ok and par2.status != "unavailable":
            self._note("warning", folder, "", par2.reason_code, f"{par2.detail}; 7-Zip's CRC check passed")
        try:
            par2_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".par2"]
        except OSError:
            return True
        for path in par2_files:
            self._record(path, "deleted", "par2_cleanup", "content verified and extracted")
        if not self.dry_run:
            self.archive_processor.remove_par2_files(folder)
        return False

    def _unrecognised_files(self, folder: Path) -> list[Path]:
        """Files in ``folder`` with no known extension: candidates for renamed (obfuscated) volumes."""
        config = getattr(self, "config", None)
        known: set[str] = {".par2", ".rar", ".7z", ".zip"}
        for attr in (
            "video_extensions",
            "music_extensions",
            "image_extensions",
            "document_extensions",
            "removable_extensions",
        ):
            values = getattr(config, attr, None)
            if isinstance(values, (list, tuple, set)):
                known.update(str(v).lower() for v in cast("Iterable[object]", values))
        try:
            files = [f for f in folder.iterdir() if f.is_file()]
        except OSError:
            return []
        return [f for f in files if f.suffix.lower() not in known and not is_archive_related(f)]

    def _release_files(self, folder: Path) -> list[Path]:
        """Files that belong to one work item: direct files for the source root, the whole tree otherwise."""
        try:
            if folder == getattr(self, "source_root", None):
                return [p for p in folder.iterdir() if p.is_file() and not is_internal(Path(p.name))]
            files: list[Path] = []
            for current, dirs, names in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".unpackr-")]
                files.extend(Path(current) / n for n in names)
            return files
        except (OSError, TypeError):
            return []

    def _screen_release(self, folder: Path) -> bool:
        """Return False when a release must not be processed this run.

        - Partial downloads (.!qB, .part, .crdownload ...) mean it is still downloading.
        - VIDEO_TS / BDMV disc structures are kept whole.
        - Bait (executables, shortcuts, disguised names, payload subtitles) is quarantined and
          the release fails: no video from it is moved.
        """
        files = self._release_files(folder)
        if not files:
            return True
        config = getattr(self, "config", None)

        partial = [f for f in files if is_incomplete_marker(f, config)]
        if partial:
            # Running Unpackr means "clean now": unfinished downloads are junk. Complete files
            # in the same release are still processed and kept.
            for path in partial:
                if self.dry_run or self.file_handler.remove_file(path, "download_incomplete"):
                    self._record(path, "deleted", "download_incomplete", "unfinished download")
                else:
                    self._record(path, "blocked", "download_incomplete", "unfinished download; could not be removed")
            self._note(
                "warning", folder, partial[0].name, "download_incomplete", f"{len(partial)} unfinished file(s) removed"
            )
            files = [f for f in files if f not in partial]

        if folder != getattr(self, "source_root", None):
            disc = has_disc_structure(folder)
            if disc is not None:
                self._note("warning", folder, disc.name, "disc_structure_kept", "disc structure kept whole")
                for path in files:
                    self._record(path, "kept", "disc_structure_kept")
                return False

        video_exts = set(getattr(config, "video_extensions", []) or [])
        has_video = any(f.suffix.lower() in video_exts for f in files)
        failed = False
        for path in files:
            finding = classify_security(path, config, has_video)
            if finding is None:
                continue
            level = "error" if finding.fails_release else "warning"
            self._note(level, folder, path.name, finding.reason_code, finding.detail)
            if not self.dry_run:
                if self.file_handler.remove_file(path, finding.reason_code):
                    self._record(path, "deleted", finding.reason_code, finding.detail)
                else:
                    self._record(path, "blocked", finding.reason_code, f"{finding.detail}; could not be removed")
            else:
                self._record(path, "deleted", finding.reason_code, finding.detail)
            failed = failed or finding.fails_release

        if failed:
            self._note("error", folder, "", "folder_failed_security", "bait found; nothing moved from this release")
            for path in files:
                report = getattr(self, "report", None)
                if path.exists() and report is not None and not report.is_recorded(path):
                    self._record(path, "blocked", "folder_failed_security")
            if hasattr(self, "failed_releases"):
                self.failed_releases.add(folder)
            # Keep the release folder: its decoy files stay for review and cleanup leaves it alone.
            hold = getattr(self.file_handler, "hold_paths", None)
            if callable(hold):
                hold([p for p in files if p.exists()], "folder_failed_security")
            return False
        return True

    def _decide_release_samples(self, folder: Path) -> None:
        """Mark sample, proof and trailer videos across one release for removal."""
        if folder == getattr(self, "source_root", None) or not hasattr(self, "release_samples"):
            return
        config = getattr(self, "config", None)
        video_exts = set(getattr(config, "video_extensions", []) or [])
        videos = [f for f in self._release_files(folder) if f.suffix.lower() in video_exts]
        if len(videos) < 2:
            return
        durations: dict[Path, float | None] = {}
        sizes: dict[Path, int] = {}
        for video in videos:
            try:
                sizes[video] = video.stat().st_size
            except OSError:
                sizes[video] = 0
            probe: Callable[[Path], float | None] | None = getattr(self.video_processor, "probe_duration", None)
            durations[video] = probe(video) if callable(probe) else None
        samples = decide_release_samples(videos, durations, sizes, config)
        self.release_samples.update(samples)
        dedupe = _config_get(config, "dedupe_same_title", False)
        if dedupe is True:
            remaining = [v for v in videos if v not in samples]
            self.release_samples.update(decide_duplicate_encodes(remaining, sizes))

    def _release_name(self, video_file: Path) -> str | None:
        """Name of the top-level release folder holding a video (None for loose videos)."""
        root = getattr(self, "source_root", None)
        if root is None:
            return video_file.parent.name or None
        try:
            parts = video_file.relative_to(root).parts
        except ValueError:
            return None
        return parts[0] if len(parts) > 1 else None

    def _plan_destination(self, video_file: Path, destination_dir: Path) -> tuple[Path, str]:
        """(target folder, file name) for a video according to output_layout and deobfuscation."""
        config = getattr(self, "config", None)
        layout = _config_get(config, "output_layout", DEFAULT_LAYOUT) or DEFAULT_LAYOUT
        deobfuscate = _config_get(config, "deobfuscate_names", True) is not False
        release = self._release_name(video_file)
        self.last_renamed_from = release if pick_base_name(video_file, release, deobfuscate)[1] else None
        rel = render_layout(layout, video_file, release, deobfuscate)
        if rel is None:
            self._note(
                "warning",
                video_file.parent,
                video_file.name,
                "layout_unparsed",
                f"name does not fit output_layout {layout!r}; used the flat layout",
            )
            rel = render_layout(DEFAULT_LAYOUT, video_file, release, deobfuscate) or Path(video_file.name)
        return destination_dir / rel.parent, rel.name

    def _move_subtitles(self, video_file: Path, final_path: Path) -> None:
        """Move subtitles that belong to a video next to its new location with a matching name."""
        config = getattr(self, "config", None)
        if _config_get(config, "keep_subtitles", True) is False:
            return
        root = getattr(self, "source_root", None)
        release = self._release_name(video_file)
        scope = (root / release) if (root is not None and release) else video_file.parent
        files = [f for f in self._release_files(scope) if f.exists()]
        video_exts = set(getattr(config, "video_extensions", []) or [])
        single_video = sum(1 for f in files if f.suffix.lower() in video_exts) <= 1
        for subtitle in files:
            if subtitle.suffix.lower() not in SUBTITLE_EXTENSIONS:
                continue
            suffix = subtitle_suffix(subtitle, video_file)
            if suffix is None:
                continue
            if subtitle.parent.name.lower() in ("subs", "subtitles", "sub") and not single_video:
                continue  # a shared Subs folder in a season pack cannot be matched safely
            target = final_path.with_name(f"{final_path.stem}{suffix}{subtitle.suffix.lower()}")
            if self.dry_run:
                self._record(subtitle, "moved", "subtitle_moved", destination=target)
                continue
            counter = 1
            while target.exists():
                target = final_path.with_name(f"{final_path.stem}{suffix}.{counter}{subtitle.suffix.lower()}")
                counter += 1
            if self.file_handler.move_file(subtitle, target.parent, target_name=target.name):
                self._record(subtitle, "moved", "subtitle_moved", destination=target)

    def _handle_video(self, video_file: Path, destination_dir: Path) -> bool:
        """Validate one video, then move it to the destination or remove it.

        Previews and samples (shorter than min_video_duration_seconds) and damaged
        or truncated files are removed. Returns True when the video was moved
        (or, in a dry run, would be moved).
        """
        try:
            size_bytes = video_file.stat().st_size
        except OSError:
            size_bytes = 0

        sample = getattr(self, "release_samples", {}).get(video_file)
        if sample is not None:
            reason_code, detail = sample
            self.stats["videos_sample"] += 1
            if self.dry_run:
                if self.dry_run_plan:
                    self.dry_run_plan.add_video_delete(video_file, f"sample: {detail}")
                self._record(video_file, "deleted", reason_code, detail, size=size_bytes)
                return False
            logging.info(f"Removing sample video: {video_file.name} ({reason_code}: {detail})")
            if self.file_handler.remove_file(video_file, reason_code):
                self._record(video_file, "deleted", reason_code, detail, size=size_bytes)
            else:
                self._record(video_file, "kept", "video_delete_failed", f"{reason_code}: {detail}", size=size_bytes)
            return False

        if self.dry_run:
            preview = self.video_processor.classify_preview(self.video_processor.probe_duration(video_file))
            if preview is not None:
                self.stats["videos_sample"] += 1
                if self.dry_run_plan:
                    self.dry_run_plan.add_video_delete(video_file, f"preview or sample: {preview.detail}")
                self._record(video_file, "deleted", preview.reason_code, preview.detail, size=size_bytes)
                logging.info(f"[DRY-RUN] Would remove preview/sample video: {video_file.name} ({preview.detail})")
                return False
            target_dir, target_name = self._plan_destination(video_file, destination_dir)
            planned = target_dir / target_name
            if self.dry_run_plan:
                try:
                    shown = str(planned.relative_to(destination_dir))
                except ValueError:
                    shown = str(planned)
                self.dry_run_plan.add_video_move(video_file, size_bytes, "unknown", destination=shown)
            renamed_from = getattr(self, "last_renamed_from", None)
            self._record(
                video_file,
                "moved",
                "renamed_deobfuscated" if renamed_from else "video_pending_validation",
                "validated during the live run"
                + (f"; obfuscated name replaced with release name {renamed_from}" if renamed_from else ""),
                destination=planned,
                size=size_bytes,
            )
            self._move_subtitles(video_file, planned)
            logging.info(f"[DRY-RUN] Would validate and move {video_file.name} to {destination_dir}")
            self.stats["videos_moved"] += 1
            return True

        if self.video_processor.check_video_health(video_file):
            self.stats["videos_healthy"] += 1
            target_dir, target_name = self._plan_destination(video_file, destination_dir)
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logging.error(f"Cannot create {target_dir}: {e}")
                target_dir, target_name = destination_dir, video_file.name
            if self.file_handler.move_file(video_file, target_dir, target_name=target_name):
                self.stats["videos_moved"] += 1
                logging.info(f"MOVED: {video_file.name} ({size_bytes / (1024 * 1024):.1f}MB) -> {destination_dir}")
                verdict = getattr(self.video_processor, "last_verdict", None)
                renamed_from = getattr(self, "last_renamed_from", None)
                self._record(
                    video_file,
                    "moved",
                    "renamed_deobfuscated" if renamed_from else (verdict.reason_code if verdict else "video_ok"),
                    f"obfuscated name replaced with release name {renamed_from}"
                    if renamed_from
                    else (verdict.detail if verdict else ""),
                    destination=getattr(self.file_handler, "last_moved_to", None) or target_dir / target_name,
                    size=size_bytes,
                )
                final_path = getattr(self.file_handler, "last_moved_to", None) or target_dir / target_name
                if isinstance(final_path, Path):
                    self._move_subtitles(video_file, final_path)
                return True
            self._note(
                "warning", video_file.parent, video_file.name, "video_move_failed", "could not move to destination"
            )
            self._record(video_file, "kept", "video_move_failed", "could not move to destination", size=size_bytes)
            return False

        verdict = self.video_processor.last_verdict
        if verdict is not None and verdict.category == "preview":
            self.stats["videos_sample"] += 1
            logging.info(f"Removing preview/sample video: {video_file.name} ({verdict.detail})")
        else:
            self.stats["videos_corrupt"] += 1
            self.stats["videos_failed"] += 1
            category = verdict.category if verdict else "corrupt"
            detail = f" ({verdict.detail})" if verdict and verdict.detail else ""
            logging.info(f"Removing {category} video: {video_file.name}{detail}")
            if hasattr(self, "damaged"):
                self.damaged.append(f"{video_file.parent.name}/{video_file.name}: {category}{detail}")
        reason_code = verdict.reason_code if verdict else "video_corrupt"
        detail = verdict.detail if verdict else ""
        if self.file_handler.wait_for_file_release(str(video_file)) and self.file_handler.delete_video_file_with_retry(
            video_file, reason_code=reason_code
        ):
            self._record(video_file, "deleted", reason_code, detail, size=size_bytes)
        else:
            self._record(video_file, "kept", "video_delete_failed", f"{reason_code}: {detail}", size=size_bytes)
        return False

    def process_folder(self, folder: Path, destination_dir: Path, current: int, total: int) -> int:
        """
        Process a single folder.

        Args:
            folder: Path to folder to process
            destination_dir: Destination for video files
            current: Current folder number
            total: Total folders to process

        Returns:
            Number of videos successfully moved
        """
        # Reset recursion guard for this folder (guard is per-folder, not global)
        self.recursion_guard.current_depth = 0

        moved_count = 0

        # Update progress immediately when starting a folder
        self._update_progress(current, total, f"Scanning folder: {folder.name[:57]}")

        # Unfinished downloads, disc structures and bait releases are left alone (bait is quarantined).
        if not self._screen_release(folder):
            self.stats["folders_processed"] += 1
            return 0

        # PAR2 first: repair damaged or renamed volumes before extraction. It never removes
        # anything and never stops extraction; 7-Zip checks every file's CRC either way.
        self._update_progress(current, total, f"PAR2 verify/repair: {folder.name[:50]}")
        par2 = UnpackrApp._verify_par2(self, folder)

        archive_sets = find_archive_sets(folder)
        if archive_sets:
            self._update_progress(current, total, f"Extract {len(archive_sets)} archive set(s): {folder.name[:40]}")
        self.stuck_detector.mark_progress()

        def extraction_progress(idx: int, total_archives: int, msg: str) -> None:
            folder_context = f"[{folder.name[:30]}]" if len(folder.name) > 30 else f"[{folder.name}]"
            self._update_progress(current, total, f"{folder_context} {msg}")
            self.stuck_detector.mark_progress()

        archive_error, _ = self._process_archives(
            folder, progress_callback=extraction_progress, archive_sets=archive_sets
        )
        self.stuck_detector.mark_progress()
        par2_error = UnpackrApp._finish_par2(self, folder, par2, archive_error, bool(archive_sets))

        # Decide samples across the whole release (Sample/ and Proof/ folders included).
        self._decide_release_samples(folder)

        # Process video files FIRST (before recursing into subfolders)
        video_files = self.file_handler.find_video_files(folder)

        # Remove sample/preview videos if full version exists
        video_files = self._remove_sample_videos(video_files)

        # Note: videos_found is already set from work_plan.total_videos in run()
        # Don't increment here to avoid double-counting

        for idx, video_file in enumerate(video_files, 1):
            folder_context = f"[{folder.name[:30]}]" if len(folder.name) > 30 else f"[{folder.name}]"
            self._update_progress(
                current, total, f"{folder_context} Validate {idx}/{len(video_files)}: {video_file.name[:40]}"
            )
            if self._handle_video(video_file, destination_dir):
                moved_count += 1

        # Process subfolders AFTER processing videos in this folder. The source root's
        # subfolders are releases of their own and are processed as separate work items.
        if folder != getattr(self, "source_root", None):
            for subfolder in folder.iterdir():
                if subfolder.is_dir() and not is_internal(Path(subfolder.name)):
                    self._process_subfolder(subfolder, destination_dir)

        # Clean up folder if possible
        if self.file_handler.is_folder_empty_or_removable(folder, par2_error, archive_error):
            if self.dry_run:
                if self.dry_run_plan:
                    self.dry_run_plan.add_folder_delete(folder)
                self._record_folder_removed(folder, "processed_folder")
                logging.info(f"[DRY-RUN] Would delete folder: {folder}")
                self.stats["folders_deleted"] += 1
            else:
                # Pass par2_error and archive_error for double-check (race condition protection)
                if self.file_handler.safe_delete_folder(folder, par2_error=par2_error, archive_error=archive_error):
                    self.stats["folders_deleted"] += 1
                else:
                    # Track failed deletion for retry
                    self.failed_deletions.append((folder, par2_error, archive_error))
                    logging.warning(f"Failed to delete folder {folder}, will retry later")

        self.stats["folders_processed"] += 1
        return moved_count

    def _start_spinner_thread(self) -> None:
        """Start background thread to animate spinner."""
        if getattr(self, "renderer", None) is not None or getattr(self, "plain_progress", False):
            return
        if not self.spinner_running:
            self.spinner_running = True
            self.spinner_thread = threading.Thread(target=self._spinner_loop, daemon=True)
            self.spinner_thread.start()

    def stop_spinner_thread(self) -> None:
        """Stop background spinner thread."""
        renderer = getattr(self, "renderer", None)
        if renderer is not None:
            renderer.stop()
            return
        self.spinner_running = False
        if self.spinner_thread:
            self.spinner_thread.join(timeout=1.0)

    def _load_comments(self) -> CommentsData:
        """
        Load random comments from a custom file or the bundled sample.

        A comments.json beside an explicit config file takes precedence. The
        bundled sample is read directly so installed package files stay read-only.
        """
        try:
            bundled_dir = Path(__file__).parent / "config_files"
            config = getattr(self, "config", None)
            config_path = getattr(config, "config_path", None)
            custom_dir = Path(config_path).parent if config_path else bundled_dir
            candidates = [
                custom_dir / "comments.json",
                bundled_dir / "comments.json",
                bundled_dir / "comments.sample.json",
            ]

            comments_file = next((path for path in candidates if path.is_file()), None)
            if comments_file is not None:
                with open(comments_file, encoding="utf-8") as f:
                    data: dict[str, Any] = json.load(f)
                # Support both old format (list) and new format (dict with rarities)
                if isinstance(data.get("comments"), dict):
                    return data  # New rarity-based format
                flat: list[str] = data.get("comments", [])
                return flat  # Old flat list format
        except Exception as e:
            logging.debug(f"Could not load comments: {e}")
        return []

    def _get_random_comment(self, current_folder: int) -> CommentDisplay | None:
        """
        Randomly return a snarky comment with rarity-based drop rates.
        Comments persist for the entire folder - only change when moving to new eligible folder.

        Args:
            current_folder: Current folder number being processed

        Returns:
            Tuple of (comment, rarity, color, effect) or None
        """
        # Check if we need to generate a new comment (every 10 folders)
        should_show_comment = current_folder - self.last_comment_folder >= 10

        # Clear stored comment if we've moved past it
        # Only clear if the current folder shouldn't show this old comment
        if current_folder != self.last_comment_folder and not should_show_comment:
            self.current_comment_display = None

        # If we have a valid comment for the current eligible folder, return it
        if self.current_comment_display is not None and current_folder == self.last_comment_folder:
            return self.current_comment_display

        # Don't show comment if cooldown hasn't elapsed
        if not should_show_comment:
            return None

        # Check if we have comments loaded
        if not self.comments:
            return None

        # Generate new comment for this folder
        self.last_comment_folder = current_folder

        # Support old format (flat list)
        if isinstance(self.comments, list):
            comment_result: CommentDisplay = (
                random.choice(self.comments),  # nosec B311 - cosmetic UI randomness only
                None,
                Fore.YELLOW,
                "normal",
            )
            self.current_comment_display = comment_result
            return comment_result

        # New rarity-based format
        rarities = self.comments.get("rarities", {})
        comments_by_rarity = self.comments.get("comments", {})

        # Build weighted pool of rarities
        rarity_pool: list[str] = []
        for rarity_name, rarity_config in rarities.items():
            weight = rarity_config.get("weight", 1)
            rarity_pool.extend([rarity_name] * weight)

        if not rarity_pool:
            return None

        # Roll for rarity
        selected_rarity = random.choice(rarity_pool)  # nosec B311 - cosmetic UI randomness only
        rarity_config = rarities[selected_rarity]
        comment_list = comments_by_rarity.get(selected_rarity, [])

        if not comment_list:
            return None

        comment = random.choice(comment_list)  # nosec B311 - cosmetic UI randomness only

        # Get color from colorama
        color_map = {
            "white": Fore.WHITE,
            "green": Fore.GREEN,
            "cyan": Fore.CYAN,
            "magenta": Fore.MAGENTA,
            "yellow": Fore.YELLOW,
            "red": Fore.RED,
            "blue": Fore.BLUE,
        }
        color = color_map.get(rarity_config.get("color", "yellow"), Fore.YELLOW)
        effect = rarity_config.get("effect", "normal")

        comment_result = (comment, selected_rarity, color, effect)
        self.current_comment_display = comment_result
        return comment_result

    def _spinner_loop(self) -> None:
        """Background thread - updates spinner every second."""
        while self.spinner_running:
            time.sleep(1.0)  # Update once per second
            if self.spinner_running:  # Check again after sleep
                with self.spinner_lock:
                    # Just update the spinner character in-place
                    spinner = self.spinner_frames[self.spinner_index]
                    self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
                    # Move to line 13, column 3 (spinner line) and update just that character
                    sys.stdout.write(f"\033[13;3H{Fore.GREEN}{spinner}{Style.RESET_ALL}")
                    sys.stdout.flush()

    @staticmethod
    def _sanitize_console_text(text: str) -> str:
        """Best-effort sanitize text for the active stdout encoding."""
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        except LookupError:
            return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

    @staticmethod
    def _derive_progress_context(action: str) -> tuple[str, str]:
        """
        Convert a progress action string into a normalized verb + target.

        Returns:
            Tuple of (verb, target)
        """
        verb = "working"
        target = action

        if "Scanning" in action or "Finding" in action or "Checking" in action:
            verb = "scanning"
            if ":" in action:
                target = action.split(":", 1)[1].strip()
        elif "PAR2" in action or "verify" in action or "repair" in action:
            verb = "repairing"
            if ":" in action:
                target = action.split(":", 1)[1].strip()
        elif "Extract" in action or "Extracting" in action:
            verb = "extracting"
            if "]" in action and ":" in action:
                folder_part = action.split("]")[0] + "]"
                filename_part = action.split(":")[-1].strip()
                target = f"{folder_part} {filename_part}"
            elif ":" in action:
                target = action.split(":", 1)[1].strip()
        elif "Validate" in action:
            verb = "validating"
            if "]" in action and ":" in action:
                folder_part = action.split("]")[0] + "]"
                filename_part = action.split(":")[-1].strip()
                target = f"{folder_part} {filename_part}"
            elif ":" in action:
                target = action.split(":")[-1].strip()

        return verb, target

    def _update_progress(self, current: int, total: int, action: str) -> None:
        """
        Update progress display - clear screen and show clean fixed display.

        Args:
            current: Current item number
            total: Total items
            action: Current action description
        """
        with self.spinner_lock:
            self.current_action = action
            spinner = self.spinner_frames[self.spinner_index]
            self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)

        # Calculate percentage and ETA
        percent = int((current / total) * 100)

        if self.start_time:
            elapsed = time.time() - self.start_time
            # Need at least 10 folders and 30 seconds for meaningful speed estimate
            # Early folders are often just quick scans, which inflates the speed
            if current >= 10 and elapsed >= 30.0:
                avg_time = elapsed / current
                remaining = (total - current) * avg_time
                eta = str(timedelta(seconds=int(remaining))).split(".")[0]
                throughput = (current / elapsed) * 60
            else:
                eta = "calculating..."
                throughput = None  # Signal to display "---" instead of 0.0
        else:
            eta = "calculating..."
            throughput = None

        # Progress bar - modern block characters
        bar_length = 40
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)

        # Stats - compact but clear, show interesting work being done
        # found = total videos discovered (before processing)
        # processed = videos that passed health checks and were moved to destination
        # bad = videos that were corrupt or samples (deleted, not moved)
        videos_found = self.stats["videos_found"]
        videos_processed = self.stats["videos_moved"]
        bad_videos = self.stats["videos_corrupt"] + self.stats["videos_sample"]

        # Core stats: found vs processed (success rate at a glance)
        stats_line = f"  {Style.DIM}found videos:{Style.RESET_ALL} {Fore.WHITE}{videos_found}{Style.RESET_ALL}  {Style.DIM}processed:{Style.RESET_ALL} {Fore.GREEN}{videos_processed}{Style.RESET_ALL}"

        # Show bad videos removed
        if bad_videos > 0:
            stats_line += f"  {Style.DIM}bad:{Style.RESET_ALL} {Fore.RED}{bad_videos}{Style.RESET_ALL}"

        # Show work done: extraction, repair, cleanup
        if self.stats["rars_extracted"] > 0:
            stats_line += (
                f"  {Style.DIM}extracted:{Style.RESET_ALL} {Fore.CYAN}{self.stats['rars_extracted']}{Style.RESET_ALL}"
            )

        if self.stats["par2s_repaired"] > 0:
            stats_line += (
                f"  {Style.DIM}repaired:{Style.RESET_ALL} {Fore.MAGENTA}{self.stats['par2s_repaired']}{Style.RESET_ALL}"
            )

        # Show cleanup progress
        if self.stats["folders_deleted"] > 0:
            stats_line += (
                f"  {Style.DIM}cleaned:{Style.RESET_ALL} {Fore.YELLOW}{self.stats['folders_deleted']}{Style.RESET_ALL}"
            )

        if self.stats["empty_folders_deleted"] > 0:
            stats_line += f"  {Style.DIM}empty:{Style.RESET_ALL} {Fore.CYAN}{self.stats['empty_folders_deleted']}{Style.RESET_ALL}"

        if self.stats["junk_files_deleted"] > 0:
            stats_line += (
                f"  {Style.DIM}junk:{Style.RESET_ALL} {Fore.YELLOW}{self.stats['junk_files_deleted']}{Style.RESET_ALL}"
            )

        # Conservative estimate for manual processing per folder:
        # Using 2 min as conservative baseline (user would likely take longer in practice)
        manual_time_minutes = current * 2
        time_saved_hours = manual_time_minutes / 60
        time_saved_str = f"{int(manual_time_minutes)} min" if time_saved_hours < 1 else f"{time_saved_hours:.1f} hrs"
        throughput_str = f"{throughput:>5.1f}" if throughput is not None else "  ---"

        # Without a terminal (service, cron, pipes) redraws would only fill the log: one line per folder.
        if getattr(self, "plain_progress", False):
            if current != getattr(self, "_last_plain_progress", 0):
                self._last_plain_progress = current
                _verb, target = UnpackrApp._derive_progress_context(action)
                print(f"[{current}/{total}] {UnpackrApp._sanitize_console_text(target)}", flush=True)
            return

        # Rich/plain renderer path for cross-platform terminals.
        renderer = getattr(self, "renderer", None)
        if renderer is not None:
            if self.first_progress_update:
                self.first_progress_update = False
                renderer.start(total)

            verb, target = UnpackrApp._derive_progress_context(action)
            safe_target = UnpackrApp._sanitize_console_text(target)
            safe_verb = UnpackrApp._sanitize_console_text(verb)

            comment_result = self._get_random_comment(current)
            comment_line = ""
            if comment_result:
                comment_line = _comment_text(comment_result)[:75]

            renderer.update(
                current=current,
                total=total,
                action=UnpackrApp._sanitize_console_text(action),
                verb=UnpackrApp._sanitize_console_text(verb),
                target=UnpackrApp._sanitize_console_text(target),
                stats_line=re.sub(r"\x1b\[[0-9;]*m", "", UnpackrApp._sanitize_console_text(stats_line)),
                time_line=UnpackrApp._sanitize_console_text(
                    f"speed: {throughput_str.strip()} folders/min | eta: {eta} | saved: {time_saved_str}"
                ),
                comment_line=UnpackrApp._sanitize_console_text(comment_line),
            )
            return

        # Clear screen and redraw on first update only
        if self.first_progress_update:
            self.first_progress_update = False
            sys.stdout.write("\033[2J\033[H")  # Clear and home

            # ASCII art header
            print(f"""  {Style.DIM}_   _ _ __  _ __   __ _  ___| | ___ __
 | | | | '_ \\| '_ \\ / _` |/ __| |/ / '__|
 | |_| | | | | |_) | (_| | (__|   <| |
  \\__,_|_| |_| .__/ \\__,_|\\___|_|\\_\\_|
             |_|{Style.RESET_ALL}
""")
            # Start spinner thread after first render
            self._start_spinner_thread()
        else:
            # Move cursor back to progress bar line (line 7)
            sys.stdout.write("\033[7;1H")  # Move to line 7, column 1

        # Progress bar
        sys.stdout.write(
            UnpackrApp._sanitize_console_text(
                f"  {Style.DIM}[{Style.RESET_ALL}{Fore.GREEN}{bar}{Style.DIM}]{Style.RESET_ALL} {Fore.WHITE}{percent}%{Style.RESET_ALL} {Style.DIM}│{Style.RESET_ALL} {Fore.WHITE}{current}{Style.RESET_ALL}{Style.DIM}/{total} folders{Style.RESET_ALL}\033[K\n"
            )
        )

        # Stats
        sys.stdout.write(UnpackrApp._sanitize_console_text(f"{stats_line}\033[K\n"))

        # Time metrics
        sys.stdout.write(
            UnpackrApp._sanitize_console_text(
                f"  {Style.DIM}speed:{Style.RESET_ALL} {Fore.CYAN}{throughput_str}{Style.RESET_ALL} {Style.DIM}folders/min  time left:{Style.RESET_ALL} {Fore.CYAN}{eta}{Style.RESET_ALL}  {Style.DIM}saved:{Style.RESET_ALL} {Fore.MAGENTA}{time_saved_str}{Style.RESET_ALL}\033[K\n"
            )
        )
        sys.stdout.write("\n")

        # Extract operation and target for display.
        verb, target = UnpackrApp._derive_progress_context(action)
        safe_target = UnpackrApp._sanitize_console_text(target)
        safe_verb = UnpackrApp._sanitize_console_text(verb)

        # Current file/folder (line 11)
        sys.stdout.write(
            UnpackrApp._sanitize_console_text(f"  {Style.DIM}>{Style.RESET_ALL} {safe_target[:80]:<80}\033[K\n")
        )

        # Easter egg comment (line 12) - optional snarky comment with rarity
        comment_result = self._get_random_comment(current)
        if comment_result:
            sys.stdout.write(UnpackrApp._sanitize_console_text(_comment_terminal_line(comment_result)))
        else:
            sys.stdout.write("\033[K\n")  # Clear line if no comment

        # Spinner line (line 13) - spinner + verb
        sys.stdout.write(
            UnpackrApp._sanitize_console_text(
                f"  {Fore.GREEN}{spinner}{Style.RESET_ALL} {Style.DIM}{safe_verb}{Style.RESET_ALL}\033[K"
            )
        )

        sys.stdout.flush()

    def _process_subfolder(self, subfolder: Path, destination_dir: Path) -> None:
        """
        Recursively process subfolder, including archive extraction.

        Args:
            subfolder: Path to subfolder
            destination_dir: Destination for video files
        """
        # Safety: prevent infinite recursion
        if not self.recursion_guard.enter():
            logging.error(f"[SAFETY] Max recursion depth reached at {subfolder}")
            self.stats["safety_stops"] += 1
            return

        try:
            # PAR2 first (never blocks extraction), then the archive sets in this subfolder
            par2 = UnpackrApp._verify_par2(self, subfolder)
            archive_error, sets_here = self._process_archives(subfolder)
            if sets_here:
                logging.info(f"Processed {sets_here} archive set(s) in subfolder {subfolder.name}")
            par2_error = UnpackrApp._finish_par2(self, subfolder, par2, archive_error, bool(sets_here))

            # Find and process videos in this subfolder
            video_files = self.file_handler.find_video_files(subfolder)
            # Track total videos found (before processing)
            self.stats["videos_found"] += len(video_files)
            for video_file in video_files:
                self._handle_video(video_file, destination_dir)

            # Recursively process nested subfolders
            for sub in subfolder.iterdir():
                if sub.is_dir() and not is_internal(Path(sub.name)):
                    self._process_subfolder(sub, destination_dir)

            # Check if subfolder can be deleted
            if self.file_handler.is_folder_empty_or_removable(subfolder, par2_error, archive_error):
                if self.dry_run:
                    self._record_folder_removed(subfolder, "processed_folder")
                    logging.info(f"[DRY-RUN] Would delete subfolder: {subfolder}")
                else:
                    # Pass par2_error and archive_error for double-check (race condition protection)
                    if not self.file_handler.safe_delete_folder(
                        subfolder, par2_error=par2_error, archive_error=archive_error
                    ):
                        # Track failed deletion for retry
                        self.failed_deletions.append((subfolder, par2_error, archive_error))
                        logging.warning(f"Failed to delete subfolder {subfolder}, will retry later")
        finally:
            self.recursion_guard.exit()

    def run(self, source_dir: Path, destination_dir: Path) -> None:
        """
        Run the main processing loop.

        Args:
            source_dir: Source directory to process
            destination_dir: Destination for video files
        """
        # Store destination for display_summary tip
        self.destination_dir = destination_dir

        # Get video folders from work plan
        if not self.work_plan:
            print(Fore.RED + "No work plan available. Run scan_and_plan() first." + Style.RESET_ALL)
            return

        video_folders = [item["path"] for item in self.work_plan.video_folders]

        report = getattr(self, "report", None)
        if report is not None:
            report.planned = bool(getattr(self, "dry_run", False))
            report.begin(source_dir)
        self._prepare_removal(source_dir)
        # Archive removals go through the safety invariants (I3: never before extraction).
        archive_processor = getattr(self, "archive_processor", None)
        if archive_processor is not None and not getattr(self, "dry_run", False):
            archive_processor.enforcer = InvariantEnforcer(destination_dir, getattr(self, "config", None))
        self.source_root = source_dir
        self.release_samples: dict[Path, tuple[str, str]] = {}
        self.failed_releases: set[Path] = set()

        run_state = getattr(self, "run_state", None)
        if getattr(self, "resume_enabled", False) and run_state is not None:
            before = len(video_folders)
            video_folders = [folder for folder in video_folders if not run_state.is_completed(folder)]
            skipped = before - len(video_folders)
            if skipped:
                logging.info(f"Resume: skipping {skipped} already-completed folder(s)")
                print(f"{Fore.CYAN}Resume: skipping {skipped} completed folder(s){Style.RESET_ALL}")

        if not video_folders:
            print(Fore.YELLOW + "No video folders found to process." + Style.RESET_ALL)
            return

        # Track preserved folders
        self.stats["folders_preserved"] = len(self.work_plan.content_folders)

        # Initialize videos_found from pre-scan total
        self.stats["videos_found"] = self.work_plan.total_videos

        # Reset all run state (ensure nothing persists from previous runs)
        self.start_time = time.time()
        self.progress_current = 0
        self.current_comment_display = None
        self.last_comment_folder = -10  # Reset to allow first folder to show comment

        # Use actual folder count that updates as we process
        # Start with initial scan count
        self.progress_total = len(video_folders)
        total = self.progress_total

        logging.info(f"Starting run: {total} folders to process")

        # Safety: Initialize runtime limit from config
        max_runtime_seconds = self.config.max_runtime_hours * 3600
        self.runtime_limit = OperationTimer(max_runtime_seconds, "Total Unpackr Runtime")

        # Safety: loop guard for folder processing
        loop_guard = LoopSafety(self.config.max_videos_per_folder * 2, "Folder processing loop")

        try:
            for i, folder in enumerate(video_folders, 1):
                # Debug: Log first iteration to confirm enumerate starts at 1
                if i == 1:
                    logging.info(f"Processing first folder (i=1): {folder.name}")

                # CANCELLATION CHECKPOINT: Check before each folder
                if self.cancellation_requested:
                    logging.info(f"Cancellation requested - stopping after {i - 1} folders")
                    break

                # Safety checks
                if not loop_guard.tick():
                    logging.error("[SAFETY] Folder processing loop exceeded safety limit")
                    self.stats["safety_stops"] += 1
                    break

                if not self.runtime_limit.check():
                    logging.error(f"[SAFETY] Runtime limit exceeded ({self.config.max_runtime_hours} hours) - stopping")
                    self.stats["safety_stops"] += 1
                    break

                if not self.stuck_detector.check():
                    logging.error("[SAFETY] Process appears stuck - stopping")
                    self.stats["safety_stops"] += 1
                    break

                # Process folder
                self.process_folder(folder, destination_dir, i, total)
                if run_state is not None and not self.cancellation_requested and not getattr(self, "dry_run", False):
                    run_state.mark_completed(folder)

                # Mark progress for stuck detection
                self.stuck_detector.mark_progress()

            # Loose videos in the source root were handled when the root itself was processed.

            # Delete junk folders identified in pre-scan (skip if cancelled)
            if self.work_plan.junk_folders and not self.cancellation_requested:
                logging.info(f"Deleting {len(self.work_plan.junk_folders)} junk folders identified in pre-scan")
                for junk_folder in self.work_plan.junk_folders:
                    if self.cancellation_requested:
                        break
                    try:
                        if self.dry_run:
                            # Same check as the live run, so the plan keeps what the run keeps.
                            if self.file_handler.is_folder_empty_or_removable(
                                junk_folder, par2_error=False, archive_error=False
                            ):
                                self._record_folder_removed(junk_folder, "junk_folder")
                                if self.dry_run_plan:
                                    self.dry_run_plan.add_folder_delete(junk_folder)
                                logging.info(f"[DRY-RUN] Would delete junk folder: {junk_folder}")
                                self.stats["folders_deleted"] += 1
                        else:
                            # Check if folder is still removable (contents might have changed)
                            if self.file_handler.is_folder_empty_or_removable(
                                junk_folder, par2_error=False, archive_error=False
                            ):
                                if self.file_handler.safe_delete_folder(junk_folder, reason_code="junk_folder"):
                                    self.stats["folders_deleted"] += 1
                                    logging.info(f"Deleted junk folder: {junk_folder.name}")
                                else:
                                    logging.warning(f"Failed to delete junk folder: {junk_folder.name}")
                            else:
                                logging.info(f"Skipping junk folder (no longer removable): {junk_folder.name}")
                    except Exception as e:
                        logging.error(f"Error deleting junk folder {junk_folder}: {e}")

        finally:
            # Stop spinner thread
            self.stop_spinner_thread()
            # Clear progress line
            if not getattr(self, "plain_progress", False):
                sys.stdout.write("\r" + " " * 100 + "\r")
                sys.stdout.flush()

            # Print dry-run summary if in dry-run mode
            if self.dry_run and self.dry_run_plan:
                self.dry_run_plan.print_summary()

    def retry_failed_deletions(self, max_passes: int = 3, wait_seconds: int = 30) -> None:
        """
        Retry deletion of folders that failed during main processing.
        Uses multi-pass approach with delays to allow file locks to release.

        Args:
            max_passes: Maximum number of retry passes
            wait_seconds: Seconds to wait between passes
        """
        if not self.failed_deletions:
            return

        if self.dry_run:
            logging.info(f"[DRY-RUN] Would retry {len(self.failed_deletions)} failed deletions")
            return

        print(f"\n{Fore.YELLOW}Retrying {len(self.failed_deletions)} failed folder deletions...{Style.RESET_ALL}")

        for pass_num in range(1, max_passes + 1):
            if not self.failed_deletions:
                break

            if pass_num > 1:
                print(f"Waiting {wait_seconds}s before pass {pass_num}/{max_passes}...")
                time.sleep(wait_seconds)

            print(f"Cleanup pass {pass_num}/{max_passes}: {len(self.failed_deletions)} folders remaining")

            # Try to delete each failed folder
            remaining: deque[tuple[Path, bool, bool]] = deque(maxlen=1000)
            for folder, par2_error, archive_error in self.failed_deletions:
                # Check if folder still exists and is still removable
                if not folder.exists():
                    logging.info(f"Folder already gone: {folder}")
                    continue

                if not self.file_handler.is_folder_empty_or_removable(folder, par2_error, archive_error):
                    logging.info(f"Folder no longer removable: {folder}")
                    continue

                # Try to delete (double-check happens inside safe_delete_folder)
                if self.file_handler.safe_delete_folder(folder, par2_error=par2_error, archive_error=archive_error):
                    self.stats["folders_deleted"] += 1
                    logging.info(f"Successfully deleted on retry: {folder}")
                else:
                    remaining.append((folder, par2_error, archive_error))

            self.failed_deletions = remaining

        if self.failed_deletions:
            print(f"{Fore.RED}Warning: {len(self.failed_deletions)} folders could not be deleted{Style.RESET_ALL}")
            for folder, _, _ in self.failed_deletions:
                logging.warning(f"Permanent deletion failure: {folder}")

    def cleanup_empty_folders(self, source_dir: Path, show_progress: bool = False) -> None:
        """Final cleanup pass to delete remaining empty folders - recursive, multi-pass.

        Args:
            source_dir: Root directory to scan
            show_progress: Show live progress updates during scan
        """
        logging.info("Starting final cleanup of empty folders (recursive, multi-pass)")
        total_deleted = 0
        max_passes = 5  # Keep trying until nothing left to delete

        for pass_num in range(1, max_passes + 1):
            pass_deleted = 0
            folders_checked = 0

            try:
                # RECURSIVE: Walk through all directories bottom-up
                # This deletes deepest folders first, then parents
                for root, dirs, _files in os.walk(source_dir, topdown=False):
                    for dir_name in dirs:
                        folder = Path(root) / dir_name
                        if is_internal(folder.relative_to(source_dir)):
                            continue
                        folders_checked += 1

                        # Show progress every 50 folders (only on first pass and if enabled)
                        if show_progress and pass_num == 1 and folders_checked % 50 == 0:
                            print(
                                f"\r{Style.DIM}  Scanned {folders_checked} folders...{Style.RESET_ALL}",
                                end="",
                                flush=True,
                            )

                        try:
                            # Check if folder is empty
                            if not any(folder.iterdir()) and self.file_handler.safe_delete_folder(folder):
                                pass_deleted += 1
                                total_deleted += 1
                                logging.info(f"Pass {pass_num}: Deleted empty folder: {folder}")
                        except PermissionError:
                            logging.warning(f"Permission denied: {folder}")
                            continue
                        except Exception as e:
                            logging.warning(f"Error checking {folder}: {e}")
                            continue

            except Exception as e:
                logging.error(f"Error during cleanup pass {pass_num}: {e}")

            # Clear progress line if shown
            if show_progress and pass_num == 1:
                print(f"\r{' ' * 50}\r", end="", flush=True)

            # If nothing deleted this pass, we're done
            if pass_deleted == 0:
                logging.info(f"Cleanup complete after {pass_num} passes (checked {folders_checked} folders)")
                break
            else:
                logging.info(f"Pass {pass_num}: Deleted {pass_deleted} empty folders")

        if total_deleted > 0:
            self.stats["empty_folders_deleted"] = total_deleted
            print(f"{Fore.GREEN}Cleaned up {total_deleted} empty folders{Style.RESET_ALL}")
            logging.info(f"Final cleanup: deleted {total_deleted} empty folders total")

    def removal_summary(self) -> dict[str, Any] | None:
        """How this run disposed of removed files, for the summary screen and --json."""
        remover = getattr(self, "remover", None)
        if remover is None:
            return None
        source = remover.source_root
        retention = getattr(getattr(self, "config", None), "quarantine_retention_days", 14)
        return {
            "mode": remover.mode,
            "run_id": remover.run_id,
            "journal": str(remover.journal.path) if remover.journal else None,
            "quarantine_path": str(remover.quarantine_dir) if remover.mode == "quarantine" else None,
            "quarantined_files": remover.quarantined_files,
            "quarantined_bytes": remover.quarantined_bytes,
            "trashed_files": remover.trashed_files,
            "retention_days": retention if isinstance(retention, int) else 14,
            "restore_command": f'unpackr restore {remover.run_id} --source "{source}"',
        }

    def finish_issues(self) -> tuple[list[str], list[str]]:
        """Final error and warning lists, including whole-run observations."""
        warnings = list(self.run_warnings)
        removed = self.stats["videos_sample"] + self.stats["videos_corrupt"]
        if not self.dry_run and self.stats["videos_moved"] == 0 and removed > 0:
            warnings.append(
                f"[no_videos_kept] no videos were kept: {self.stats['videos_sample']} removed as previews or samples, "
                f"{self.stats['videos_corrupt']} as damaged"
            )
        return list(self.run_errors), warnings

    def display_summary(self) -> None:
        """Display processing summary with detailed stats."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        elapsed_str = str(timedelta(seconds=int(elapsed))).split(".")[0]

        # Clear screen and show final summary
        if not getattr(self, "plain_progress", False):
            sys.stdout.write("\033[2J\033[H")

        total_cleaned = self.stats["folders_deleted"] + self.stats["empty_folders_deleted"]

        # Show cancelled or complete status
        status = (
            f"{Fore.YELLOW}cancelled{Style.RESET_ALL}"
            if self.cancellation_requested
            else f"{Fore.GREEN}complete{Style.RESET_ALL}"
        )

        print(f"""
  {Style.DIM}_   _ _ __  _ __   __ _  ___| | ___ __
 | | | | '_ \\| '_ \\ / _` |/ __| |/ / '__|
 | |_| | | | | |_) | (_| | (__|   <| |
  \\__,_|_| |_| .__/ \\__,_|\\___|_|\\_\\_|
             |_|{Style.RESET_ALL}  {status} {Style.DIM}- runtime:{Style.RESET_ALL} {Fore.CYAN}{elapsed_str}{Style.RESET_ALL}

  {Style.DIM}FOLDERS{Style.RESET_ALL}  processed: {Fore.WHITE}{self.stats["folders_processed"]:>4}{Style.RESET_ALL}  |  deleted: {Fore.GREEN}{self.stats["folders_deleted"]:>4}{Style.RESET_ALL}  |  empty: {Fore.CYAN}{self.stats["empty_folders_deleted"]:>4}{Style.RESET_ALL}  |  preserved: {Fore.MAGENTA}{self.stats["folders_preserved"]:>4}{Style.RESET_ALL}  |  {Fore.GREEN}total cleaned: {total_cleaned}{Style.RESET_ALL}
  {Style.DIM}VIDEOS{Style.RESET_ALL}   found: {Fore.WHITE}{self.stats["videos_found"]:>4}{Style.RESET_ALL}  |  processed: {Fore.GREEN}{self.stats["videos_moved"]:>4}{Style.RESET_ALL}  |  samples: {Fore.YELLOW}{self.stats["videos_sample"]:>4}{Style.RESET_ALL}  |  corrupt: {Fore.RED}{self.stats["videos_corrupt"]:>4}{Style.RESET_ALL}  |  failed: {Fore.RED}{self.stats["videos_failed"]:>4}{Style.RESET_ALL}
  {Style.DIM}ARCHIVES{Style.RESET_ALL} extracted: {Fore.CYAN}{self.stats["rars_extracted"]:>4}{Style.RESET_ALL}  |  repaired: {Fore.MAGENTA}{self.stats["par2s_repaired"]:>4}{Style.RESET_ALL}""")

        if self.stats["files_sanitized"] > 0:
            print(
                f"  {Style.DIM}FILES{Style.RESET_ALL}    sanitized: {Fore.CYAN}{self.stats['files_sanitized']:>4}{Style.RESET_ALL}"
            )

        # Show warnings/tips on same line if possible
        warnings: list[str] = []
        if self.stats["safety_stops"] > 0:
            warnings.append(f"{Fore.RED}SAFETY STOPS: {self.stats['safety_stops']}{Style.RESET_ALL}")
        if self.failed_deletions:
            warnings.append(f"{Fore.YELLOW}locked folders: {len(self.failed_deletions)}{Style.RESET_ALL}")

        if warnings:
            print(f"\n  {' | '.join(warnings)}")

        removal = self.removal_summary()
        if removal and (removal["quarantined_files"] or removal["trashed_files"]):
            if removal["mode"] == "quarantine":
                print(
                    f"\n  {Style.DIM}QUARANTINE{Style.RESET_ALL} {removal['quarantined_files']} files, "
                    f"{removal['quarantined_bytes'] / (1024 * 1024):.1f} MB held"
                    + (f" for {removal['retention_days']} days" if removal["retention_days"] else "")
                    + f"  |  undo: {removal['restore_command']}"
                )
            else:
                print(
                    f"\n  {Style.DIM}TRASH{Style.RESET_ALL} {removal['trashed_files']} files sent to the system trash"
                )

        damaged = getattr(self, "damaged", [])
        if damaged:
            print(f"\n  {Fore.YELLOW}DAMAGED, RE-DOWNLOAD ({len(damaged)}){Style.RESET_ALL}")
            for message in damaged[:5]:
                print(f"    {message}")
            if len(damaged) > 5:
                print(f"    ... and {len(damaged) - 5} more (see the log or --json)")

        if self.run_errors:
            label = "WOULD NEED ATTENTION" if self.dry_run else "NEEDS ATTENTION"
            print(f"\n  {Fore.RED}{label} ({len(self.run_errors)}){Style.RESET_ALL}")
            for message in self.run_errors[:10]:
                print(f"    {message}")
            if len(self.run_errors) > 10:
                print(f"    ... and {len(self.run_errors) - 10} more (see the log or --json)")

        # Suggest vhealth for collection maintenance if videos were processed
        if self.stats["videos_moved"] > 0 and self.destination_dir:
            print(
                f"\n  {Style.DIM}Tip: Run 'vhealth \"{self.destination_dir}\"' to check for duplicates, samples, and corruption{Style.RESET_ALL}"
            )


def _is_interactive() -> bool:
    """True when a person can see the terminal and press Ctrl+C."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def main() -> None:
    """Main entry point with defensive error handling."""
    init()  # Initialize colorama with default settings; may be refined after args/config.

    json_mode = False
    json_out = sys.stdout
    source_for_summary: str | None = None
    dest_for_summary: str | None = None
    app: UnpackrApp | None = None
    dry_run = False

    report_path: Path | None = None
    report_items: list[dict[str, Any]] | None = None

    def emit_json_and_exit(
        exit_code: int,
        status: str,
        *,
        cancelled: bool = False,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        plan: list[dict[str, Any]] | None = None,
    ) -> NoReturn:
        if json_mode or report_path is not None:
            stats = app.stats.get_snapshot() if app is not None else {}
            summary = build_unpackr_run_summary(
                status=status,
                exit_code=exit_code,
                source=source_for_summary,
                destination=dest_for_summary,
                dry_run=dry_run,
                cancelled=cancelled,
                stats=stats,
                errors=errors,
                warnings=warnings,
                version=__version__,
                items=report_items,
                plan=plan,
                removal=app.removal_summary() if app is not None and hasattr(app, "removal_summary") else None,
                damaged=list(getattr(app, "damaged", []) or []) if app is not None else None,
            )
            if report_path is not None and report_items is not None:
                try:
                    header = {k: v for k, v in summary.items() if k not in ("items",)}
                    RunReport.write_jsonl([ReportItem(**item) for item in report_items], report_path, summary=header)
                except OSError as e:
                    logging.error(f"Could not write report {report_path}: {e}")
            if json_mode:
                print(dumps_run_summary(summary), file=json_out, flush=True)
        sys.stdout = json_out
        raise SystemExit(exit_code)

    def collect_report_items() -> None:
        nonlocal report_items
        report = getattr(app, "report", None) if app is not None else None
        if report is None:
            return
        removable = getattr(getattr(app, "config", None), "removable_extensions", [])
        report_items = [item.to_dict() for item in report.finalize(removable)]

    if len(sys.argv) > 1 and sys.argv[1] == "service":
        print(
            "unpackr service was removed in 1.6.0: Unpackr is run by hand, not on a schedule.\n"
            "To remove an installed timer: delete ~/.config/systemd/user/unpackr-* and run "
            "`systemctl --user daemon-reload`.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMMANDS:
        raise SystemExit(run_subcommand(sys.argv[1:]))

    try:
        # Parse arguments
        parser = build_unpackr_arg_parser()
        args = parser.parse_args()
        json_mode = bool(getattr(args, "json", False))
        if json_mode:
            # stdout carries only the JSON summary (so `unpackr --json | jq` works); the
            # banner, progress and summary screen go to stderr.
            sys.stdout = sys.stderr
        if getattr(args, "report", None):
            report_path = Path(os.path.expanduser(args.report))
        dry_run = bool(args.dry_run)

        args.source, args.destination = resolve_unpackr_paths(args, parser)

        # Load configuration defensively
        config_path = (
            Path(args.config) if args.config else Path(__file__).resolve().parent / "config_files" / "config.json"
        )

        try:
            config = Config(config_path)
            if not getattr(config, "is_valid", True):
                raise ValueError(f"configuration file is invalid or unavailable: {config_path}")
        except Exception as e:
            print(Fore.RED + f"Error loading config: {e}" + Style.RESET_ALL)
            logging.error(f"Config load failed: {e}", exc_info=True)
            emit_json_and_exit(1, "failed", errors=[f"config load failed: {e}"])

        # Resolve presentation settings before any major console output.
        animation_mode, no_color = resolve_cli_presentation(args, config)
        if no_color:
            init(strip=True)

        print(ASCII_ART if no_color else Fore.YELLOW + ASCII_ART + Style.RESET_ALL)

        # Set up logging
        try:
            log_file = setup_logging(config.log_folder, config.max_log_files)
            logging.info("=" * 70)
            logging.info("Unpackr started")
            logging.info(f"Log file: {log_file}")
        except Exception as e:
            print(Fore.RED + f"Error setting up logging: {e}" + Style.RESET_ALL)
            emit_json_and_exit(1, "failed", errors=[f"logging setup failed: {e}"])

        # Get and validate source and destination paths
        if args.source and args.destination:
            # Clean and validate paths defensively
            try:
                source_str = clean_path(args.source)
                dest_str = clean_path(args.destination)

                source_dir = InputValidator.validate_path(source_str, must_exist=True, must_be_dir=True)
                dest_candidate = Path(os.path.expanduser(dest_str))
                planning_only = bool(args.dry_run or args.show_plan)
                if not dest_candidate.exists():
                    if not dest_candidate.parent.is_dir():
                        raise ValidationError(
                            f"Destination does not exist and neither does its parent: {dest_candidate}"
                        )
                    if planning_only:
                        print(
                            f"{Fore.CYAN}Destination will be created on a live run: {dest_candidate}{Style.RESET_ALL}"
                        )
                    else:
                        dest_candidate.mkdir()
                        print(f"{Fore.CYAN}Created destination: {dest_candidate}{Style.RESET_ALL}")
                        logging.info(f"Created destination directory {dest_candidate}")
                if dest_candidate.exists():
                    destination_dir = InputValidator.validate_path(dest_str, must_exist=True, must_be_dir=True)
                else:
                    destination_dir = dest_candidate.absolute()

            except ValidationError as e:
                print(Fore.RED + f"Path validation failed: {e}" + Style.RESET_ALL)
                logging.error(f"Path validation: {e}")
                emit_json_and_exit(1, "failed", errors=[f"path validation failed: {e}"])

        else:
            # Interactive mode - get paths from user
            if json_mode:
                emit_json_and_exit(
                    1,
                    "failed",
                    errors=["interactive path prompts are unavailable with --json; pass --source and --destination"],
                )
            print(
                Style.BRIGHT
                + Fore.YELLOW
                + "This script requires 7-Zip; par2cmdline is recommended for repair support."
                + Style.RESET_ALL
            )
            print(Fore.CYAN + "\nEnter paths with or without quotes." + Style.RESET_ALL)
            source_dir = get_user_input("\nEnter the path to your downloads directory: ")
            destination_dir = get_user_input("Enter the path to your destination directory: ")

        if source_dir is None or destination_dir is None:
            logging.error("Source or destination directory was not provided")
            emit_json_and_exit(1, "failed", errors=["source or destination directory was not provided"])

        source_for_summary = str(source_dir)
        dest_for_summary = str(destination_dir)

        # One live run per source: a second run started on the same folder exits cleanly.
        if not (args.dry_run or args.show_plan):
            run_lock = RunLock(source_dir)
            try:
                locked = run_lock.acquire()
            except OSError as e:
                logging.warning(f"Could not create lock {run_lock.path}: {e}")
                locked = True
            if not locked:
                holder = run_lock.holder()
                message = f"another unpackr run is working on {source_dir}" + (f" (pid {holder})" if holder else "")
                print(f"{Fore.YELLOW}Skipped: {message}.{Style.RESET_ALL}")
                logging.info(f"Skipped: {message}")
                emit_json_and_exit(1, "failed", errors=[f"[run_locked] {message}"])
            atexit.register(run_lock.release)

        # Defensive: Additional checks on paths
        writable_target = destination_dir if destination_dir.exists() else destination_dir.parent
        if not StateValidator.check_dir_writable(writable_target):
            print(Fore.RED + f"Destination directory is not writable: {destination_dir}" + Style.RESET_ALL)
            logging.error(f"Destination not writable: {destination_dir}")
            emit_json_and_exit(1, "failed", errors=[f"destination not writable: {destination_dir}"])

        if not StateValidator.check_disk_space(writable_target, required_mb=1000):
            print(Fore.YELLOW + "Warning: Low disk space in destination directory" + Style.RESET_ALL)
            logging.warning("Low disk space warning")

        # Check system requirements
        print("Checking requirements...", end=" ")
        system_check = SystemCheck(config)
        tools_status = system_check.check_all_tools()
        if not system_check.display_tool_status(tools_status):
            logging.error("Required tools missing")
            emit_json_and_exit(1, "failed", errors=["required tools missing"])

        # Check for running processes from previous session (only ones working on this source)
        system_check.source_dir = source_dir
        system_check.dry_run = bool(args.dry_run)
        if not system_check.warn_running_processes():
            emit_json_and_exit(0, "cancelled", cancelled=True, warnings=["user aborted due to process conflicts"])

        # Create app and scan first
        try:
            app = UnpackrApp(config)
            app.renderer = create_renderer(mode=animation_mode, no_color=no_color)
            app.dry_run = args.dry_run
            if args.dry_run:
                app.dry_run_plan = DryRunPlan()  # Initialize plan collector
                print(f"{Fore.YELLOW}[DRY-RUN MODE] No files will be modified{Style.RESET_ALL}")
                logging.info("Dry-run mode enabled - no modifications will be made")
        except Exception as e:
            print(Fore.RED + f"Error initializing application: {e}" + Style.RESET_ALL)
            logging.error(f"App init failed: {e}", exc_info=True)
            emit_json_and_exit(1, "failed", errors=[f"app init failed: {e}"])

        runtime_app = app

        runtime_app.plain_progress = app.renderer is None and not _is_interactive()
        runtime_app.resume_enabled = bool(getattr(args, "resume", False))
        state_path = default_state_path(source_dir)
        runtime_app.run_state = RunState.load(state_path) if runtime_app.resume_enabled else RunState(path=state_path)
        runtime_app.run_state.configure(source_dir, destination_dir)
        if runtime_app.resume_enabled:
            logging.info(f"Resume enabled; state file: {state_path}")

        # Set up graceful cancellation handler
        def handle_cancel(signum: int, frame: FrameType | None) -> None:
            if runtime_app.cancellation_requested:
                # Second Ctrl+C = force exit
                print(f"\n{Fore.RED}Force exit...{Style.RESET_ALL}")
                runtime_app.stop_spinner_thread()
                sys.exit(1)
            runtime_app.cancellation_requested = True
            print(f"\n{Fore.YELLOW}Cancellation requested - finishing current operation...{Style.RESET_ALL}")
            logging.info("User requested cancellation (Ctrl+C)")
            # Terminate active subprocess if any
            if runtime_app.active_process:
                try:
                    runtime_app.active_process.terminate()
                    logging.info("Terminated active subprocess")
                except Exception:
                    logging.debug("Failed to terminate active subprocess cleanly", exc_info=True)

        signal.signal(signal.SIGINT, handle_cancel)

        # Scan and plan
        try:
            work_plan = runtime_app.scan_and_plan(source_dir)
        except Exception as e:
            print(Fore.RED + f"Error during scan: {e}" + Style.RESET_ALL)
            logging.error(f"Scan failed: {e}", exc_info=True)
            emit_json_and_exit(1, "failed", errors=[f"scan failed: {e}"])

        # If --show-plan, display detailed plan and exit
        if args.show_plan:
            work_plan.display_detailed()
            print(f"{Fore.CYAN}Source: {source_dir}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Destination: {destination_dir}{Style.RESET_ALL}")
            print(f"\n{Fore.GREEN}Pre-flight check complete. No changes made.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Run without --show-plan to execute.{Style.RESET_ALL}\n")
            emit_json_and_exit(0, "planned", plan=work_plan.as_plan_entries(source_dir))

        # Display work plan (compact single line)
        work_plan.display()

        # Display confirmation (compact)
        mode = f"{Fore.YELLOW}DRY-RUN{Style.RESET_ALL}" if args.dry_run else f"{Fore.GREEN}LIVE-RUN{Style.RESET_ALL}"
        vhealth_mode = (
            f"{Fore.GREEN}enabled{Style.RESET_ALL}" if args.vhealth else f"{Style.DIM}disabled{Style.RESET_ALL}"
        )
        print(f"\n{Fore.CYAN}Run Overview{Style.RESET_ALL}")
        print(f"  Mode:        {mode}")
        print(f"  Source:      {Fore.CYAN}{source_dir}{Style.RESET_ALL}")
        print(f"  Destination: {Fore.CYAN}{destination_dir}{Style.RESET_ALL}")
        print(f"  Log:         {log_file.name}")
        print(f"  Post-check:  vhealth {vhealth_mode}")
        if args.dry_run:
            print(f"  {Fore.YELLOW}No files will be modified in dry-run mode.{Style.RESET_ALL}")
        else:
            print(f"  {Fore.RED}Processed folders will be deleted after successful moves.{Style.RESET_ALL}")

        # Quick pre-flight check before countdown
        if not quick_preflight(config, source_dir, destination_dir):
            logging.error("Pre-flight check failed")
            emit_json_and_exit(1, "failed", errors=["pre-flight check failed"])

        # The countdown is a chance to cancel a live run; dry runs change nothing and
        # automation (--json, no terminal) cannot answer it.
        if json_mode:
            logging.info("JSON mode: skipping interactive countdown")
        elif args.dry_run:
            logging.info("Dry run: skipping countdown")
        elif not _is_interactive():
            logging.info("No interactive terminal: skipping countdown")
        elif not countdown_prompt(10, operation_label="processing"):
            logging.info("User cancelled operation")
            emit_json_and_exit(0, "cancelled", cancelled=True)

        # Initial cleanup: delete empty folders first for quick wins
        # Skip on first pass if there are many folders (will be cleaned up at end anyway)
        try:
            num_video_folders = len(work_plan.video_folders)
            if num_video_folders < 50:
                print(f"{Fore.CYAN}Initial cleanup...{Style.RESET_ALL}", flush=True)
                runtime_app.cleanup_empty_folders(source_dir, show_progress=False)
            else:
                # Skip initial cleanup when there are many folders (too slow)
                logging.info(f"Skipping initial cleanup ({num_video_folders} folders - will clean up at end)")
        except Exception as e:
            logging.error(f"Initial cleanup failed: {e}", exc_info=True)
            print(f"{Fore.YELLOW}Warning: Initial cleanup had errors (continuing anyway){Style.RESET_ALL}")

        # Run the application
        print()  # Blank line before progress
        try:
            runtime_app.run(source_dir, destination_dir)

            # Skip cleanup if cancelled
            if not runtime_app.cancellation_requested:
                # Multi-pass cleanup for locked folders
                runtime_app.retry_failed_deletions()

                # Final cleanup of empty folders
                runtime_app.cleanup_empty_folders(source_dir)

            runtime_app.display_summary()

            if runtime_app.cancellation_requested:
                logging.info("Unpackr cancelled by user")
            else:
                logging.info("Unpackr completed successfully")

            # Run vhealth on destination if requested (skip if cancelled)
            if args.vhealth and destination_dir and not runtime_app.cancellation_requested:
                print(f"\n{Fore.CYAN}Running video health check on destination...{Style.RESET_ALL}\n")
                try:
                    from vhealth import VideoHealthChecker

                    checker = VideoHealthChecker(config)
                    checker.check_path(
                        destination_dir,
                        min_resolution=None,
                        skip_samples=False,
                        skip_health=False,  # Full health check
                    )
                    checker.print_summary(auto_delete=False)  # Prompt user before deleting
                    logging.info("Video health check completed")
                except Exception as e:
                    print(f"{Fore.YELLOW}Video health check failed: {e}{Style.RESET_ALL}")
                    logging.error(f"vhealth failed: {e}", exc_info=True)

            collect_report_items()
            if runtime_app.cancellation_requested:
                emit_json_and_exit(0, "cancelled", cancelled=True)
            runtime_app.run_state.clear()
            run_errors, run_warnings = runtime_app.finish_issues()
            if run_errors and not runtime_app.dry_run:
                logging.warning(f"Completed with {len(run_errors)} item(s) needing attention")
                emit_json_and_exit(
                    EXIT_COMPLETED_WITH_ERRORS, "completed_with_errors", errors=run_errors, warnings=run_warnings
                )
            emit_json_and_exit(0, "completed", warnings=run_errors + run_warnings)
        except Exception as e:
            print(Fore.RED + f"\nFatal error during processing: {e}" + Style.RESET_ALL)
            logging.error(f"Processing failed: {e}", exc_info=True)
            runtime_app.stop_spinner_thread()  # Ensure spinner stops before exit
            runtime_app.display_summary()  # Show what we accomplished
            emit_json_and_exit(1, "failed", errors=[f"processing failed: {e}"])

    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\nOperation interrupted by user" + Style.RESET_ALL)
        logging.info("User interrupted operation")
        # Stop spinner if app was initialized. Use `app`, not `runtime_app`: Ctrl+C can land
        # after UnpackrApp(...) returns but before runtime_app is assigned.
        if app is not None:
            app.stop_spinner_thread()
        emit_json_and_exit(0, "cancelled", cancelled=True)
    except Exception as e:
        print(Fore.RED + f"\nUnexpected error: {e}" + Style.RESET_ALL)
        logging.error(f"Unexpected error: {e}", exc_info=True)
        # Stop spinner if app was initialized (runtime_app may not be assigned yet).
        if app is not None:
            app.stop_spinner_thread()
        emit_json_and_exit(1, "failed", errors=[f"unexpected error: {e}"])


if __name__ == "__main__":
    main()
