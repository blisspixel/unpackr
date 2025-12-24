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
            if not skip_samples or min_resolution:
                print(f"{Style.DIM}Pre-scanning for samples and resolution...{Style.RESET_ALL}\n")
                self._prescan_videos(video_files, min_resolution, skip_samples)

                # Show what we found
                total_bad = len(self.sample_videos) + len(self.low_res_videos)
                if total_bad > 0:
                    print(f"\n{Fore.YELLOW}Pre-scan found:{Style.RESET_ALL}")
                    if self.sample_videos:
                        print(f"  {len(self.sample_videos)} sample files")
                    if self.low_res_videos:
                        print(f"  {len(self.low_res_videos)} low-resolution files")

                    # Ask if they want to delete these without health checking
                    if not skip_health:
                        response = input(f"\nDelete these {total_bad} files without health check? [y/N]: ").strip().lower()
                        if response in ('y', 'yes'):
                            skip_health = True

            # Now do health checks on remaining videos (if not skipping)
            if not skip_health:
                print(f"\n{Style.DIM}Checking video health...{Style.RESET_ALL}\n")
                for i, video in enumerate(video_files, 1):
                    # Skip if already identified as sample or low-res
                    if video in self.sample_videos or any(v == video for v, _ in self.low_res_videos):
                        continue

                    print(f"[{i}/{len(video_files)}] {video.name}")
                    self._check_video(video, min_resolution=None, skip_health=False)
        else:
            print(f"{Fore.RED}Path not found: {path}{Style.RESET_ALL}")

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
            is_healthy = self.video_processor.check_video_health(video_file)

            if not is_healthy:
                self.corrupt_videos.append(video_file)
                print(f"  {Fore.RED}CORRUPT{Style.RESET_ALL}")
                return

        # Check resolution if specified
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
                operation=f"Resolution check: {video_file.name}"
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
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Health Check Summary{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        total = len(self.healthy_videos) + len(self.corrupt_videos) + len(self.sample_videos) + len(self.low_res_videos)

        print(f"{Fore.GREEN}✓ Healthy:{Style.RESET_ALL}     {len(self.healthy_videos)}")
        print(f"{Fore.RED}✗ Corrupt:{Style.RESET_ALL}     {len(self.corrupt_videos)}")
        print(f"{Fore.YELLOW}⚠ Samples:{Style.RESET_ALL}     {len(self.sample_videos)}")
        print(f"{Fore.YELLOW}⚠ Low Res:{Style.RESET_ALL}     {len(self.low_res_videos)}")
        print(f"{Style.DIM}Total:{Style.RESET_ALL}        {total}\n")

        # Show details for problem videos
        if self.corrupt_videos:
            print(f"{Fore.RED}Corrupt Videos:{Style.RESET_ALL}")
            for video in self.corrupt_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  • {video.name} ({size_mb:.1f}MB)")
            print()

        if self.sample_videos:
            print(f"{Fore.YELLOW}Sample Videos:{Style.RESET_ALL}")
            for video in self.sample_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  • {video.name} ({size_mb:.1f}MB)")
            print()

        if self.low_res_videos:
            print(f"{Fore.YELLOW}Low Resolution Videos:{Style.RESET_ALL}")
            for video, (width, height) in self.low_res_videos:
                size_mb = video.stat().st_size / (1024 * 1024)
                print(f"  • {video.name} ({width}x{height}, {size_mb:.1f}MB)")
            print()

        # Offer to delete bad videos
        bad_videos = self.corrupt_videos + self.sample_videos + [v for v, _ in self.low_res_videos]

        if bad_videos:
            if auto_delete:
                self._delete_videos(bad_videos)
            else:
                self._prompt_delete(bad_videos)
        else:
            print(f"{Fore.GREEN}All videos are healthy!{Style.RESET_ALL}")

    def _prompt_delete(self, videos: List[Path]) -> None:
        """Prompt user to delete bad videos."""
        total_size_mb = sum(v.stat().st_size for v in videos) / (1024 * 1024)

        print(f"{Fore.YELLOW}Delete {len(videos)} videos? (Total: {total_size_mb:.1f}MB){Style.RESET_ALL}")
        print(f"{Style.DIM}This will free up disk space.{Style.RESET_ALL}")

        response = input(f"\nDelete? [y/N]: ").strip().lower()

        if response in ('y', 'yes'):
            self._delete_videos(videos)
        else:
            print(f"{Style.DIM}No videos deleted.{Style.RESET_ALL}")

    def _delete_videos(self, videos: List[Path]) -> None:
        """Delete specified videos."""
        deleted_count = 0
        failed_count = 0
        total_freed_mb = 0

        print(f"\n{Style.DIM}Deleting videos...{Style.RESET_ALL}")

        for video in videos:
            try:
                size_mb = video.stat().st_size / (1024 * 1024)
                video.unlink()
                deleted_count += 1
                total_freed_mb += size_mb
                print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Deleted: {video.name}")
            except Exception as e:
                failed_count += 1
                print(f"  {Fore.RED}✗{Style.RESET_ALL} Failed: {video.name} ({e})")

        print(f"\n{Fore.GREEN}Deleted {deleted_count} videos{Style.RESET_ALL} ({total_freed_mb:.1f}MB freed)")

        if failed_count > 0:
            print(f"{Fore.YELLOW}Failed to delete {failed_count} videos{Style.RESET_ALL}")


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
    parser.add_argument('--delete-bad', action='store_true',
                       help='Automatically delete corrupt, sample, and low-res videos')
    parser.add_argument('--min-resolution', metavar='RES',
                       help='Flag videos below this resolution (480p, 720p, 1080p, 4k)')
    parser.add_argument('--skip-samples', action='store_true',
                       help='Skip sample detection, go straight to health check')
    parser.add_argument('--skip-health', action='store_true',
                       help='Skip health check (only check samples/resolution)')
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
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Video Health Checker{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

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
            skip_health=args.skip_health
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
