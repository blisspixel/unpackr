"""
Unpackr: Your Digital Declutterer
Automate, Organize, and Streamline Your Downloads with Ease

A specialized tool for cleaning up download folders from Usenet/newsgroups.
Extracts archives, repairs files, validates videos, and removes garbage.
"""

import sys
import time
import argparse
import logging
import re
import os
import threading
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from colorama import init, Fore, Style

from core import Config, setup_logging
from core.file_handler import FileHandler
from core.archive_processor import ArchiveProcessor
from core.video_processor import VideoProcessor
from utils.system_check import SystemCheck
from utils.safety import (GLOBAL_RUNTIME_LIMIT, LoopSafety, RecursionSafety, 
                          SafetyLimits, StuckDetector)
from utils.defensive import InputValidator, StateValidator, ValidationError


class ThreadSafeStats:
    """Thread-safe statistics tracking with atomic operations."""

    def __init__(self):
        """Initialize statistics with thread safety."""
        self._lock = threading.Lock()
        self._stats = {
            'folders_processed': 0,
            'folders_deleted': 0,
            'folders_preserved': 0,
            'empty_folders_deleted': 0,
            'videos_moved': 0,
            'videos_healthy': 0,
            'videos_corrupt': 0,
            'videos_sample': 0,
            'videos_failed': 0,
            'files_sanitized': 0,
            'rars_extracted': 0,
            'par2s_repaired': 0,
            'junk_files_deleted': 0,
            'safety_stops': 0
        }

    def increment(self, key: str, value: int = 1):
        """Atomically increment a statistic."""
        with self._lock:
            if key in self._stats:
                self._stats[key] += value

    def __getitem__(self, key: str) -> int:
        """Thread-safe get operation."""
        with self._lock:
            return self._stats.get(key, 0)

    def __setitem__(self, key: str, value: int):
        """
        Thread-safe set operation.

        Note: self.stats['key'] += 1 is NOT fully atomic (involves get+set).
        Use increment() method for true atomic increments if needed.
        However, since only the main thread modifies stats and the spinner
        only reads, this is safe for current architecture.
        """
        with self._lock:
            self._stats[key] = value

    def get_snapshot(self) -> dict:
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


class WorkPlan:
    """Represents the work plan from pre-scan analysis."""
    
    def __init__(self):
        self.video_folders = []
        self.content_folders = []
        self.loose_videos = []
        self.total_videos = 0
        self.total_rars = 0
        self.total_par2s = 0
        self.estimated_time = 0
        
    def add_video_folder(self, folder: Path, videos: int, rars: int, par2s: int):
        """Add a video folder to the plan."""
        self.video_folders.append({
            'path': folder,
            'videos': videos,
            'rars': rars,
            'par2s': par2s
        })
        self.total_videos += videos
        self.total_rars += rars
        self.total_par2s += par2s
        
    def add_content_folder(self, folder: Path, reason: str = ""):
        """Add a content folder to keep."""
        self.content_folders.append({
            'path': folder,
            'reason': reason
        })
        
    def add_loose_video(self, video: Path):
        """Add a loose video file."""
        self.loose_videos.append(video)
        self.total_videos += 1
        
    def calculate_time_estimate(self):
        """Calculate estimated processing time."""
        # More realistic estimates:
        # - 10 seconds per video check (FFmpeg can be slow)
        # - 3 seconds per RAR (usually just extracts first .part001)
        # - 5 seconds per PAR2 set (usually just verifies, rarely repairs)
        # - 2 seconds per folder operation

        time_estimate = 0
        time_estimate += self.total_videos * 10  # Video health checks
        time_estimate += self.total_rars * 3     # RAR extractions (only .part001)
        time_estimate += self.total_par2s * 5    # PAR2 verify (not full repair)
        time_estimate += len(self.video_folders) * 2  # Folder operations

        self.estimated_time = time_estimate
        return time_estimate
        
    def display(self):
        """Display the work plan."""
        # Compact single-line summary
        eta = timedelta(seconds=self.estimated_time)
        eta_str = str(eta).split('.')[0]

        print(f"[PLAN] {Fore.YELLOW}{len(self.video_folders)}{Style.RESET_ALL} folders, "
              f"{Fore.YELLOW}{self.total_videos}{Style.RESET_ALL} videos, "
              f"{Fore.YELLOW}{self.total_rars}{Style.RESET_ALL} RARs, "
              f"{Fore.YELLOW}{self.total_par2s}{Style.RESET_ALL} PAR2s | "
              f"ETA: {Fore.CYAN}{eta_str}{Style.RESET_ALL} | "
              f"{Fore.GREEN}{len(self.content_folders)}{Style.RESET_ALL} folders preserved")

    def display_detailed(self):
        """Display detailed pre-flight plan showing what will happen to each folder."""
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}PRE-FLIGHT CHECK - Detailed Plan{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Video folders to process
        if self.video_folders:
            print(f"{Fore.YELLOW}FOLDERS TO PROCESS ({len(self.video_folders)} folders):{Style.RESET_ALL}")
            print(f"{Fore.WHITE}These will be processed: PAR2 verify -> RAR extract -> Video check -> Move good videos -> Delete folder{Style.RESET_ALL}\n")
            for item in self.video_folders:
                folder = item['path']
                videos = item['videos']
                rars = item['rars']
                par2s = item['par2s']

                actions = []
                if par2s > 0:
                    actions.append(f"{par2s} PAR2")
                if rars > 0:
                    actions.append(f"{rars} RAR")
                if videos > 0:
                    actions.append(f"{videos} video(s)")

                action_str = " -> ".join(actions) if actions else "scan only"
                print(f"  {Fore.GREEN}+{Style.RESET_ALL} {folder.name[:60]:<60} | {action_str}")
            print()

        # Content folders to preserve
        if self.content_folders:
            print(f"{Fore.GREEN}FOLDERS TO PRESERVE ({len(self.content_folders)} folders):{Style.RESET_ALL}")
            print(f"{Fore.WHITE}These will NOT be deleted (contain music/images/documents){Style.RESET_ALL}\n")
            for item in self.content_folders:
                folder = item['path']
                reason = item.get('reason', 'content detected')
                print(f"  {Fore.BLUE}*{Style.RESET_ALL} {folder.name[:60]:<60} | {reason}")
            print()

        # Summary
        eta = timedelta(seconds=self.estimated_time)
        eta_str = str(eta).split('.')[0]
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}SUMMARY:{Style.RESET_ALL}")
        print(f"  Process: {len(self.video_folders)} folders -> {self.total_videos} videos -> Estimated time: {eta_str}")
        print(f"  Preserve: {len(self.content_folders)} folders (will NOT be deleted)")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")


