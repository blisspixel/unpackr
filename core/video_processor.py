"""
Video processing for Unpackr.
Handles video file health checks and validation.
"""

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.safety import SubprocessSafety, SafetyLimits
from utils.system_check import SystemCheck
from core.safety_invariants import ValidationCache, ValidationResult, ValidationDecision
from utils.error_messages import log_error
from datetime import datetime


class VideoProcessor:
    """Handles video file validation and health checks."""
    
    def __init__(self, config=None, process_tracker=None):
        """Initialize the video processor.
        
        Args:
            config: Configuration object
            process_tracker: Object with 'active_process' attribute for cancellation support
        """
        self.config = config or {}
        self.system_check = SystemCheck(config)
        self.process_tracker = process_tracker
    
    def check_video_health(self, video_file: Path, check_quality: bool = False) -> tuple:
        """
        Check if a video file is healthy and fully playable (not corrupted or partial).

        Performs comprehensive validation:
        1. File size sanity check (not 0 bytes, reasonable for video)
        2. Get video metadata (duration, bitrate, streams)
        3. Verify duration vs file size ratio (detect truncated files)
        4. Full decode test to ensure video can be read to completion
        5. Optional: Check for low quality (resolution, bitrate)

        Args:
            video_file: Path to video file
            check_quality: If True, also check for low quality (resolution < 480p or bitrate < 1000 kb/s)

        Returns:
            If check_quality is False: bool (True if healthy)
            If check_quality is True: tuple (is_healthy: bool, is_low_quality: bool, quality_reason: str, resolution: tuple)
        """
        file_size_mb = video_file.stat().st_size / (1024 * 1024)

        # Check if file size is 0 or suspiciously small
        if file_size_mb < 1:
            log_error(
                what_failed=f"Video file rejected: {video_file.name}",
                reason=f"File too small ({file_size_mb:.2f}MB)",
                action="Check if download completed or extraction failed",
                location=video_file.parent
            )
            if check_quality:
                return (False, False, None, None)
            return False

        # Use ffmpeg to check video integrity with comprehensive validation
        try:
            # Get ffmpeg command from config
            ffmpeg_cmd = self.system_check.get_tool_command('ffmpeg')
            if not ffmpeg_cmd:
                ffmpeg_cmd = ['ffmpeg']

            # Step 1: Get video metadata (duration, bitrate, codec info)
            logging.debug(f"Checking video metadata: {video_file.name}")
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ffmpeg_cmd + ['-i', str(video_file)],
                timeout=10,  # Metadata check should be fast
                operation=f"Video metadata check: {video_file.name}",
                expected_codes=[0, 1],  # ffmpeg returns 1 when no output file specified (normal for metadata check)
                process_tracker=self.process_tracker
            )

            # Parse duration, bitrate, and resolution from ffmpeg output
            duration_seconds = None
            bitrate_kbps = None
            resolution = None  # (width, height)

            # Check stderr for Duration line (ffmpeg outputs metadata to stderr)
            if stderr:
                import re
                for line in stderr.split('\n'):
                    if 'Duration:' in line:
                        # Extract duration: "Duration: 00:45:23.45"
                        try:
                            duration_str = line.split('Duration:')[1].split(',')[0].strip()
                            h, m, s = duration_str.split(':')
                            duration_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                        except:
                            pass
                    if 'bitrate:' in line:
                        # Extract bitrate: "bitrate: 2500 kb/s"
                        try:
                            bitrate_str = line.split('bitrate:')[1].strip()
                            bitrate_kbps = float(bitrate_str.split()[0])
                        except:
                            pass
                    if 'Stream' in line and 'Video:' in line:
                        # Extract resolution: "Stream #0:0: Video: ..., 1920x1080"
                        match = re.search(r'(\d{3,4})x(\d{3,4})', line)
                        if match:
                            resolution = (int(match.group(1)), int(match.group(2)))

            # Validate duration exists and is reasonable
            if not duration_seconds or duration_seconds < 10:
                log_error(
                    what_failed=f"Video validation failed: {video_file.name}",
                    reason=f"Invalid or missing duration ({duration_seconds}s)",
                    action="File may be corrupted or incomplete - re-extract or re-download",
                    location=video_file.parent
                )
                if check_quality:
                    return (False, False, None, resolution)
                return False

            # Calculate expected file size from duration and bitrate
            # Typical video bitrates: 720p ~2500kbps, 1080p ~5000kbps, 4K ~15000kbps
            if bitrate_kbps:
                expected_size_mb = (bitrate_kbps * duration_seconds) / (8 * 1024)
                size_ratio = file_size_mb / expected_size_mb if expected_size_mb > 0 else 0

                # If actual size is less than 70% of expected, likely truncated
                if size_ratio < 0.70:
                    log_error(
                        what_failed=f"Video appears truncated: {video_file.name}",
                        reason=f"{file_size_mb:.1f}MB actual vs {expected_size_mb:.1f}MB expected (ratio: {size_ratio:.2f})",
                        action="Re-extract archive or re-download file",
                        location=video_file.parent
                    )
                    if check_quality:
                        return (False, False, None, resolution)
                    return False

                logging.debug(f"Size validation passed: {file_size_mb:.1f}MB (ratio: {size_ratio:.2f})")

            # Step 2: Full decode test - actually decode the entire video to verify all frames readable
            logging.debug(f"Full decode test: {video_file.name}")
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ffmpeg_cmd + [
                    '-v', 'error',           # Only show errors
                    '-i', str(video_file),   # Input file
                    '-map', '0:v:0',         # Only decode first video stream (faster)
                    '-c:v', 'copy',          # Copy codec (fast - just demux)
                    '-f', 'null',            # Null output
                    '-'
                ],
                timeout=SafetyLimits.VIDEO_CHECK_TIMEOUT,
                operation=f"Video decode test: {video_file.name}",
                process_tracker=self.process_tracker
            )

            # Check for errors in decode
            if not success:
                log_error(
                    what_failed=f"Video decode test failed: {video_file.name}",
                    reason="Operation timed out or ffmpeg failed to run",
                    action="Check if file is playable and ffmpeg is working",
                    location=video_file.parent
                )
                if check_quality:
                    return (False, False, None, resolution)
                return False

            if code != 0:
                log_error(
                    what_failed=f"Video decode failed: {video_file.name}",
                    reason=f"ffmpeg returned error code {code}",
                    action="File may be corrupted - re-extract or re-download",
                    location=video_file.parent
                )
                if check_quality:
                    return (False, False, None, resolution)
                return False

            # Check stderr for corruption indicators
            if stderr:
                error_keywords = [
                    'Invalid data',
                    'corrupt',
                    'truncated',
                    'incomplete',
                    'Error while decoding',
                    'moov atom not found',
                    'Header missing',
                    'Premature end'
                ]

                stderr_lower = stderr.lower()
                for keyword in error_keywords:
                    if keyword.lower() in stderr_lower:
                        log_error(
                            what_failed=f"Video corruption detected: {video_file.name}",
                            reason=f"Corruption indicator found: {keyword}",
                            action="Re-extract archive or re-download file",
                            location=video_file.parent,
                            details=f"ffmpeg output: {stderr[:300]}"
                        )
                        if check_quality:
                            return (False, False, None, resolution)
                        return False

            # Video is healthy - now check quality if requested
            if check_quality:
                is_low_quality = False
                quality_reason = None

                # Check for low resolution (480p or less)
                if resolution:
                    width, height = resolution
                    if height <= 480:
                        is_low_quality = True
                        quality_reason = f"Low resolution ({width}x{height})"

                # Check for very low bitrate (< 1000 kb/s is poor for any video)
                if not is_low_quality and bitrate_kbps and bitrate_kbps < 1000:
                    is_low_quality = True
                    quality_reason = f"Low bitrate ({bitrate_kbps:.0f} kb/s)"

                # Check for low bitrate relative to resolution
                if not is_low_quality and resolution and bitrate_kbps:
                    width, height = resolution
                    # Expected bitrates: 720p ~2500kbps, 1080p ~5000kbps
                    # Use conservative thresholds
                    if height >= 1080 and bitrate_kbps < 3000:
                        is_low_quality = True
                        quality_reason = f"Low bitrate for 1080p ({bitrate_kbps:.0f} kb/s)"
                    elif height >= 720 and bitrate_kbps < 1500:
                        is_low_quality = True
                        quality_reason = f"Low bitrate for 720p ({bitrate_kbps:.0f} kb/s)"

                logging.info(f"Video health check PASSED: {video_file.name} ({file_size_mb:.1f}MB, {duration_seconds:.1f}s){' - ' + quality_reason if is_low_quality else ''}")

                # Register validated video with ValidationCache to prevent accidental deletion
                decision = ValidationDecision.FAIL_LOW_QUALITY if is_low_quality else ValidationDecision.PASS
                ValidationCache.set(video_file, ValidationResult(
                    path=video_file,
                    decision=decision,
                    timestamp=datetime.now(),
                    metadata={'size_mb': file_size_mb, 'duration_s': duration_seconds, 'resolution': resolution}
                ))

                return (True, is_low_quality, quality_reason, resolution)

            logging.info(f"Video health check PASSED: {video_file.name} ({file_size_mb:.1f}MB, {duration_seconds:.1f}s)")

            # Register validated video with ValidationCache to prevent accidental deletion
            ValidationCache.set(video_file, ValidationResult(
                path=video_file,
                decision=ValidationDecision.PASS,
                timestamp=datetime.now(),
                metadata={'size_mb': file_size_mb, 'duration_s': duration_seconds}
            ))

            return True

        except FileNotFoundError:
            logging.warning("FFMPEG is not installed. Skipping health check - ASSUMING VIDEO IS GOOD")
            if check_quality:
                return (True, False, None, None)
            return True  # Assume healthy if can't check
        except Exception as e:
            log_error(
                what_failed=f"Video health check failed: {video_file.name}",
                reason=str(e),
                action="Check if file is accessible and ffmpeg is working",
                location=video_file.parent
            )
            if check_quality:
                return (False, False, None, None)
            return False
    
    def is_sample_file(self, video_file: Path, min_size_mb: int = 50) -> bool:
        """
        Check if a video file is likely a sample (too small).
        
        Args:
            video_file: Path to video file
            min_size_mb: Minimum size in MB to not be considered a sample
            
        Returns:
            True if file is likely a sample, False otherwise
        """
        # Check if file exists first
        if not video_file.exists():
            return False
        
        # Check filename for 'sample' keyword
        if 'sample' in video_file.name.lower():
            return True
            
        # Check file size
        try:
            size_mb = video_file.stat().st_size / (1024 * 1024)
            return size_mb < min_size_mb
        except (OSError, FileNotFoundError):
            return False
