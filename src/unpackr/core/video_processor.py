"""
Video processing for Unpackr.
Handles video file health checks and validation.
"""

import contextlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast, overload

from unpackr.core.config import ConfigSource
from unpackr.core.safety_invariants import ValidationCache, ValidationDecision, ValidationResult
from unpackr.utils.error_messages import log_error
from unpackr.utils.safety import ProcessTracker, SafetyLimits, SubprocessSafety
from unpackr.utils.system_check import SystemCheck

Resolution: TypeAlias = tuple[int, int] | None
# (is_healthy, is_low_quality, quality_reason, resolution)
QualityResult: TypeAlias = tuple[bool, bool, str | None, Resolution]
HealthResult: TypeAlias = bool | QualityResult

# ffmpeg stderr phrases that mean the file is damaged or incomplete.
CORRUPTION_INDICATORS = (
    "invalid data",
    "corrupt",
    "truncated",
    "incomplete",
    "error while decoding",
    "moov atom not found",
    "header missing",
    "premature end",
    "ended prematurely",
    "partial file",
    "unexpected end",
)

# A demux pass that reaches less than this share of the declared duration
# (and falls short by more than TRUNCATION_MIN_GAP_SECONDS) is truncated.
TRUNCATION_MIN_RATIO = 0.9
TRUNCATION_MIN_GAP_SECONDS = 2.0


@dataclass(frozen=True)
class VideoVerdict:
    """Outcome of one video check.

    category is one of "healthy", "preview", "corrupt", "truncated" or "unverified".
    "preview" means the file is a real video that is too short to be the wanted
    content (a preview, sample or trailer); it is removed like a sample, not
    reported as damage.
    """

    ok: bool
    category: str
    reason_code: str
    detail: str = ""


def _config_value(config: Any, key: str, default: Any) -> Any:
    if isinstance(config, dict):
        return cast(dict[str, Any], config).get(key, default)
    getter = getattr(config, "get", None)
    if callable(getter):
        value = getter(key, default)
        return default if value is None else value
    return getattr(config, key, default)


def parse_ffmpeg_duration(stderr: str) -> float | None:
    """Return the container duration in seconds from ffmpeg -i output, or None."""
    for line in stderr.split("\n"):
        if "Duration:" not in line:
            continue
        try:
            duration_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, sec = duration_str.split(":")
            return int(h) * 3600 + int(m) * 60 + float(sec)
        except (ValueError, IndexError):
            return None
    return None


def parse_progress_seconds(stdout: str) -> float | None:
    """Return the last media position reported by ffmpeg -progress, in seconds."""
    last: float | None = None
    for line in stdout.splitlines():
        key, _, value = line.partition("=")
        if key in ("out_time_us", "out_time_ms") and value.strip().lstrip("-").isdigit():
            # ffmpeg reports both keys in microseconds.
            last = int(value.strip()) / 1_000_000
    return last