class UnpackrApp:
    """Main application class for Unpackr."""
    
    def __init__(self, config: Config):
        """
        Initialize the application.
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.stats = ThreadSafeStats()  # Thread-safe statistics tracking
        # Initialize handlers with stats tracking
        self.file_handler = FileHandler(config, self.stats)
        self.archive_processor = ArchiveProcessor(config)
        self.video_processor = VideoProcessor(config)
        self.dry_run = False  # Set to True for dry-run mode
        self.start_time = None
        self.work_plan = None
        self.failed_deletions = []  # Track folders that couldn't be deleted
        self.recursion_guard = RecursionSafety(config.max_subfolder_depth, "Subfolder processing")
        self.stuck_detector = StuckDetector(timeout=config.stuck_timeout_hours * 3600, check_interval=60)
        self.runtime_limit = None  # Will be initialized when processing starts
        self.spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']  # Modern spinner
        self.spinner_index = 0
        self.first_progress_update = True  # Track if this is the first render
        self.current_action = ""  # Current action text
        self.progress_current = 0  # Current progress
        self.progress_total = 0  # Total progress
        self.spinner_thread = None  # Background spinner thread
        self.spinner_running = False  # Control flag for spinner thread
        self.spinner_lock = threading.Lock()  # Thread safety for spinner updates

        # Load snarky comments for easter eggs
        self.comments = self._load_comments()
        self.last_comment_folder = -1  # Track when we last showed a comment

    def scan_and_plan(self, source_dir: Path) -> WorkPlan:
        """
        Scan source directory and create a work plan.
        
        Args:
            source_dir: Source directory to scan
            
        Returns:
            WorkPlan instance
        """
        plan = WorkPlan()
        # Sort folders by modification time (oldest first) to process completed downloads before ongoing ones
        folders = sorted([f for f in source_dir.iterdir() if f.is_dir()],
                        key=lambda f: f.stat().st_mtime)

        # Show progress during scan
        for i, folder in enumerate(folders, 1):
            sys.stdout.write(f"\r[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
            sys.stdout.flush()
            
            # Count videos, RARs, 7z, PAR2s, and content files (optimized single-pass)
            video_extensions = set(self.config.video_extensions)
            music_extensions = set(self.config.music_extensions)
            image_extensions = set(self.config.image_extensions)
            document_extensions = set(self.config.document_extensions)
            rar_pattern = re.compile(r'\.r\d{2}$')
            sevenz_pattern = re.compile(r'\.7z(\.\d+)?$')

            videos = []
            rars = []
            sevenz = []
            par2s = []
            music_files = 0
            image_files = 0
            image_total_bytes = 0
            document_files = 0

            # RECURSIVE: Walk through folder and all subfolders to find files
            for root, dirs, files in os.walk(folder):
                for filename in files:
                    file = Path(root) / filename
                    ext_lower = file.suffix.lower()
                    filename_lower = file.name.lower()

                    if ext_lower in video_extensions:
                        videos.append(file)
                    elif ext_lower == '.rar' or rar_pattern.match(ext_lower):
                        rars.append(file)
                    elif ext_lower == '.7z' or '.7z.' in filename_lower:  # Catch .7z and .7z.001 etc
                        sevenz.append(file)
                    elif ext_lower == '.par2':
                        par2s.append(file)
                    elif ext_lower in music_extensions:
                        music_files += 1
                    elif ext_lower in image_extensions:
                        image_files += 1
                        try:
                            image_total_bytes += file.stat().st_size
                        except (OSError, FileNotFoundError):
                            pass
                    elif ext_lower in document_extensions:
                        document_files += 1

            # Determine if this is a video folder or content folder to preserve
            if videos or rars or sevenz:
                # This is a video folder (has videos or archives that might contain videos)
                plan.add_video_folder(folder, len(videos), len(rars), len(par2s))
            else:
                # Check if this is a content folder worth preserving
                # For images: must have both >10 files AND >10MB total (avoids thumbnail folders)
                image_total_mb = image_total_bytes / (1024 * 1024)
                has_significant_images = (image_files > self.config.min_image_files and
                                         image_total_mb > 10)

                if (music_files > self.config.min_music_files or
                    has_significant_images or
                    document_files > self.config.min_documents):
                    # This is a content folder with significant music/images/docs - preserve it
                    reasons = []
                    if music_files > self.config.min_music_files:
                        reasons.append(f"{music_files} music files")
                    if has_significant_images:
                        reasons.append(f"{image_files} images ({image_total_mb:.1f}MB)")
                    if document_files > self.config.min_documents:
                        reasons.append(f"{document_files} documents")
                    reason_str = ", ".join(reasons)
                    plan.add_content_folder(folder, reason_str)
            # Otherwise: not a video folder and not enough content to preserve - will be skipped/deleted
        
        # Check for loose video files (optimized single-pass)
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov'}
        for item in source_dir.iterdir():
            if item.is_file() and item.suffix.lower() in video_extensions:
                plan.add_loose_video(item)
        
        sys.stdout.write("\r" + " "*80 + "\r")
        
        plan.calculate_time_estimate()
        self.work_plan = plan
        return plan

    def _remove_sample_videos(self, video_files: list) -> list:
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

        sample_keywords = ['sample', 'preview', 'trailer', 'promo']
        to_delete = []

        # Group videos by folder for efficient comparison
        by_folder = {}
        for video in video_files:
            folder = video.parent
            if folder not in by_folder:
                by_folder[folder] = []
            by_folder[folder].append(video)

        # For each folder, find sample videos and check if full version exists
        for folder, videos in by_folder.items():
            for video in videos:
                video_name_lower = video.stem.lower()

                # Check if this is a sample video
                is_sample = any(keyword in video_name_lower for keyword in sample_keywords)

                if is_sample:
                    # Try to find the full version by removing sample keywords and normalizing
                    base_name = video_name_lower
                    for keyword in sample_keywords:
                        # Remove keyword and surrounding separators
                        base_name = base_name.replace(f'-{keyword}', '').replace(f'_{keyword}', '')
                        base_name = base_name.replace(f'.{keyword}', '').replace(f'{keyword}-', '')
                        base_name = base_name.replace(f'{keyword}_', '').replace(f'{keyword}.', '')
                        base_name = base_name.replace(keyword, '')

                    # Clean up multiple separators and normalize
                    base_name = base_name.replace('..', '.').replace('--', '-').replace('__', '_')
                    base_name = base_name.replace('.', ' ').replace('-', ' ').replace('_', ' ')
                    base_name = ' '.join(base_name.split())  # Normalize whitespace

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
                                other_normalized = other_name_lower.replace('.', ' ').replace('-', ' ').replace('_', ' ')
                                other_words = {w for w in other_normalized.split() if len(w) > 2}

                                if base_words and other_words:
                                    common_words = base_words & other_words
                                    # Calculate match ratio from both sides for better accuracy
                                    match_ratio_1 = len(common_words) / len(base_words) if base_words else 0
                                    match_ratio_2 = len(common_words) / len(other_words) if other_words else 0
                                    avg_ratio = (match_ratio_1 + match_ratio_2) / 2

                                    # If >50% average match, consider it the same video
                                    if avg_ratio > 0.5:
                                        to_delete.append(video)
                                        logging.info(f"Sample video detected: {video.name} ({sample_size / (1024*1024):.1f}MB) - full version: {other_video.name} ({other_size / (1024*1024):.1f}MB)")
                                        self.stats['videos_sample'] += 1
                                        break

                    except (OSError, FileNotFoundError) as e:
                        logging.warning(f"Error checking sample video {video}: {e}")
                        continue

        # Delete sample videos
        for sample_video in to_delete:
            try:
                if not self.dry_run:
                    sample_video.unlink()
                    logging.info(f"Deleted sample video: {sample_video.name}")
                else:
                    logging.info(f"[DRY-RUN] Would delete sample video: {sample_video.name}")
            except Exception as e:
                logging.error(f"Failed to delete sample video {sample_video}: {e}")

        # Return filtered list
        return [v for v in video_files if v not in to_delete]

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

        # Process PAR2 files FIRST - verify/repair archives before extraction
        # This is more efficient: if no repair needed, PAR2 files are deleted early (saves disk I/O)
        # If repair fails, corrupted archives are deleted, skipping extraction entirely
        par2_files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == '.par2']
        if par2_files:
            self._update_progress(current, total, f"PAR2 verify/repair: {folder.name[:50]}")
            self.stuck_detector.mark_progress()  # Mark progress before long PAR2 operation
            if self.dry_run:
                logging.info(f"[DRY-RUN] Would verify/repair {len(par2_files)} PAR2 files in {folder}")
                success = True
                par2_error = False
            else:
                success = self.archive_processor.process_par2_files(folder)
                if success:
                    self.stats['par2s_repaired'] += 1
                self.stuck_detector.mark_progress()  # Mark progress after PAR2 completes
                # If PAR2 repair failed, corrupted archives are already deleted
                par2_error = not success
        else:
            par2_error = False

        # Process archive files AFTER PAR2 (only if PAR2 didn't delete them)
        # Skip extraction if PAR2 repair failed (archives already deleted as corrupted)
        if not par2_error:
            rar_pattern = re.compile(r'\.r\d{2}$')
            sevenz_pattern = re.compile(r'\.7z(\.\d+)?$')
            archive_files = []

            for file in folder.iterdir():
                if file.is_file():
                    ext_lower = file.suffix.lower()
                    if ext_lower == '.rar' or rar_pattern.match(ext_lower) or ext_lower == '.7z' or sevenz_pattern.match(ext_lower):
                        archive_files.append(file)
            if archive_files:
                # More specific message - show archive count
                self._update_progress(current, total, f"Extract {len(archive_files)} archives: {folder.name[:40]}")
                self.stuck_detector.mark_progress()  # Mark progress before extraction
                if self.dry_run:
                    logging.info(f"[DRY-RUN] Would extract {len(archive_files)} archives in {folder}")
                    success = True
                    archive_error = False
                else:
                    # Pass progress callback to show extraction progress
                    def extraction_progress(idx, total_archives, msg):
                        self._update_progress(current, total, msg)
                        self.stuck_detector.mark_progress()  # Mark progress during extraction

                    success = self.archive_processor.process_rar_files(folder, progress_callback=extraction_progress)
                    if success:
                        self.stats['rars_extracted'] += 1
                    self.stuck_detector.mark_progress()  # Mark progress after extraction
                    # If extraction failed, archives are now junk and should be treated as removable
                    archive_error = not success
            else:
                archive_error = False
        else:
            # PAR2 repair failed - archives already deleted
            archive_error = True
        
        # Process subfolders
        for subfolder in folder.iterdir():
            if subfolder.is_dir():
                self._process_subfolder(subfolder, destination_dir)
        
        # Process video files
        video_files = self.file_handler.find_video_files(folder)

        # Remove sample/preview videos if full version exists
        video_files = self._remove_sample_videos(video_files)

        for idx, video_file in enumerate(video_files, 1):
            # Show folder context and video being validated
            folder_context = f"[{folder.name[:30]}]" if len(folder.name) > 30 else f"[{folder.name}]"
            self._update_progress(current, total, f"{folder_context} Validate {idx}/{len(video_files)}: {video_file.name[:40]}")

            if self.dry_run:
                logging.info(f"[DRY-RUN] Would validate video: {video_file}")
                # In dry-run, simulate success
                logging.info(f"[DRY-RUN] Would move {video_file.name} to {destination_dir}")
                moved_count += 1
                self.stats['videos_moved'] += 1
            else:
                # Get file size BEFORE moving (after move, file no longer at original path)
                try:
                    file_size_mb = video_file.stat().st_size / (1024 * 1024)
                except:
                    file_size_mb = 0

                if self.video_processor.check_video_health(video_file):
                    self.stats['videos_healthy'] += 1
                    if self.file_handler.move_file(video_file, destination_dir):
                        moved_count += 1
                        self.stats['videos_moved'] += 1
                        # Log success so user knows videos are being moved
                        logging.info(f"MOVED: {video_file.name} ({file_size_mb:.1f}MB) -> {destination_dir}")
                else:
                    # Delete corrupt video
                    self.stats['videos_corrupt'] += 1
                    self.stats['videos_failed'] += 1
                    logging.info(f"Deleting corrupt video: {video_file.name}")
                    if self.file_handler.wait_for_file_release(str(video_file)):
                        self.file_handler.delete_video_file_with_retry(video_file)
        
        # Clean up folder if possible
        if self.file_handler.is_folder_empty_or_removable(folder, par2_error, archive_error):
            if self.dry_run:
                logging.info(f"[DRY-RUN] Would delete folder: {folder}")
                self.stats['folders_deleted'] += 1
            else:
                if self.file_handler.safe_delete_folder(folder):
                    self.stats['folders_deleted'] += 1
                else:
                    # Track failed deletion for retry
                    self.failed_deletions.append((folder, par2_error, archive_error))
                    logging.warning(f"Failed to delete folder {folder}, will retry later")
        
        self.stats['folders_processed'] += 1
        return moved_count
    
    def _start_spinner_thread(self):
        """Start background thread to animate spinner."""
        if not self.spinner_running:
            self.spinner_running = True
            self.spinner_thread = threading.Thread(target=self._spinner_loop, daemon=True)
            self.spinner_thread.start()

    def _stop_spinner_thread(self):
        """Stop background spinner thread."""
        self.spinner_running = False
        if self.spinner_thread:
            self.spinner_thread.join(timeout=1.0)

    def _load_comments(self):
        """Load snarky comments from JSON file."""
        try:
            comments_file = Path(__file__).parent / 'config_files' / 'comments.json'
            if comments_file.exists():
                with open(comments_file, 'r') as f:
                    data = json.load(f)
                    return data.get('comments', [])
        except Exception as e:
            logging.debug(f"Could not load comments: {e}")
        return []

    def _get_random_comment(self, current_folder: int):
        """
        Randomly return a snarky comment (15% chance per folder).

        Args:
            current_folder: Current folder number being processed

        Returns:
            Comment string or None
        """
        # Don't show comment if we just showed one recently (within 5 folders)
        if current_folder - self.last_comment_folder < 5:
            return None

        # 15% chance to show a comment (increased for better user experience)
        if self.comments and random.random() < 0.15:
            self.last_comment_folder = current_folder
            return random.choice(self.comments)

        return None

    def _spinner_loop(self):
        """Background thread - updates spinner every second."""
        while self.spinner_running:
            time.sleep(1.0)  # Update once per second
            if self.spinner_running:  # Check again after sleep
                with self.spinner_lock:
                    # Just update the spinner character in-place
                    spinner = self.spinner_frames[self.spinner_index]
                    self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
                    # Move to line 12, column 3 (spinner line) and update just that character
                    sys.stdout.write(f'\033[12;3H{Fore.GREEN}{spinner}{Style.RESET_ALL}')
                    sys.stdout.flush()

    def _update_progress(self, current: int, total: int, action: str):
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
            if current > 0 and elapsed >= 1.0:
                avg_time = elapsed / current
                remaining = (total - current) * avg_time
                eta = str(timedelta(seconds=int(remaining))).split('.')[0]
                throughput = (current / elapsed) * 60
            else:
                eta = "..."
                throughput = 0.0
        else:
            eta = "..."
            throughput = 0.0

        # Progress bar - modern block characters
        bar_length = 40
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)

        # Stats - compact but clear, show interesting work being done
        videos_found = self.stats['videos_healthy'] + self.stats['videos_corrupt'] + self.stats['videos_sample']
        videos_moved = self.stats['videos_moved']
        bad_videos = self.stats['videos_corrupt'] + self.stats['videos_sample']

        # Core stats: found vs moved (success rate at a glance)
        stats_line = f"  {Style.DIM}found:{Style.RESET_ALL} {Fore.WHITE}{videos_found}{Style.RESET_ALL}  {Style.DIM}moved:{Style.RESET_ALL} {Fore.GREEN}{videos_moved}{Style.RESET_ALL}"

        # Show bad videos removed
        if bad_videos > 0:
            stats_line += f"  {Style.DIM}bad:{Style.RESET_ALL} {Fore.RED}{bad_videos}{Style.RESET_ALL}"

        # Show work done: extraction, repair, cleanup
        if self.stats['rars_extracted'] > 0:
            stats_line += f"  {Style.DIM}extracted:{Style.RESET_ALL} {Fore.CYAN}{self.stats['rars_extracted']}{Style.RESET_ALL}"

        if self.stats['par2s_repaired'] > 0:
            stats_line += f"  {Style.DIM}repaired:{Style.RESET_ALL} {Fore.MAGENTA}{self.stats['par2s_repaired']}{Style.RESET_ALL}"

        # Show cleanup progress
        if self.stats['folders_deleted'] > 0:
            stats_line += f"  {Style.DIM}cleaned:{Style.RESET_ALL} {Fore.YELLOW}{self.stats['folders_deleted']}{Style.RESET_ALL}"

        if self.stats['junk_files_deleted'] > 0:
            stats_line += f"  {Style.DIM}junk:{Style.RESET_ALL} {Fore.YELLOW}{self.stats['junk_files_deleted']}{Style.RESET_ALL}"

        # Clear screen and redraw on first update only
        if self.first_progress_update:
            self.first_progress_update = False
            sys.stdout.write('\033[2J\033[H')  # Clear and home

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
            sys.stdout.write('\033[7;1H')  # Move to line 7, column 1

        # Progress bar
        sys.stdout.write(f"  {Style.DIM}[{Style.RESET_ALL}{Fore.GREEN}{bar}{Style.DIM}]{Style.RESET_ALL} {Fore.WHITE}{percent}%{Style.RESET_ALL} {Style.DIM}│{Style.RESET_ALL} {Fore.WHITE}{current}{Style.RESET_ALL}{Style.DIM}/{total}{Style.RESET_ALL}\033[K\n")

        # Stats
        sys.stdout.write(f"{stats_line}\033[K\n")

        # Time metrics with time saved estimate
        # Conservative estimate for manual processing per folder:
        # - Open folder, check PAR2: 30s
        # - Wait for 7z extraction: 1-2 min (depends on size)
        # - Find video in subfolders: 20s
        # - Open video to verify quality: 30s
        # - Move to destination, organize: 30s
        # - Delete junk, cleanup folder: 30s
        # Total: ~2 min minimum for simple folders, 3-5 min for complex ones with PAR2/archives
        # Using 2 min as conservative baseline (user would likely take longer in practice)
        manual_time_minutes = current * 2  # 2 min per folder conservative estimate
        time_saved_hours = manual_time_minutes / 60

        if time_saved_hours < 1:
            time_saved_str = f"{int(manual_time_minutes)} min"
        else:
            time_saved_str = f"{time_saved_hours:.1f} hrs"

        sys.stdout.write(f"  {Style.DIM}speed:{Style.RESET_ALL} {Fore.CYAN}{throughput:>5.1f}{Style.RESET_ALL} {Style.DIM}folders/min  time left:{Style.RESET_ALL} {Fore.CYAN}{eta}{Style.RESET_ALL}  {Style.DIM}saved:{Style.RESET_ALL} {Fore.MAGENTA}{time_saved_str}{Style.RESET_ALL}\033[K\n")
        sys.stdout.write("\n")

        # Current action (line 11) - shows what's happening (with occasional easter egg)
        comment = self._get_random_comment(current)
        if comment:
            # Show snarky comment instead of action (easter egg!)
            sys.stdout.write(f"  {Style.DIM}>{Style.RESET_ALL} {Fore.YELLOW}{comment[:75]}{Style.RESET_ALL}\033[K\n")
        else:
            sys.stdout.write(f"  {Style.DIM}>{Style.RESET_ALL} {action[:80]:<80}\033[K\n")

        # Spinner line (line 12) - animates continuously
        sys.stdout.write(f"  {Fore.GREEN}{spinner}{Style.RESET_ALL} {Style.DIM}working{Style.RESET_ALL}\033[K")

        sys.stdout.flush()
    
    def _process_subfolder(self, subfolder: Path, destination_dir: Path):
        """
        Recursively process subfolder, including archive extraction.

        Args:
            subfolder: Path to subfolder
            destination_dir: Destination for video files
        """
        # Safety: prevent infinite recursion
        if not self.recursion_guard.enter():
            logging.error(f"[SAFETY] Max recursion depth reached at {subfolder}")
            self.stats['safety_stops'] += 1
            return

        try:
            # Process PAR2 files FIRST in this subfolder
            par2_files = [f for f in subfolder.iterdir() if f.is_file() and f.suffix.lower() == '.par2']
            par2_error = False
            if par2_files:
                logging.info(f"Verifying/repairing PAR2 in subfolder {subfolder.name}")
                if self.dry_run:
                    logging.info(f"[DRY-RUN] Would verify/repair {len(par2_files)} PAR2 files in {subfolder}")
                    success = True
                    par2_error = False
                else:
                    success = self.archive_processor.process_par2_files(subfolder)
                    if success:
                        self.stats['par2s_repaired'] += 1
                    par2_error = not success

            # Process archives AFTER PAR2 in this subfolder (only if PAR2 didn't delete them)
            if not par2_error:
                rar_pattern = re.compile(r'\.r\d{2}$')
                sevenz_pattern = re.compile(r'\.7z(\.\d+)?$')
                archive_files = []

                for file in subfolder.iterdir():
                    if file.is_file():
                        ext_lower = file.suffix.lower()
                        if ext_lower == '.rar' or rar_pattern.match(ext_lower) or ext_lower == '.7z' or sevenz_pattern.match(ext_lower):
                            archive_files.append(file)

                archive_error = False
                if archive_files:
                    logging.info(f"Extracting {len(archive_files)} archives in subfolder {subfolder.name}")
                    if self.dry_run:
                        logging.info(f"[DRY-RUN] Would extract {len(archive_files)} archives in {subfolder}")
                        success = True
                        archive_error = False
                    else:
                        # Extraction progress is logged but no progress bar in subfolders
                        success = self.archive_processor.process_rar_files(subfolder)
                        if success:
                            self.stats['rars_extracted'] += 1
                        archive_error = not success
            else:
                # PAR2 repair failed - archives already deleted
                archive_error = True

            # Find and process videos in this subfolder
            video_files = self.file_handler.find_video_files(subfolder)
            for video_file in video_files:
                if self.dry_run:
                    logging.info(f"[DRY-RUN] Would validate and move video: {video_file.name}")
                    self.stats['videos_moved'] += 1
                else:
                    # Get file size BEFORE moving (after move, file no longer at original path)
                    try:
                        file_size_mb = video_file.stat().st_size / (1024 * 1024)
                    except:
                        file_size_mb = 0

                    if self.video_processor.check_video_health(video_file):
                        self.stats['videos_healthy'] += 1
                        if self.file_handler.move_file(video_file, destination_dir):
                            self.stats['videos_moved'] += 1
                            # Log success so user knows videos are being moved
                            logging.info(f"MOVED: {video_file.name} ({file_size_mb:.1f}MB) -> {destination_dir}")
                    else:
                        # Delete corrupt video
                        self.stats['videos_corrupt'] += 1
                        self.stats['videos_failed'] += 1
                        logging.info(f"Deleting corrupt video: {video_file.name}")
                        if self.file_handler.wait_for_file_release(str(video_file)):
                            self.file_handler.delete_video_file_with_retry(video_file)

            # Recursively process nested subfolders
            for sub in subfolder.iterdir():
                if sub.is_dir():
                    self._process_subfolder(sub, destination_dir)

            # Check if subfolder can be deleted
            if self.file_handler.is_folder_empty_or_removable(subfolder, par2_error, archive_error):
                if self.dry_run:
                    logging.info(f"[DRY-RUN] Would delete subfolder: {subfolder}")
                else:
                    if not self.file_handler.safe_delete_folder(subfolder):
                        # Track failed deletion for retry
                        self.failed_deletions.append((subfolder, par2_error, archive_error))
                        logging.warning(f"Failed to delete subfolder {subfolder}, will retry later")
        finally:
            self.recursion_guard.exit()
    
    def run(self, source_dir: Path, destination_dir: Path):
        """
        Run the main processing loop.
        
        Args:
            source_dir: Source directory to process
            destination_dir: Destination for video files
        """
        # Get video folders from work plan
        if not self.work_plan:
            print(Fore.RED + "No work plan available. Run scan_and_plan() first." + Style.RESET_ALL)
            return

        video_folders = [item['path'] for item in self.work_plan.video_folders]

        if not video_folders:
            print(Fore.YELLOW + "No video folders found to process." + Style.RESET_ALL)
            return

        # Track preserved folders
        self.stats['folders_preserved'] = len(self.work_plan.content_folders)

        self.start_time = time.time()
        total = len(video_folders)

        # Safety: Initialize runtime limit from config
        from utils.safety import OperationTimer
        max_runtime_seconds = self.config.max_runtime_hours * 3600
        self.runtime_limit = OperationTimer(max_runtime_seconds, "Total Unpackr Runtime")

        # Safety: loop guard for folder processing
        loop_guard = LoopSafety(self.config.max_videos_per_folder * 2, "Folder processing loop")

        try:
            for i, folder in enumerate(video_folders, 1):
                # Safety checks
                if not loop_guard.tick():
                    logging.error("[SAFETY] Folder processing loop exceeded safety limit")
                    self.stats['safety_stops'] += 1
                    break

                if not self.runtime_limit.check():
                    logging.error(f"[SAFETY] Runtime limit exceeded ({self.config.max_runtime_hours} hours) - stopping")
                    self.stats['safety_stops'] += 1
                    break
                
                if not self.stuck_detector.check():
                    logging.error("[SAFETY] Process appears stuck - stopping")
                    self.stats['safety_stops'] += 1
                    break
                
                # Process folder
                self.process_folder(folder, destination_dir, i, total)

                # Mark progress for stuck detection
                self.stuck_detector.mark_progress()

            # Process loose videos
            if self.work_plan.loose_videos:
                for video in self.work_plan.loose_videos:
                    try:
                        if self.dry_run:
                            logging.info(f"[DRY-RUN] Would validate and move loose video: {video.name}")
                            self.stats['videos_moved'] += 1
                        else:
                            # Validate video using video_processor (not undefined video_validator)
                            if self.video_processor and self.video_processor.check_video_health(video):
                                self.stats['videos_healthy'] += 1
                                # Move to destination
                                dest_file = destination_dir / video.name
                                if not dest_file.exists():
                                    video.rename(dest_file)
                                    self.stats['videos_moved'] += 1
                                    logging.info(f"Moved loose video: {video.name}")
                            else:
                                self.stats['videos_corrupt'] += 1
                                self.stats['videos_failed'] += 1
                                logging.warning(f"Loose video failed validation: {video.name}")
                                video.unlink()  # Delete corrupt video
                    except Exception as e:
                        logging.error(f"Error processing loose video {video}: {e}")

        finally:
            # Stop spinner thread
            self._stop_spinner_thread()
            # Clear progress line
            sys.stdout.write('\r' + ' '*100 + '\r')
            sys.stdout.flush()

    def retry_failed_deletions(self, max_passes: int = 3, wait_seconds: int = 30):
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
            remaining = []
            for folder, par2_error, archive_error in self.failed_deletions:
                # Check if folder still exists and is still removable
                if not folder.exists():
                    logging.info(f"Folder already gone: {folder}")
                    continue

                if not self.file_handler.is_folder_empty_or_removable(folder, par2_error, archive_error):
                    logging.info(f"Folder no longer removable: {folder}")
                    continue

                # Try to delete
                if self.file_handler.safe_delete_folder(folder):
                    self.stats['folders_deleted'] += 1
                    logging.info(f"Successfully deleted on retry: {folder}")
                else:
                    remaining.append((folder, par2_error, archive_error))

            self.failed_deletions = remaining

        if self.failed_deletions:
            print(f"{Fore.RED}Warning: {len(self.failed_deletions)} folders could not be deleted{Style.RESET_ALL}")
            for folder, _, _ in self.failed_deletions:
                logging.warning(f"Permanent deletion failure: {folder}")

    def cleanup_empty_folders(self, source_dir: Path):
        """Final cleanup pass to delete remaining empty folders - recursive, multi-pass."""
        logging.info("Starting final cleanup of empty folders (recursive, multi-pass)")
        total_deleted = 0
        max_passes = 5  # Keep trying until nothing left to delete

        for pass_num in range(1, max_passes + 1):
            pass_deleted = 0

            try:
                # RECURSIVE: Walk through all directories bottom-up
                # This deletes deepest folders first, then parents
                for root, dirs, files in os.walk(source_dir, topdown=False):
                    for dir_name in dirs:
                        folder = Path(root) / dir_name

                        try:
                            # Check if folder is empty
                            if not any(folder.iterdir()):
                                if self.file_handler.safe_delete_folder(folder):
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

            # If nothing deleted this pass, we're done
            if pass_deleted == 0:
                logging.info(f"Cleanup complete after {pass_num} passes")
                break
            else:
                logging.info(f"Pass {pass_num}: Deleted {pass_deleted} empty folders")

        if total_deleted > 0:
            self.stats['empty_folders_deleted'] = total_deleted
            print(f"{Fore.GREEN}Cleaned up {total_deleted} empty folders{Style.RESET_ALL}")
            logging.info(f"Final cleanup: deleted {total_deleted} empty folders total")

    def display_summary(self):
        """Display processing summary with detailed stats."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        elapsed_str = str(timedelta(seconds=int(elapsed))).split('.')[0]

        # Clear screen and show final summary
        sys.stdout.write('\033[2J\033[H')

        total_cleaned = self.stats['folders_deleted'] + self.stats['empty_folders_deleted']

        print(f"""
  {Style.DIM}_   _ _ __  _ __   __ _  ___| | ___ __
 | | | | '_ \\| '_ \\ / _` |/ __| |/ / '__|
 | |_| | | | | |_) | (_| | (__|   <| |
  \\__,_|_| |_| .__/ \\__,_|\\___|_|\\_\\_|
             |_|{Style.RESET_ALL}

  {Fore.GREEN}[COMPLETE]{Style.RESET_ALL} {Style.DIM}runtime:{Style.RESET_ALL} {Fore.CYAN}{elapsed_str}{Style.RESET_ALL}

  {Fore.GREEN}▓▓{Style.RESET_ALL} {Style.DIM}FOLDERS{Style.RESET_ALL}
     {Style.DIM}processed....{Style.RESET_ALL} {Fore.WHITE}{self.stats['folders_processed']:>4}{Style.RESET_ALL}
     {Style.DIM}deleted......{Style.RESET_ALL} {Fore.GREEN}{self.stats['folders_deleted']:>4}{Style.RESET_ALL}
     {Style.DIM}empty........{Style.RESET_ALL} {Fore.CYAN}{self.stats['empty_folders_deleted']:>4}{Style.RESET_ALL}
     {Style.DIM}preserved....{Style.RESET_ALL} {Fore.MAGENTA}{self.stats['folders_preserved']:>4}{Style.RESET_ALL}
     {Fore.GREEN}total cleaned: {total_cleaned}{Style.RESET_ALL}

  {Fore.GREEN}▓▓{Style.RESET_ALL} {Style.DIM}VIDEOS{Style.RESET_ALL}
     {Style.DIM}moved (ok)...{Style.RESET_ALL} {Fore.GREEN}{self.stats['videos_moved']:>4}{Style.RESET_ALL}
     {Style.DIM}samples......{Style.RESET_ALL} {Fore.YELLOW}{self.stats['videos_sample']:>4}{Style.RESET_ALL} {Style.DIM}dropped{Style.RESET_ALL}
     {Style.DIM}corrupt......{Style.RESET_ALL} {Fore.RED}{self.stats['videos_corrupt']:>4}{Style.RESET_ALL} {Style.DIM}dropped{Style.RESET_ALL}
     {Style.DIM}failed.......{Style.RESET_ALL} {Fore.RED}{self.stats['videos_failed']:>4}{Style.RESET_ALL}

  {Fore.GREEN}▓▓{Style.RESET_ALL} {Style.DIM}ARCHIVES{Style.RESET_ALL}
     {Style.DIM}extracted....{Style.RESET_ALL} {Fore.CYAN}{self.stats['rars_extracted']:>4}{Style.RESET_ALL}
     {Style.DIM}repaired.....{Style.RESET_ALL} {Fore.MAGENTA}{self.stats['par2s_repaired']:>4}{Style.RESET_ALL}
""")

        if self.stats['files_sanitized'] > 0:
            print(f"  {Fore.GREEN}▓▓{Style.RESET_ALL} {Style.DIM}FILES{Style.RESET_ALL}")
            print(f"     {Style.DIM}sanitized....{Style.RESET_ALL} {Fore.CYAN}{self.stats['files_sanitized']:>4}{Style.RESET_ALL}\n")

        if self.stats['safety_stops'] > 0:
            print(f"  {Fore.RED}[!] SAFETY STOPS: {self.stats['safety_stops']}{Style.RESET_ALL}\n")

        if self.failed_deletions:
            print(f"  {Fore.YELLOW}[!] locked folders: {len(self.failed_deletions)}{Style.RESET_ALL}\n")


