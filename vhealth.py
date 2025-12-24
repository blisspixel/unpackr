"""
Video Health Checker - Standalone utility for validating video files.

Usage:
    vhealth "C:\Videos"                    # Check all videos in folder
    vhealth "C:\Videos\movie.mkv"          # Check single file
    vhealth "C:\Videos" --delete-bad       # Auto-delete corrupt/low-quality videos
    vhealth "C:\Videos" --min-resolution 720p  # Flag videos below 720p
"""

import sys
import argparse
import logging
from pathlib import Path
from colorama import init, Fore, Style
from typing import List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core import Config
from core.video_processor import VideoProcessor
from utils.safety import SubprocessSafety

init(autoreset=True)


class VideoHealthChecker:
    """Check video health and quality."""

    def __init__(self, config=None):
        """Initialize the health checker."""
        self.config = config or Config()
        self.video_processor = VideoProcessor(self.config)

        # Results tracking
        self.healthy_videos = []
        self.corrupt_videos = []
        self.sample_videos = []
        self.low_res_videos = []
        self.duplicate_videos = []  # (video, duplicate_of, reason)
        self.potential_duplicates = []  # [(video1, video2, similarity_score)]

    def check_path(self, path: Path, min_resolution: str = None, skip_samples: bool = False, skip_health: bool = False) -> None:
        """
        Check video(s) at given path.

        Args:
            path: File or directory path
            min_resolution: Minimum resolution (e.g., "720p", "1080p")
            skip_samples: Skip sample detection, go straight to health check
            skip_health: Skip health check (only check samples/resolution)
        """
        if path.is_file():
            self._check_video(path, min_resolution, skip_health=skip_health)
        elif path.is_dir():
            video_files = self._find_videos(path)
            print(f"\n{Fore.CYAN}Found {len(video_files)} video files{Style.RESET_ALL}")

            # Quick pre-scan for samples and low-res if not skipping
            delete_bad_now = False
            auto_clean = skip_health  # If --clean flag used, auto-delete without prompting

            if not skip_samples or min_resolution:
                print(f"{Style.DIM}Initial check...{Style.RESET_ALL}\n")

                # Count small files and samples separately
                small_files = []
                sample_name_files = []

                for video in video_files:
                    size_mb = video.stat().st_size / (1024 * 1024)
                    if size_mb < 50:  # Small file
                        small_files.append(video)
                        if 'sample' in video.name.lower():  # Also has "sample" in name
                            sample_name_files.append(video)

                # Check resolution if specified
                if min_resolution:
                    print(f"{Style.DIM}Checking resolution...{Style.RESET_ALL}\n")
                    for video in video_files:
                        if video not in small_files:  # Skip small files
                            resolution = self._get_resolution(video)
                            if resolution and not self._meets_min_resolution(resolution, min_resolution):
                                self.low_res_videos.append((video, resolution))

                # Store results
                self.sample_videos = small_files

                # Show what we found
                total_bad = len(self.sample_videos) + len(self.low_res_videos)
                if total_bad > 0:
                    remaining_count = len(video_files) - total_bad
                    print(f"{Fore.YELLOW}Found:{Style.RESET_ALL}")
                    print(f"  {len(small_files)} small files {Style.DIM}(<50MB){Style.RESET_ALL}")
                    if sample_name_files:
                        print(f"  {len(sample_name_files)} named 'sample'")
                    if self.low_res_videos:
                        print(f"  {len(self.low_res_videos)} low resolution")
                    print(f"  {remaining_count} remaining to check\n")

                    # Auto-delete if --clean flag, otherwise ask
                    if auto_clean:
                        delete_bad_now = True
                        print(f"{Style.DIM}Deleting and continuing health check...{Style.RESET_ALL}\n")
                    else:
                        print(f"Delete these and continue health check? [Y/n]: ", end='')
                        choice = input().strip().lower()

                        if choice in ('', 'y', 'yes'):
                            delete_bad_now = True
                        else:
                            print(f"{Style.DIM}Keeping all files, checking everything...{Style.RESET_ALL}\n")

            # Delete bad files now if requested
            if delete_bad_now:
                bad_files = self.sample_videos + [v for v, _ in self.low_res_videos]
                if bad_files:
                    self._delete_videos(bad_files)
                    print()

            # Now do health checks on remaining videos (if not skipping)
            if not skip_health:
                videos_to_check = [v for v in video_files if not (delete_bad_now and (v in self.sample_videos or any(vv == v for vv, _ in self.low_res_videos)))]

                if not videos_to_check:
                    return

                print(f"{Style.DIM}Checking {len(videos_to_check)} videos...{Style.RESET_ALL}\n")

                # Track problems for display
                problems = []

                for i, video in enumerate(videos_to_check, 1):
                    # Show progress
                    if len(videos_to_check) > 5:
                        print(f"\r{Style.DIM}  {i}/{len(videos_to_check)}{Style.RESET_ALL}", end='', flush=True)

                    # Skip if file no longer exists
                    if not video.exists():
                        continue

                    # Check the video
                    result = self._check_video_silent(video)

                    # Only track problems
                    if result != 'healthy':
                        problems.append((video, result))

                # Clear progress line
                if len(videos_to_check) > 5:
                    print(f"\r{' ' * 20}\r", end='')

                # Show problems found
                if problems:
                    print()
                    for video, status in problems:
                        print(f"{video.name}")
                        print(f"  {status}")
                        print()
                else:
                    print()

            # Duplicate detection (after health checks)
            if not skip_health:
                print(f"{Style.DIM}Checking for duplicates...{Style.RESET_ALL}\n")
                self._detect_duplicates(video_files)
        else:
            print(f"{Fore.RED}Path not found: {path}{Style.RESET_ALL}")

    def _detect_duplicates(self, video_files: List[Path]) -> None:
        """
        Detect duplicate videos using multiple strategies (rock solid):
        1. Exact size + partial hash match (fast, high confidence)
        2. Similar size + duration + hash (thorough, catches re-encodes)
        3. Filename patterns (copy, duplicate, etc.)
        4. Similar names + similar size (potential duplicates)
        """
        import hashlib
        from difflib import SequenceMatcher

        # Filter to only existing, healthy videos
        valid_videos = [v for v in video_files if v.exists() and v not in self.corrupt_videos and v not in self.sample_videos]

        # Strategy 1: Group by exact size, then hash to confirm (FAST)
        size_groups = {}
        for video in valid_videos:
            try:
                size = video.stat().st_size
                if size not in size_groups:
                    size_groups[size] = []
                size_groups[size].append(video)
            except:
                continue

        # Check size groups for duplicates using hash
        for size, videos in size_groups.items():
            if len(videos) > 1:
                # Multiple files with same size - hash first 1MB to confirm
                hashes = {}
                for video in videos:
                    try:
                        with open(video, 'rb') as f:
                            # Hash first 1MB (fast, usually enough)
                            chunk = f.read(1024 * 1024)
                            file_hash = hashlib.md5(chunk).hexdigest()

                            if file_hash in hashes:
                                # Confirmed duplicate (size + hash match)
                                self.duplicate_videos.append((video, hashes[file_hash], "Exact match (size + hash)"))
                            else:
                                hashes[file_hash] = video
                    except:
                        continue

        # Strategy 2: Duration + size similarity (catches re-encodes with different sizes)
        # Only check videos in similar size ranges to optimize performance
        print(f"{Style.DIM}Checking durations for similar-sized videos...{Style.RESET_ALL}", flush=True)

        # Group videos by size buckets (within 10% of each other)
        size_buckets = {}
        for video in valid_videos:
            if video in [v for v, _, _ in self.duplicate_videos]:
                continue  # Skip already confirmed duplicates

            try:
                size = video.stat().st_size
                # Find bucket (10% tolerance)
                bucket_found = False
                for bucket_size in list(size_buckets.keys()):
                    if abs(size - bucket_size) / max(size, bucket_size) <= 0.10:
                        size_buckets[bucket_size].append(video)
                        bucket_found = True
                        break

                if not bucket_found:
                    size_buckets[size] = [video]
            except:
                continue

        # Only check duration for buckets with multiple videos
        duration_candidates = []
        for bucket_videos in size_buckets.values():
            if len(bucket_videos) > 1:
                duration_candidates.extend(bucket_videos)

        # Fetch durations for candidates
        duration_map = {}
        total_to_check = len(duration_candidates)
        if total_to_check > 0:
            for i, video in enumerate(duration_candidates, 1):
                print(f"\r{Style.DIM}  {i}/{total_to_check}{Style.RESET_ALL}", end='', flush=True)
                duration = self._get_duration(video)
                if duration:
                    duration_map[video] = duration
            print(f"\r{' ' * 20}\r", end='', flush=True)

        # Check for videos with same duration (within 1 second) and similar size
        duration_groups = {}
        for video, duration in duration_map.items():
            duration_key = round(duration)  # Round to nearest second
            if duration_key not in duration_groups:
                duration_groups[duration_key] = []
            duration_groups[duration_key].append(video)

        # For each duration group, check size and hash
        for duration, videos in duration_groups.items():
            if len(videos) > 1:
                # Hash and compare
                hashes = {}
                for video in videos:
                    try:
                        with open(video, 'rb') as f:
                            chunk = f.read(1024 * 1024)
                            file_hash = hashlib.md5(chunk).hexdigest()

                            if file_hash in hashes:
                                # Different sizes but same duration + hash = likely re-encode or duplicate
                                self.duplicate_videos.append((video, hashes[file_hash], "Same duration + hash"))
                            else:
                                hashes[file_hash] = video
                    except:
                        continue

        # Strategy 3: Filename patterns indicating copies
        # Only flag as duplicate if pattern is at END of filename (before extension)
        # This avoids false positives like "weekend 1", "weekend 2" which are series, not dupes
        copy_patterns = [' copy', ' duplicate', '(1)', '(2)', '(3)', ' - copy', '-copy']
        for video in valid_videos:
            name_stem = video.stem  # Filename without extension
            name_lower = name_stem.lower()

            # Check if pattern is at the very end of the filename
            matched_pattern = None
            for pattern in copy_patterns:
                if name_lower.endswith(pattern):
                    matched_pattern = pattern
                    break

            if matched_pattern:
                # Remove the pattern to find original name
                original_stem = name_stem[:len(name_stem) - len(matched_pattern)].strip()
                original_name = original_stem + video.suffix

                # Look for original file
                potential_original = video.parent / original_name
                if potential_original.exists() and potential_original != video:
                    self.duplicate_videos.append((video, potential_original, f"Filename pattern ('{matched_pattern.strip()}')"))


        # Deduplicate the confirmed duplicates list (a file might be caught by multiple strategies)
        seen_dupes = set()
        unique_duplicates = []
        for video, original, reason in self.duplicate_videos:
            key = (str(video), str(original))
            if key not in seen_dupes:
                seen_dupes.add(key)
                unique_duplicates.append((video, original, reason))
        self.duplicate_videos = unique_duplicates

        # Strategy 4: Similar names + similar sizes (potential duplicates for manual review)
        checked_pairs = set()
        for i, video1 in enumerate(valid_videos):
            if video1 in [v for v, _, _ in self.duplicate_videos]:
                continue  # Already confirmed as duplicate

            for video2 in valid_videos[i+1:]:
                if video2 in [v for v, _, _ in self.duplicate_videos]:
                    continue

                # Avoid checking same pair twice
                pair_key = tuple(sorted([str(video1), str(video2)]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                # Compare names
                name1 = video1.stem.lower()
                name2 = video2.stem.lower()
                similarity = SequenceMatcher(None, name1, name2).ratio()

                # Compare sizes (within 1% - tighter threshold)
                try:
                    size1 = video1.stat().st_size
                    size2 = video2.stat().st_size
                    size_diff = abs(size1 - size2) / max(size1, size2)

                    # Very high name similarity + nearly identical size = potential duplicate
                    # Require 95% name match AND <1% size difference
                    if similarity >= 0.95 and size_diff <= 0.01:
                        self.potential_duplicates.append((video1, video2, similarity))
                except:
                    continue

    def _find_videos(self, directory: Path) -> List[Path]:
        """Find all video files in directory and subdirectories."""
        video_extensions = self.config.video_extensions
        videos = []

        for ext in video_extensions:
            videos.extend(directory.rglob(f"*{ext}"))

        # Sort by size (largest first) for better UX
        return sorted(videos, key=lambda p: p.stat().st_size, reverse=True)

    def _prescan_videos(self, video_files: List[Path], min_resolution: str = None, skip_samples: bool = False) -> None:
        """
        Quick pre-scan to identify samples and low-res videos without full health check.

        Args:
            video_files: List of video files to scan
            min_resolution: Minimum resolution requirement
            skip_samples: Skip sample detection
        """
        for video in video_files:
            # Check for samples (fast - just file size)
            if not skip_samples and self.video_processor.is_sample_file(video):
                self.sample_videos.append(video)
                continue

            # Check resolution if specified (requires ffmpeg metadata check)
            if min_resolution:
                resolution = self._get_resolution(video)
                if resolution and not self._meets_min_resolution(resolution, min_resolution):
                    self.low_res_videos.append((video, resolution))

    def _check_video_silent(self, video_file: Path, min_resolution: str = None) -> str:
        """
        Check single video file and return status string (for silent processing).

        Returns:
            'healthy', 'sample', 'corrupt', 'low_quality:<reason>' status string
        """
        # Check if it's a sample file
        if self.video_processor.is_sample_file(video_file):
            self.sample_videos.append(video_file)
            size_mb = video_file.stat().st_size / (1024 * 1024)
            return f"{Fore.YELLOW}SAMPLE{Style.RESET_ALL} ({size_mb:.1f}MB)"

        # Check video health with quality detection
        result = self.video_processor.check_video_health(video_file, check_quality=True)
        is_healthy, is_low_quality, quality_reason, resolution = result

        if not is_healthy:
            self.corrupt_videos.append(video_file)
            return f"{Fore.RED}CORRUPT{Style.RESET_ALL}"

        # Check if video is low quality (auto-detected: <= 480p or < 1000 kb/s)
        if is_low_quality:
            self.low_res_videos.append((video_file, resolution))
            return f"{Fore.YELLOW}LOW QUALITY{Style.RESET_ALL} ({quality_reason})"

        # Check resolution if min_resolution specified (user wants specific threshold)
        if min_resolution:
            resolution = self._get_resolution(video_file)
            if resolution and not self._meets_min_resolution(resolution, min_resolution):
                self.low_res_videos.append((video_file, resolution))
                return f"{Fore.YELLOW}LOW RES{Style.RESET_ALL} ({resolution[0]}x{resolution[1]})"

        # Video is healthy
        self.healthy_videos.append(video_file)
        return 'healthy'

    def _check_video(self, video_file: Path, min_resolution: str = None, skip_health: bool = False) -> None:
        """
        Check single video file.

        Args:
            video_file: Video file to check
            min_resolution: Minimum resolution requirement
            skip_health: Skip health check (only check samples/resolution)
        """
        # Check if it's a sample file
        if self.video_processor.is_sample_file(video_file):
            self.sample_videos.append(video_file)
            size_mb = video_file.stat().st_size / (1024 * 1024)
            print(f"  {Fore.YELLOW}SAMPLE{Style.RESET_ALL} ({size_mb:.1f}MB)")
            return

        # Check video health (unless skipping)
        if not skip_health:
            # Enable quality checking to automatically detect low-res/low-bitrate videos
            result = self.video_processor.check_video_health(video_file, check_quality=True)
            is_healthy, is_low_quality, quality_reason, resolution = result

            if not is_healthy:
                self.corrupt_videos.append(video_file)
                print(f"  {Fore.RED}CORRUPT{Style.RESET_ALL}")
                return

            # Check if video is low quality (auto-detected: <= 480p or < 1000 kb/s)
            if is_low_quality:
                self.low_res_videos.append((video_file, resolution))
                print(f"  {Fore.YELLOW}LOW QUALITY{Style.RESET_ALL} ({quality_reason})")
                return

        # Check resolution if min_resolution specified (user wants specific threshold)
        if min_resolution:
            resolution = self._get_resolution(video_file)
            if resolution and not self._meets_min_resolution(resolution, min_resolution):
                self.low_res_videos.append((video_file, resolution))
                print(f"  {Fore.YELLOW}LOW RES{Style.RESET_ALL} ({resolution[0]}x{resolution[1]})")
                return

        # Video is healthy
        if not skip_health:
            self.healthy_videos.append(video_file)
            print(f"  {Fore.GREEN}HEALTHY{Style.RESET_ALL}")

    def _get_duration(self, video_file: Path) -> float:
        """Get video duration in seconds."""
        try:
            from utils.system_check import SystemCheck
            system_check = SystemCheck(self.config)

            ffmpeg_cmd = system_check.get_tool_command('ffmpeg')
            if not ffmpeg_cmd:
                ffmpeg_cmd = ['ffmpeg']

            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ffmpeg_cmd + ['-i', str(video_file)],
                timeout=10,
                operation=f"Duration check: {video_file.name}",
                expected_codes=[0, 1]
            )

            # Parse duration from ffmpeg output
            if stderr:
                for line in stderr.split('\n'):
                    if 'Duration:' in line:
                        try:
                            duration_str = line.split('Duration:')[1].split(',')[0].strip()
                            h, m, s = duration_str.split(':')
                            return int(h) * 3600 + int(m) * 60 + float(s)
                        except:
                            pass
            return None
        except Exception:
            return None

    def _get_resolution(self, video_file: Path) -> Tuple[int, int]:
        """Get video resolution (width, height)."""
        try:
            from utils.system_check import SystemCheck
            system_check = SystemCheck(self.config)

            ffmpeg_cmd = system_check.get_tool_command('ffmpeg')
            if not ffmpeg_cmd:
                ffmpeg_cmd = ['ffmpeg']

            # Use ffprobe if available, otherwise ffmpeg
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ffmpeg_cmd + ['-i', str(video_file)],
                timeout=10,
                operation=f"Resolution check: {video_file.name}",
                expected_codes=[0, 1]  # ffmpeg returns 1 when no output file specified
            )

            # Parse resolution from output
            # Look for pattern like "1920x1080" or "Stream #0:0: Video: ..., 1920x1080"
            output = stdout + stderr
            import re

            # Try to find resolution pattern
            match = re.search(r'(\d{3,4})x(\d{3,4})', output)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return (width, height)

            return None
        except Exception as e:
            logging.debug(f"Could not get resolution for {video_file.name}: {e}")
            return None

    def _meets_min_resolution(self, resolution: Tuple[int, int], min_res: str) -> bool:
        """Check if resolution meets minimum requirement."""
        width, height = resolution

        # Map common names to pixel heights
        min_heights = {
            '480p': 480,
            '720p': 720,
            '1080p': 1080,
            '1440p': 1440,
            '4k': 2160,
            '2160p': 2160,
        }

        min_height = min_heights.get(min_res.lower())
        if not min_height:
            print(f"{Fore.YELLOW}Warning: Unknown resolution '{min_res}', using 720p{Style.RESET_ALL}")
            min_height = 720

        return height >= min_height

    def print_summary(self, auto_delete: bool = False) -> None:
        """Print summary of results."""
        print(f"\n{Fore.CYAN}Summary{Style.RESET_ALL}\n")

        total = len(self.healthy_videos) + len(self.corrupt_videos) + len(self.sample_videos) + len(self.low_res_videos) + len(self.duplicate_videos)

        print(f"  {Fore.GREEN}Healthy{Style.RESET_ALL}         {len(self.healthy_videos)}")
        print(f"  {Fore.RED}Corrupt{Style.RESET_ALL}         {len(self.corrupt_videos)}")
        print(f"  {Fore.YELLOW}Samples{Style.RESET_ALL}         {len(self.sample_videos)}")
        print(f"  {Fore.YELLOW}Low quality{Style.RESET_ALL}      {len(self.low_res_videos)}")
        print(f"  {Fore.YELLOW}Duplicates{Style.RESET_ALL}       {len(self.duplicate_videos)}")
        if self.potential_duplicates:
            print(f"  {Style.DIM}Potential dupes{Style.RESET_ALL}  {len(self.potential_duplicates)}")
        print(f"  {Style.DIM}Total{Style.RESET_ALL}           {total}\n")

        # Show details for problem videos
        if self.corrupt_videos:
            print(f"{Fore.RED}Corrupt{Style.RESET_ALL}")
            for video in self.corrupt_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  {video.name} {Style.DIM}({size_mb:.1f}MB){Style.RESET_ALL}")
            print()

        if self.sample_videos:
            print(f"{Fore.YELLOW}Samples{Style.RESET_ALL}")
            for video in self.sample_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  {video.name} {Style.DIM}({size_mb:.1f}MB){Style.RESET_ALL}")
            print()

        if self.low_res_videos:
            print(f"{Fore.YELLOW}Low quality{Style.RESET_ALL}")
            for video, resolution in self.low_res_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                if resolution:
                    width, height = resolution
                    print(f"  {video.name} {Style.DIM}({width}x{height}, {size_mb:.1f}MB){Style.RESET_ALL}")
                else:
                    print(f"  {video.name} {Style.DIM}({size_mb:.1f}MB){Style.RESET_ALL}")
            print()

        if self.duplicate_videos:
            print(f"{Fore.YELLOW}Duplicates{Style.RESET_ALL}")
            for video, original, reason in self.duplicate_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  {video.name} {Style.DIM}-> {original.name}{Style.RESET_ALL}")
                print(f"    {Style.DIM}{reason} ({size_mb:.1f}MB){Style.RESET_ALL}")
            print()

        if self.potential_duplicates:
            print(f"{Style.DIM}Potential duplicates{Style.RESET_ALL}")
            for video1, video2, similarity in self.potential_duplicates:
                size1_mb = video1.stat().st_size / (1024 * 1024)
                size2_mb = video2.stat().st_size / (1024 * 1024)
                print(f"  {video1.name} {Style.DIM}({size1_mb:.1f}MB){Style.RESET_ALL}")
                print(f"  {video2.name} {Style.DIM}({size2_mb:.1f}MB){Style.RESET_ALL}")
                print(f"    {Style.DIM}Similarity: {similarity:.0%}{Style.RESET_ALL}")
            print()

        # Offer to delete bad videos (including duplicates)
        bad_videos = self.corrupt_videos + self.sample_videos + [v for v, _ in self.low_res_videos] + [v for v, _, _ in self.duplicate_videos]

        if bad_videos:
            if auto_delete:
                self._delete_videos(bad_videos)
            else:
                self._prompt_delete(bad_videos)
        else:
            print(f"{Fore.GREEN}All videos healthy{Style.RESET_ALL}")

    def _prompt_delete(self, videos: List[Path]) -> None:
        """Prompt user to delete bad videos."""
        total_size_mb = sum(v.stat().st_size for v in videos) / (1024 * 1024)

        print(f"Delete {len(videos)} videos? {Style.DIM}({total_size_mb:.1f}MB){Style.RESET_ALL}")
        response = input(f"[y/N]: ").strip().lower()

        if response in ('y', 'yes'):
            self._delete_videos(videos)
        else:
            print(f"{Style.DIM}Skipped{Style.RESET_ALL}")

    def _delete_videos(self, videos: List[Path]) -> None:
        """Delete specified videos."""
        deleted_count = 0
        failed_count = 0
        total_freed_mb = 0

        print(f"\n{Style.DIM}Deleting...{Style.RESET_ALL}\n")

        for video in videos:
            try:
                size_mb = video.stat().st_size / (1024 * 1024)
                video.unlink()
                deleted_count += 1
                total_freed_mb += size_mb
                print(f"  {Fore.GREEN}ok{Style.RESET_ALL}  {video.name}")
            except Exception as e:
                failed_count += 1
                print(f"  {Fore.RED}err{Style.RESET_ALL} {video.name} {Style.DIM}({e}){Style.RESET_ALL}")

        print(f"\n{Fore.GREEN}Deleted {deleted_count}{Style.RESET_ALL} {Style.DIM}({total_freed_mb:.1f}MB freed){Style.RESET_ALL}")

        if failed_count > 0:
            print(f"{Fore.YELLOW}Failed {failed_count}{Style.RESET_ALL}")