class VideoProcessor:
    """Handles video file validation and health checks."""

    def __init__(self, config: ConfigSource | None = None, process_tracker: ProcessTracker | None = None) -> None:
        """Initialize the video processor.

        Args:
            config: Configuration object
            process_tracker: Object with 'active_process' attribute for cancellation support
        """
        self.config: ConfigSource = config or {}
        self.system_check = SystemCheck(config)
        self.process_tracker = process_tracker
        self.last_verdict: VideoVerdict | None = None

    @property
    def min_duration_seconds(self) -> float:
        """Shortest duration kept as real content; shorter videos are previews."""
        value = _config_value(self.config, "min_video_duration_seconds", 10)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 10.0

    def _ffmpeg_cmd(self) -> list[str]:
        return self.system_check.get_tool_command("ffmpeg") or ["ffmpeg"]

    def probe_duration(self, video_file: Path) -> float | None:
        """Read the container duration without decoding (fast, read-only)."""
        try:
            _ok, _out, stderr, _code = SubprocessSafety.run_with_timeout(
                self._ffmpeg_cmd() + ["-hide_banner", "-i", str(video_file)],
                timeout=10,
                operation=f"Video metadata check: {video_file.name}",
                expected_codes=[0, 1],
                process_tracker=self.process_tracker,
            )
        except FileNotFoundError:
            return None
        return parse_ffmpeg_duration(stderr or "")

    def classify_preview(self, duration_seconds: float | None) -> VideoVerdict | None:
        """Return a preview verdict when a known duration is under the minimum."""
        minimum = self.min_duration_seconds
        if duration_seconds and minimum > 0 and duration_seconds < minimum:
            return VideoVerdict(
                ok=False,
                category="preview",
                reason_code="video_too_short",
                detail=f"{duration_seconds:.1f}s is under the {minimum:g}s minimum (preview or sample)",
            )
        return None

    def _fail(self, verdict: VideoVerdict, check_quality: bool, resolution: Resolution = None) -> HealthResult:
        self.last_verdict = verdict
        if check_quality:
            return (False, False, None, resolution)
        return False

    @overload
    def check_video_health(self, video_file: Path, check_quality: Literal[False] = False) -> bool: ...
    @overload
    def check_video_health(self, video_file: Path, check_quality: Literal[True]) -> QualityResult: ...
    @overload
    def check_video_health(self, video_file: Path, check_quality: bool) -> HealthResult: ...

    def check_video_health(self, video_file: Path, check_quality: bool = False) -> HealthResult:
        """
        Check if a video file is healthy and fully playable (not corrupted or partial).

        Validation steps:
        1. File size sanity check (not 0 bytes, reasonable for video)
        2. Read container metadata (duration, bitrate, resolution)
        3. Classify videos shorter than ``min_video_duration_seconds`` as previews
        4. Demux the first video stream to the end, failing on ffmpeg corruption
           messages and on streams that end well before the declared duration
        5. Optional: check for low quality (resolution, bitrate)

        The detailed outcome of the most recent call is kept in ``last_verdict``.

        Args:
            video_file: Path to video file
            check_quality: If True, also check for low quality (resolution < 480p or bitrate < 1000 kb/s)

        Returns:
            If check_quality is False: bool (True if healthy)
            If check_quality is True: tuple (is_healthy: bool, is_low_quality: bool, quality_reason: str, resolution: tuple)
        """
        self.last_verdict = None
        file_size_mb = video_file.stat().st_size / (1024 * 1024)

        if file_size_mb < 1:
            log_error(
                what_failed=f"Video file rejected: {video_file.name}",
                reason=f"File too small ({file_size_mb:.2f}MB)",
                action="Check if download completed or extraction failed",
                location=video_file.parent,
            )
            return self._fail(
                VideoVerdict(False, "corrupt", "video_file_too_small", f"{file_size_mb:.2f}MB"), check_quality
            )

        try:
            ffmpeg_cmd = self._ffmpeg_cmd()

            # Step 1: container metadata (ffmpeg prints it to stderr and exits 1 without an output).
            logging.debug(f"Checking video metadata: {video_file.name}")
            _success, _stdout, stderr, _code = SubprocessSafety.run_with_timeout(
                ffmpeg_cmd + ["-i", str(video_file)],
                timeout=10,
                operation=f"Video metadata check: {video_file.name}",
                expected_codes=[0, 1],
                process_tracker=self.process_tracker,
            )

            stderr = stderr or ""
            duration_seconds = parse_ffmpeg_duration(stderr)
            bitrate_kbps = None
            resolution: Resolution = None  # (width, height)
            for line in stderr.split("\n"):
                if "bitrate:" in line:
                    with contextlib.suppress(ValueError, IndexError):
                        bitrate_kbps = float(line.split("bitrate:")[1].strip().split()[0])
                if "Stream" in line and "Video:" in line:
                    match = re.search(r"(\d{3,4})x(\d{3,4})", line)
                    if match:
                        resolution = (int(match.group(1)), int(match.group(2)))

            if not duration_seconds:
                log_error(
                    what_failed=f"Video validation failed: {video_file.name}",
                    reason="Missing or zero duration",
                    action="File may be corrupted or incomplete - re-extract or re-download",
                    location=video_file.parent,
                )
                return self._fail(
                    VideoVerdict(False, "corrupt", "video_duration_missing", "no readable duration"),
                    check_quality,
                    resolution,
                )

            preview = self.classify_preview(duration_seconds)
            if preview is not None:
                logging.info(f"Preview or sample video: {video_file.name} ({preview.detail})")
                return self._fail(preview, check_quality, resolution)

            # Step 2: demux the first video stream to the end. -progress reports how far
            # the stream actually reaches, which exposes files cut short even when ffmpeg
            # exits 0 (a truncated Matroska file does).
            logging.debug(f"Stream read test: {video_file.name}")
            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                ffmpeg_cmd
                + [
                    "-v",
                    "error",
                    "-nostats",
                    "-progress",
                    "pipe:1",
                    "-i",
                    str(video_file),
                    "-map",
                    "0:v:0",
                    "-c:v",
                    "copy",
                    "-f",
                    "null",
                    "-",
                ],
                timeout=SafetyLimits.VIDEO_CHECK_TIMEOUT,
                operation=f"Video decode test: {video_file.name}",
                process_tracker=self.process_tracker,
            )

            if not success:
                log_error(
                    what_failed=f"Video decode test failed: {video_file.name}",
                    reason="Operation timed out or ffmpeg failed to run",
                    action="Check if file is playable and ffmpeg is working",
                    location=video_file.parent,
                )
                return self._fail(
                    VideoVerdict(False, "corrupt", "video_read_failed", "ffmpeg did not finish"),
                    check_quality,
                    resolution,
                )

            if code != 0:
                log_error(
                    what_failed=f"Video decode failed: {video_file.name}",
                    reason=f"ffmpeg returned error code {code}",
                    action="File may be corrupted - re-extract or re-download",
                    location=video_file.parent,
                )
                return self._fail(
                    VideoVerdict(False, "corrupt", "video_read_failed", f"ffmpeg exit code {code}"),
                    check_quality,
                    resolution,
                )

            stderr_lower = (stderr or "").lower()
            for keyword in CORRUPTION_INDICATORS:
                if keyword in stderr_lower:
                    log_error(
                        what_failed=f"Video corruption detected: {video_file.name}",
                        reason=f"Corruption indicator found: {keyword}",
                        action="Re-extract archive or re-download file",
                        location=video_file.parent,
                        details=f"ffmpeg output: {(stderr or '')[:300]}",
                    )
                    category = (
                        "truncated" if keyword in ("ended prematurely", "partial file", "truncated") else "corrupt"
                    )
                    return self._fail(
                        VideoVerdict(False, category, f"video_{category}", f"ffmpeg reported '{keyword}'"),
                        check_quality,
                        resolution,
                    )

            reached = parse_progress_seconds(stdout or "")
            if (
                reached is not None
                and reached < duration_seconds * TRUNCATION_MIN_RATIO
                and duration_seconds - reached > TRUNCATION_MIN_GAP_SECONDS
            ):
                detail = f"stream ends at {reached:.1f}s of a declared {duration_seconds:.1f}s"
                log_error(
                    what_failed=f"Video appears truncated: {video_file.name}",
                    reason=detail,
                    action="Re-extract archive or re-download file",
                    location=video_file.parent,
                )
                return self._fail(
                    VideoVerdict(False, "truncated", "video_truncated", detail), check_quality, resolution
                )

            is_low_quality = False
            quality_reason: str | None = None
            if check_quality:
                if resolution:
                    width, height = resolution
                    if height <= 480:
                        is_low_quality = True
                        quality_reason = f"Low resolution ({width}x{height})"
                if not is_low_quality and bitrate_kbps and bitrate_kbps < 1000:
                    is_low_quality = True
                    quality_reason = f"Low bitrate ({bitrate_kbps:.0f} kb/s)"
                if not is_low_quality and resolution and bitrate_kbps:
                    width, height = resolution
                    if height >= 1080 and bitrate_kbps < 3000:
                        is_low_quality = True
                        quality_reason = f"Low bitrate for 1080p ({bitrate_kbps:.0f} kb/s)"
                    elif height >= 720 and bitrate_kbps < 1500:
                        is_low_quality = True
                        quality_reason = f"Low bitrate for 720p ({bitrate_kbps:.0f} kb/s)"

            quality_suffix = f" - {quality_reason}" if quality_reason else ""
            logging.info(
                f"Video health check PASSED: {video_file.name} ({file_size_mb:.1f}MB, "
                f"{duration_seconds:.1f}s){quality_suffix}"
            )
            self.last_verdict = VideoVerdict(True, "healthy", "video_ok", f"{duration_seconds:.1f}s")

            # Register validated video with ValidationCache to prevent accidental deletion
            metadata: dict[str, Any] = {"size_mb": file_size_mb, "duration_s": duration_seconds}
            if check_quality:
                metadata["resolution"] = resolution
            decision = ValidationDecision.FAIL_LOW_QUALITY if is_low_quality else ValidationDecision.PASS
            ValidationCache.set(
                video_file,
                ValidationResult(path=video_file, decision=decision, timestamp=datetime.now(), metadata=metadata),
            )

            if check_quality:
                return (True, is_low_quality, quality_reason, resolution)
            return True

        except FileNotFoundError:
            logging.warning("FFMPEG is not installed. Skipping health check - ASSUMING VIDEO IS GOOD")
            self.last_verdict = VideoVerdict(True, "unverified", "video_unverified_no_ffmpeg", "ffmpeg not found")
            if check_quality:
                return (True, False, None, None)
            return True
        except Exception as e:
            log_error(
                what_failed=f"Video health check failed: {video_file.name}",
                reason=str(e),
                action="Check if file is accessible and ffmpeg is working",
                location=video_file.parent,
            )
            return self._fail(VideoVerdict(False, "corrupt", "video_check_error", str(e)[:200]), check_quality)

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
        if "sample" in video_file.name.lower():
            return True

        # Check file size
        try:
            size_mb = video_file.stat().st_size / (1024 * 1024)
            return size_mb < min_size_mb
        except (OSError, FileNotFoundError):
            return False