def clean_path(path_str: str) -> str:
    """
    Clean path string by removing quotes and extra whitespace.
    
    Args:
        path_str: Raw path string
        
    Returns:
        Cleaned path string
    """
    cleaned = path_str.strip()
    # Remove surrounding quotes (single or double)
    if (cleaned.startswith('"') and cleaned.endswith('"')) or \
       (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def get_user_input(prompt: str) -> Path:
    """
    Prompt user for directory path with validation.
    
    Args:
        prompt: Prompt message
        
    Returns:
        Valid directory path
    """
    while True:
        user_input = input(prompt).strip()
        cleaned = clean_path(user_input)
        path = Path(cleaned)
        
        if path.is_dir():
            return path
        else:
            print(Fore.RED + f"Invalid path. Please enter a valid directory path." + Style.RESET_ALL)
            if user_input != cleaned:
                print(Fore.YELLOW + f"Tip: Path was cleaned to: {cleaned}" + Style.RESET_ALL)


def quick_preflight(config, source_dir, destination_dir) -> bool:
    """
    Quick pre-flight check before processing starts.
    Silent if everything is OK - only shows output if issues found.

    Args:
        config: Config object
        source_dir: Source directory path
        destination_dir: Destination directory path

    Returns:
        True if checks pass, False if critical issues
    """
    warnings = []

    # Check 1: Disk space (quick but important)
    try:
        import shutil
        total, used, free = shutil.disk_usage(destination_dir)
        free_gb = free // (2**30)
        if free_gb < 5:
            warnings.append(f"Very low disk space: {free_gb}GB available (may run out)")
        elif free_gb < 10:
            warnings.append(f"Low disk space: {free_gb}GB available")
    except:
        pass

    # Check 2: Source has content to process
    try:
        dir_list = list(source_dir.iterdir())
        if not dir_list:
            warnings.append("Source directory is empty - nothing to process")
    except Exception as e:
        warnings.append(f"Cannot read source directory: {e}")

    # Display warnings only if there are any
    if warnings:
        print(f"\n{Fore.YELLOW}Pre-flight Check:{Style.RESET_ALL}")
        for w in warnings:
            print(f"  {Fore.YELLOW}⚠{Style.RESET_ALL} {w}")

        print(f"\n{Style.DIM}Continue anyway? (Enter to proceed, Ctrl+C to abort){Style.RESET_ALL}")
        try:
            input()
        except KeyboardInterrupt:
            print(Fore.RED + "\nAborted by user." + Style.RESET_ALL)
            return False

    return True


def countdown_prompt(seconds: int = 10) -> bool:
    """
    Display countdown before starting.

    Args:
        seconds: Countdown duration

    Returns:
        True if user didn't cancel, False if cancelled
    """
    try:
        for i in range(seconds, 0, -1):
            sys.stdout.write(f"\r{Fore.GREEN}Starting in {i} seconds... "
                           f"(Press Ctrl+C to cancel) {Style.RESET_ALL}")
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\r" + " " * 60 + "\r")
        return True
    except KeyboardInterrupt:
        print(Fore.RED + "\n\nOperation cancelled by user." + Style.RESET_ALL)
        return False


def main():
    """Main entry point with defensive error handling."""
    init()  # Initialize colorama
    
    print(Fore.YELLOW + ASCII_ART + Style.RESET_ALL)
    
    try:
        # Parse arguments
        parser = argparse.ArgumentParser(
            description="Automated video file processing and cleanup tool.",
            epilog="Examples:\n"
                   "  unpackr --source C:\\Downloads --destination D:\\Videos\n"
                   "  unpackr C:\\Downloads D:\\Videos\n"
                   "  unpackr  (interactive mode)",
            formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('source_pos', nargs='?', help='Source downloads directory (positional)')
        parser.add_argument('dest_pos', nargs='?', help='Destination directory (positional)')
        parser.add_argument('--source', '-s', help='Path to source downloads directory')
        parser.add_argument('--destination', '-d', help='Path to destination directory')
        parser.add_argument('--config', '-c', help='Path to config.json file')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
        parser.add_argument('--show-plan', action='store_true', help='Show detailed pre-flight plan and exit (no processing)')
        args = parser.parse_args()

        # Handle positional vs named arguments
        if args.source_pos:
            args.source = args.source_pos
        if args.dest_pos:
            args.destination = args.dest_pos
        
        # Load configuration defensively
        config_path = Path(args.config) if args.config else Path('config_files/config.json')
        
        try:
            config = Config(config_path if config_path.exists() else None)
        except Exception as e:
            print(Fore.RED + f"Error loading config: {e}" + Style.RESET_ALL)
            logging.error(f"Config load failed: {e}", exc_info=True)
            sys.exit(1)
        
        # Set up logging
        try:
            log_file = setup_logging(config.log_folder, config.max_log_files)
            logging.info("="*70)
            logging.info("Unpackr started")
            logging.info(f"Log file: {log_file}")
        except Exception as e:
            print(Fore.RED + f"Error setting up logging: {e}" + Style.RESET_ALL)
            sys.exit(1)
        
        # Get and validate source and destination paths
        if args.source and args.destination:
            # Clean and validate paths defensively
            try:
                source_str = clean_path(args.source)
                dest_str = clean_path(args.destination)
                
                source_dir = InputValidator.validate_path(source_str, must_exist=True, must_be_dir=True)
                destination_dir = InputValidator.validate_path(dest_str, must_exist=True, must_be_dir=True)
                
            except ValidationError as e:
                print(Fore.RED + f"Path validation failed: {e}" + Style.RESET_ALL)
                logging.error(f"Path validation: {e}")
                sys.exit(1)
                
        else:
            # Interactive mode - get paths from user
            print(Style.BRIGHT + Fore.YELLOW + 
                  "This script requires par2cmdline and 7-Zip installed and available in PATH." + 
                  Style.RESET_ALL)
            print(Fore.CYAN + "\nEnter paths with or without quotes." + Style.RESET_ALL)
            source_dir = get_user_input("\nEnter the path to your downloads directory: ")
            destination_dir = get_user_input("Enter the path to your destination directory: ")
        
        # Defensive: Additional checks on paths
        if not StateValidator.check_dir_writable(destination_dir):
            print(Fore.RED + f"Destination directory is not writable: {destination_dir}" + Style.RESET_ALL)
            logging.error(f"Destination not writable: {destination_dir}")
            sys.exit(1)
        
        if not StateValidator.check_disk_space(destination_dir, required_mb=1000):
            print(Fore.YELLOW + f"Warning: Low disk space in destination directory" + Style.RESET_ALL)
            logging.warning("Low disk space warning")
    
        # Check system requirements
        print(f"[TOOLS] Checking requirements...", end=" ")
        system_check = SystemCheck(config)
        tools_status = system_check.check_all_tools()
        if not system_check.display_tool_status(tools_status):
            logging.error("Required tools missing")
            sys.exit(1)

        # Check for running processes from previous session
        if not system_check.warn_running_processes():
            sys.exit(0)

        # Create app and scan first
        try:
            app = UnpackrApp(config)
            app.dry_run = args.dry_run
            if args.dry_run:
                print(f"{Fore.YELLOW}[DRY-RUN MODE] No files will be modified{Style.RESET_ALL}")
                logging.info("Dry-run mode enabled - no modifications will be made")
        except Exception as e:
            print(Fore.RED + f"Error initializing application: {e}" + Style.RESET_ALL)
            logging.error(f"App init failed: {e}", exc_info=True)
            sys.exit(1)
        
        # Scan and plan
        try:
            work_plan = app.scan_and_plan(source_dir)
        except Exception as e:
            print(Fore.RED + f"Error during scan: {e}" + Style.RESET_ALL)
            logging.error(f"Scan failed: {e}", exc_info=True)
            sys.exit(1)

        # If --show-plan, display detailed plan and exit
        if args.show_plan:
            work_plan.display_detailed()
            print(f"{Fore.CYAN}Source: {source_dir}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Destination: {destination_dir}{Style.RESET_ALL}")
            print(f"\n{Fore.GREEN}Pre-flight check complete. No changes made.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Run without --show-plan to execute.{Style.RESET_ALL}\n")
            sys.exit(0)

        # Display work plan (compact single line)
        work_plan.display()

        # Display confirmation (compact)
        print(f"[INFO] Source: {Fore.CYAN}{source_dir}{Style.RESET_ALL} -> Dest: {Fore.CYAN}{destination_dir}{Style.RESET_ALL}")
        print(f"[WARN] {Fore.RED}Processed folders will be DELETED{Style.RESET_ALL} | Log: {log_file.name}")

        # Quick pre-flight check before countdown
        if not quick_preflight(config, source_dir, destination_dir):
            logging.error("Pre-flight check failed")
            sys.exit(1)

        if not countdown_prompt(10):
            logging.info("User cancelled operation")
            sys.exit(0)

        # Initial cleanup: delete empty folders first for quick wins
        print()  # Blank line before progress
        print(f"{Fore.CYAN}[CLEANUP] Scanning for empty folders...{Style.RESET_ALL}")
        try:
            app.cleanup_empty_folders(source_dir)
        except Exception as e:
            logging.error(f"Initial cleanup failed: {e}", exc_info=True)
            print(f"{Fore.YELLOW}Warning: Initial cleanup had errors (continuing anyway){Style.RESET_ALL}")

        # Run the application
        print()  # Blank line before progress
        try:
            app.run(source_dir, destination_dir)

            # Multi-pass cleanup for locked folders
            app.retry_failed_deletions()

            # Final cleanup of empty folders
            app.cleanup_empty_folders(source_dir)

            app.display_summary()
            logging.info("Unpackr completed successfully")
        except Exception as e:
            print(Fore.RED + f"\nFatal error during processing: {e}" + Style.RESET_ALL)
            logging.error(f"Processing failed: {e}", exc_info=True)
            app.display_summary()  # Show what we accomplished
            sys.exit(1)
    
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\nOperation interrupted by user" + Style.RESET_ALL)
        logging.info("User interrupted operation")
        sys.exit(0)
    except Exception as e:
        print(Fore.RED + f"\nUnexpected error: {e}" + Style.RESET_ALL)
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