def main():
    """Main entry point for vhealth command."""
    parser = argparse.ArgumentParser(
        description="Video health checker - Validate video files and detect issues",
        epilog="Examples:\n"
               "  vhealth \"C:\\Videos\"\n"
               "  vhealth \"C:\\Videos\\movie.mkv\"\n"
               "  vhealth \"C:\\Videos\" --delete-bad\n"
               "  vhealth \"C:\\Videos\" --min-resolution 720p",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('path', help='Video file or folder to check')
    parser.add_argument('--clean', action='store_true',
                       help='Auto-delete small/sample files without prompting, then health check remaining')
    parser.add_argument('--delete-bad', action='store_true',
                       help='Automatically delete all unhealthy videos at the end')
    parser.add_argument('--min-resolution', metavar='RES',
                       help='Flag videos below this resolution (480p, 720p, 1080p, 4k)')
    parser.add_argument('--skip-samples', action='store_true',
                       help='Skip sample detection, go straight to health check')
    parser.add_argument('--config', help='Path to custom config file')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Show verbose output (ffmpeg messages, etc.)')

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    else:
        logging.basicConfig(level=logging.ERROR, format='%(message)s')  # Only errors, suppress warnings

    # Print header
    print(f"\n{Fore.CYAN}vhealth{Style.RESET_ALL} {Style.DIM}v1.0{Style.RESET_ALL}")
    print(f"{Style.DIM}Video health checker and validator{Style.RESET_ALL}\n")

    # Load config
    if args.config:
        config = Config(config_file=args.config)
    else:
        config = Config()

    # Validate path
    path = Path(args.path)
    if not path.exists():
        print(f"\n{Fore.RED}Error: Path does not exist: {path}{Style.RESET_ALL}")
        sys.exit(1)

    # Run health check
    checker = VideoHealthChecker(config)

    try:
        checker.check_path(
            path,
            min_resolution=args.min_resolution,
            skip_samples=args.skip_samples,
            skip_health=args.clean  # --clean flag enables skip_health for auto-delete
        )
        checker.print_summary(auto_delete=args.delete_bad)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Cancelled by user{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
        logging.error("Health check failed", exc_info=True)
        sys.exit(1)

    print()


if __name__ == '__main__':
    main()
