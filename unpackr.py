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
        
    def add_content_folder(self, folder: Path):
        """Add a content folder to keep."""
        self.content_folders.append(folder)
        
    def add_loose_video(self, video: Path):
        """Add a loose video file."""
        self.loose_videos.append(video)
        self.total_videos += 1
        
    def calculate_time_estimate(self):
        """Calculate estimated processing time."""
        # Rough estimates:
        # - 5 seconds per video check
        # - 10 seconds per RAR extraction
        # - 15 seconds per PAR2 repair
        # - 2 seconds per folder operation
        
        time_estimate = 0
        time_estimate += self.total_videos * 5  # Video health checks
        time_estimate += self.total_rars * 10   # RAR extractions
        time_estimate += self.total_par2s * 15  # PAR2 repairs
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


class UnpackrApp:
    """Main application class for Unpackr."""
    
    def __init__(self, config: Config):
        """
        Initialize the application.
        
        Args:
            config: Configuration instance
        """
        self.config = config
        self.file_handler = FileHandler(config)
        self.archive_processor = ArchiveProcessor(config)
        self.video_processor = VideoProcessor(config)
        self.stats = {
            'folders_processed': 0,
            'videos_moved': 0,
            'videos_failed': 0,
            'folders_deleted': 0,
            'rars_extracted': 0,
            'par2s_repaired': 0,
            'safety_stops': 0
        }
        self.start_time = None
        self.work_plan = None
        self.recursion_guard = RecursionSafety(SafetyLimits.MAX_SUBFOLDERS_DEPTH, "Subfolder processing")
        self.stuck_detector = StuckDetector(timeout=300, check_interval=30)  # 5min without progress
        
    def scan_and_plan(self, source_dir: Path) -> WorkPlan:
        """
        Scan source directory and create a work plan.
        
        Args:
            source_dir: Source directory to scan
            
        Returns:
            WorkPlan instance
        """
        plan = WorkPlan()
        folders = [f for f in source_dir.iterdir() if f.is_dir()]
        
        # Show progress during scan
        for i, folder in enumerate(folders, 1):
            sys.stdout.write(f"\r[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
            sys.stdout.flush()
            
            # Count videos, RARs, PAR2s
            videos = list(folder.glob('*.mp4')) + list(folder.glob('*.avi')) + \
                    list(folder.glob('*.mkv')) + list(folder.glob('*.mov'))
            rars = list(folder.glob('*.rar')) + list(folder.glob('*.r[0-9][0-9]'))
            par2s = list(folder.glob('*.par2'))
            
            if videos or rars:
                # This is a video folder
                plan.add_video_folder(folder, len(videos), len(rars), len(par2s))
            else:
                # This is a content folder (music, docs, etc.)
                plan.add_content_folder(folder)
        
        # Check for loose video files
        for ext in ['.mp4', '.avi', '.mkv', '.mov']:
            for video in source_dir.glob(f'*{ext}'):
                if video.is_file():
                    plan.add_loose_video(video)
        
        sys.stdout.write("\r" + " "*80 + "\r")
        
        plan.calculate_time_estimate()
        self.work_plan = plan
        return plan
    
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
        moved_count = 0
        
        # Update progress header
        self._update_progress(current, total, f"Processing: {folder.name[:40]}")
        
        # Process RAR files first
        rar_files = list(folder.glob('*.rar'))
        if rar_files:
            self._update_progress(current, total, f"Extracting RAR: {folder.name[:40]}")
            if self.archive_processor.process_rar_files(folder):
                self.stats['rars_extracted'] += 1
            rar_error = False
        else:
            rar_error = False
        
        # Process PAR2 files
        par2_files = list(folder.glob('*.par2'))
        if par2_files:
            self._update_progress(current, total, f"Repairing PAR2: {folder.name[:40]}")
            if self.archive_processor.process_par2_files(folder):
                self.stats['par2s_repaired'] += 1
            par2_error = False
        else:
            par2_error = False
        
        # Process subfolders
        for subfolder in folder.iterdir():
            if subfolder.is_dir():
                self._process_subfolder(subfolder, destination_dir)
        
        # Process video files
        video_files = self.file_handler.find_video_files(folder)
        
        for video_file in video_files:
            self._update_progress(current, total, f"Checking video: {video_file.name[:35]}")
            
            if self.video_processor.check_video_health(video_file):
                if self.file_handler.move_file(video_file, destination_dir):
                    moved_count += 1
                    self.stats['videos_moved'] += 1
            else:
                # Delete corrupt video
                self.stats['videos_failed'] += 1
                if self.file_handler.wait_for_file_release(str(video_file)):
                    self.file_handler.delete_video_file_with_retry(video_file)
        
        # Clean up folder if possible
        if self.file_handler.is_folder_empty_or_removable(folder, par2_error, rar_error):
            self.file_handler.safe_delete_folder(folder)
            self.stats['folders_deleted'] += 1
        
        self.stats['folders_processed'] += 1
        return moved_count
    
    def _update_progress(self, current: int, total: int, action: str):
        """
        Update progress display.
        
        Args:
            current: Current item number
            total: Total items
            action: Current action description
        """
        # Calculate percentage and ETA
        percent = int((current / total) * 100)
        
        if self.start_time:
            elapsed = time.time() - self.start_time
            if current > 0:
                avg_time = elapsed / current
                remaining = (total - current) * avg_time
                eta = str(timedelta(seconds=int(remaining))).split('.')[0]
            else:
                eta = "calculating..."
        else:
            eta = "calculating..."
        
        # Progress bar
        bar_length = 30
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        # Clear line and print
        sys.stdout.write('\r' + ' '*100 + '\r')
        progress_line = (f"{Fore.CYAN}[{bar}] {percent}%{Style.RESET_ALL} | "
                        f"{Fore.YELLOW}{current}/{total}{Style.RESET_ALL} | "
                        f"ETA: {Fore.GREEN}{eta}{Style.RESET_ALL} | "
                        f"{action[:40]}")
        sys.stdout.write(progress_line)
        sys.stdout.flush()
    
    def _process_subfolder(self, subfolder: Path, destination_dir: Path):
        """
        Recursively process subfolder.
        
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
            for sub in subfolder.iterdir():
                if sub.is_dir():
                    self._process_subfolder(sub, destination_dir)
            
            # Check if subfolder can be deleted
            if self.file_handler.is_folder_empty_or_removable(subfolder, False, False):
                self.file_handler.safe_delete_folder(subfolder)
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
        
        self.start_time = time.time()
        total = len(video_folders)
        
        # Safety: loop guard for folder processing
        loop_guard = LoopSafety(SafetyLimits.MAX_VIDEOS_PER_FOLDER * 2, "Folder processing loop")
        
        try:
            for i, folder in enumerate(video_folders, 1):
                # Safety checks
                if not loop_guard.tick():
                    logging.error("[SAFETY] Folder processing loop exceeded safety limit")
                    self.stats['safety_stops'] += 1
                    break
                
                if not GLOBAL_RUNTIME_LIMIT.check():
                    logging.error("[SAFETY] Global runtime limit exceeded - stopping")
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
        
        finally:
            # Clear progress line
            sys.stdout.write('\r' + ' '*100 + '\r')
            sys.stdout.flush()
    
    def display_summary(self):
        """Display processing summary."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        elapsed_str = str(timedelta(seconds=int(elapsed))).split('.')[0]
        
        summary = (f"\n[DONE] Time: {Fore.CYAN}{elapsed_str}{Style.RESET_ALL} | "
              f"Folders: {Fore.GREEN}{self.stats['folders_processed']}{Style.RESET_ALL} processed, "
              f"{Fore.YELLOW}{self.stats['folders_deleted']}{Style.RESET_ALL} deleted | "
              f"Videos: {Fore.GREEN}{self.stats['videos_moved']}{Style.RESET_ALL} moved")
        
        if self.stats['videos_failed'] > 0:
            summary += f", {Fore.RED}{self.stats['videos_failed']}{Style.RESET_ALL} failed"
        if self.stats['rars_extracted'] > 0:
            summary += f" | RARs: {self.stats['rars_extracted']}"
        if self.stats['par2s_repaired'] > 0:
            summary += f" | PAR2s: {self.stats['par2s_repaired']}"
        if self.stats['safety_stops'] > 0:
            summary += f" | {Fore.RED}SAFETY STOPS: {self.stats['safety_stops']}{Style.RESET_ALL}"
        
        print(summary)


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
            description="Automated video file processing and cleanup tool.")
        parser.add_argument('--source', '-s', help='Path to source downloads directory', required=False)
        parser.add_argument('--destination', '-d', help='Path to destination directory', required=False)
        parser.add_argument('--config', '-c', help='Path to config.json file', required=False)
        args = parser.parse_args()
        
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
        
        # Create app and scan first
        try:
            app = UnpackrApp(config)
        except Exception as e:
            print(Fore.RED + f"Error initializing application: {e}" + Style.RESET_ALL)
            logging.error(f"App init failed: {e}", exc_info=True)
            logging.error(f"App init failed: {e}", exc_info=True)
            sys.exit(1)
        
        # Scan and plan
        try:
            work_plan = app.scan_and_plan(source_dir)
        except Exception as e:
            print(Fore.RED + f"Error during scan: {e}" + Style.RESET_ALL)
            logging.error(f"Scan failed: {e}", exc_info=True)
            sys.exit(1)
        
        # Display work plan (compact single line)
        work_plan.display()
        
        # Display confirmation (compact)
        print(f"[INFO] Source: {Fore.CYAN}{source_dir}{Style.RESET_ALL} -> Dest: {Fore.CYAN}{destination_dir}{Style.RESET_ALL}")
        print(f"[WARN] {Fore.RED}Processed folders will be DELETED{Style.RESET_ALL} | Log: {log_file.name}")
        
        if not countdown_prompt(10):
            logging.info("User cancelled operation")
            sys.exit(0)
        
        # Run the application
        print()  # Blank line before progress
        try:
            app.run(source_dir, destination_dir)
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
