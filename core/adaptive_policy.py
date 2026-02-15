"""
Adaptive Policy Framework

This module implements self-tuning policies that learn from empirical outcomes
and adapt thresholds based on actual system performance and user feedback.

Design Philosophy:
- Start with conservative defaults
- Learn from false positives and false negatives
- Adapt to environment (HDD vs SSD, fast vs slow CPU)
- Reinforce from user corrections
- Maintain safety bounds (never go below minimum thresholds)

References:
- docs/DEEP_ANALYSIS.md - Adaptive Intelligence section
- docs/FMEA.md - Failure modes that policies address
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from enum import Enum, auto
import statistics


logger = logging.getLogger(__name__)


class DiskType(Enum):
    """Type of storage device."""
    UNKNOWN = auto()
    HDD = auto()
    SSD = auto()
    NVME = auto()


class OutcomeType(Enum):
    """Validation outcome types for learning."""
    TRUE_POSITIVE = auto()   # Correctly rejected bad file
    TRUE_NEGATIVE = auto()   # Correctly accepted good file
    FALSE_POSITIVE = auto()  # Incorrectly rejected good file
    FALSE_NEGATIVE = auto()  # Incorrectly accepted bad file
    USER_OVERRIDE = auto()   # User manually corrected decision


@dataclass
class OperationOutcome:
    """Record of an operation outcome for learning."""
    timestamp: datetime
    operation_type: str  # 'extraction', 'validation', 'truncation_check', etc.
    file_path: str
    file_size_bytes: int
    duration_seconds: float
    decision: str  # 'accept', 'reject', 'timeout', etc.
    outcome: OutcomeType
    metadata: Dict  # Additional context
    user_feedback: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['outcome'] = self.outcome.name
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'OperationOutcome':
        """Create from dictionary."""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['outcome'] = OutcomeType[data['outcome']]
        return cls(**data)


@dataclass
class EnvironmentProfile:
    """Profile of system environment and performance characteristics."""
    disk_type: DiskType
    sequential_read_mbps: float
    random_read_mbps: float
    cpu_score: float  # Relative score based on observed operations
    extraction_speed_mbps: float  # Observed archive extraction speed
    video_decode_fps: float  # Observed video decode speed
    last_updated: datetime

    def to_dict(self) -> dict:
        data = asdict(self)
        data['disk_type'] = self.disk_type.name
        data['last_updated'] = self.last_updated.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'EnvironmentProfile':
        data = data.copy()
        data['disk_type'] = DiskType[data['disk_type']]
        data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


class EnvironmentProfiler:
    """
    Profiles the system environment to adapt operations.

    Detects HDD vs SSD, measures I/O performance, CPU speed, etc.
    """

    def __init__(self, cache_file: Optional[Path] = None):
        """
        Initialize environment profiler.

        Args:
            cache_file: Path to cache profile results (to avoid repeated benchmarks)
        """
        self.cache_file = cache_file or Path.home() / '.unpackr' / 'env_profile.json'
        self.profile: Optional[EnvironmentProfile] = None

    def get_profile(self, force_refresh: bool = False) -> EnvironmentProfile:
        """
        Get environment profile, using cache if available.

        Args:
            force_refresh: Force re-profiling even if cache exists

        Returns:
            Environment profile with performance characteristics
        """
        # Try to load cached profile
        if not force_refresh and self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self.profile = EnvironmentProfile.from_dict(data)

                    # Use cache if less than 7 days old
                    age = datetime.now() - self.profile.last_updated
                    if age < timedelta(days=7):
                        logger.info(f"Using cached environment profile (age: {age.days} days)")
                        return self.profile
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to load cached profile: {e}")

        # Profile the environment
        logger.info("Profiling system environment...")
        self.profile = self._profile_system()

        # Cache the results
        self._save_profile()

        return self.profile

    def _profile_system(self) -> EnvironmentProfile:
        """
        Profile the system by running micro-benchmarks.

        Returns:
            Environment profile with measured characteristics
        """
        import tempfile
        import shutil

        # Create temporary directory for benchmarking
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Detect disk type
            disk_type = self._detect_disk_type(temp_dir)

            # Measure sequential read speed
            seq_read_speed = self._measure_sequential_read(temp_dir)

            # Measure random read speed
            rand_read_speed = self._measure_random_read(temp_dir)

            # CPU score (basic measurement)
            cpu_score = self._measure_cpu_speed()

            # These will be learned over time from actual operations
            extraction_speed = 50.0  # MB/s default estimate
            video_decode_fps = 100.0  # FPS default estimate

            profile = EnvironmentProfile(
                disk_type=disk_type,
                sequential_read_mbps=seq_read_speed,
                random_read_mbps=rand_read_speed,
                cpu_score=cpu_score,
                extraction_speed_mbps=extraction_speed,
                video_decode_fps=video_decode_fps,
                last_updated=datetime.now()
            )

            logger.info(
                f"Environment profiled: {disk_type.name} disk, "
                f"seq={seq_read_speed:.1f} MB/s, "
                f"rand={rand_read_speed:.1f} MB/s, "
                f"cpu_score={cpu_score:.1f}"
            )

            return profile

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _detect_disk_type(self, test_path: Path) -> DiskType:
        """
        Infer disk type from seek time patterns.

        HDDs have high seek time (10ms+), SSDs have low (<1ms).
        """
        # Measure random vs sequential read ratio
        # This is a simplified heuristic - full implementation would use OS APIs
        try:
            seq_speed = self._measure_sequential_read(test_path)
            rand_speed = self._measure_random_read(test_path)

            if seq_speed == 0:
                return DiskType.UNKNOWN

            ratio = seq_speed / rand_speed

            # HDD: Random reads much slower than sequential (ratio > 5)
            # SSD: Random reads similar to sequential (ratio < 2)
            # NVMe: Very high speeds for both
            if seq_speed > 2000 and ratio < 2:
                return DiskType.NVME
            elif ratio > 5:
                return DiskType.HDD
            elif ratio < 3:
                return DiskType.SSD
            else:
                return DiskType.UNKNOWN

        except Exception as e:
            logger.warning(f"Failed to detect disk type: {e}")
            return DiskType.UNKNOWN

    def _measure_sequential_read(self, test_path: Path) -> float:
        """
        Measure sequential read speed in MB/s.

        Args:
            test_path: Directory to use for testing

        Returns:
            Sequential read speed in MB/s
        """
        test_file = test_path / "seq_test.bin"
        file_size_mb = 10  # 10MB test file

        try:
            # Write test file
            data = b'x' * (1024 * 1024)  # 1MB chunks
            with open(test_file, 'wb') as f:
                for _ in range(file_size_mb):
                    f.write(data)

            # Flush OS cache (OS-specific, this is a simplification)
            # On Linux: sync; echo 3 > /proc/sys/vm/drop_caches
            # On Windows: no easy way without admin rights

            # Measure read speed
            start = time.time()
            with open(test_file, 'rb') as f:
                while f.read(1024 * 1024):
                    pass
            elapsed = time.time() - start

            if elapsed <= 0:
                # Timer resolution edge case on very fast I/O.
                return 100.0
            speed_mbps = file_size_mb / elapsed
            return max(speed_mbps, 0.1)

        except Exception as e:
            logger.warning(f"Sequential read benchmark failed: {e}")
            return 100.0  # Default assumption

        finally:
            if test_file.exists():
                test_file.unlink()

    def _measure_random_read(self, test_path: Path) -> float:
        """
        Measure random read speed in MB/s.

        Args:
            test_path: Directory to use for testing

        Returns:
            Random read speed in MB/s
        """
        test_file = test_path / "rand_test.bin"
        file_size_mb = 10

        try:
            # Write test file
            data = b'x' * (1024 * 1024)
            with open(test_file, 'wb') as f:
                for _ in range(file_size_mb):
                    f.write(data)

            # Measure random read speed
            import random
            chunk_size = 64 * 1024  # 64KB chunks
            num_reads = 100

            start = time.perf_counter()
            with open(test_file, 'rb') as f:
                for _ in range(num_reads):
                    offset = random.randint(0, (file_size_mb * 1024 * 1024) - chunk_size)
                    f.seek(offset)
                    f.read(chunk_size)
            elapsed = time.perf_counter() - start

            if elapsed <= 0:
                # Timer resolution edge case on very fast I/O.
                return 50.0
            bytes_read = num_reads * chunk_size
            speed_mbps = (bytes_read / (1024 * 1024)) / elapsed
            return max(speed_mbps, 0.1)

        except Exception as e:
            logger.warning(f"Random read benchmark failed: {e}")
            return 50.0  # Default assumption

        finally:
            if test_file.exists():
                test_file.unlink()

    def _measure_cpu_speed(self) -> float:
        """
        Measure relative CPU speed with simple benchmark.

        Returns:
            CPU score (higher = faster)
        """
        try:
            # Simple computation benchmark
            start = time.time()
            result = 0
            for i in range(1000000):
                result += i * i
            elapsed = time.time() - start

            if elapsed > 0:
                # Score is inversely proportional to time
                # Normalized to ~1.0 for typical modern CPU
                score = 0.5 / elapsed  # Calibrated heuristic
                return max(0.1, min(10.0, score))  # Clamp to reasonable range
            else:
                return 1.0

        except Exception as e:
            logger.warning(f"CPU benchmark failed: {e}")
            return 1.0

    def _save_profile(self):
        """Save profile to cache file."""
        if self.profile is None:
            return

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.profile.to_dict(), f, indent=2)
            logger.debug(f"Saved environment profile to {self.cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save profile: {e}")

    def update_learned_metrics(self, extraction_speed: float = None, video_decode_fps: float = None):
        """
        Update learned metrics from actual operations.

        Args:
            extraction_speed: Observed extraction speed in MB/s
            video_decode_fps: Observed video decode FPS
        """
        if self.profile is None:
            return

        updated = False

        if extraction_speed is not None:
            # Use exponential moving average
            alpha = 0.3
            self.profile.extraction_speed_mbps = (
                alpha * extraction_speed +
                (1 - alpha) * self.profile.extraction_speed_mbps
            )
            updated = True

        if video_decode_fps is not None:
            alpha = 0.3
            self.profile.video_decode_fps = (
                alpha * video_decode_fps +
                (1 - alpha) * self.profile.video_decode_fps
            )
            updated = True

        if updated:
            self.profile.last_updated = datetime.now()
            self._save_profile()


class AdaptivePolicy:
    """
    Self-tuning policy that adapts thresholds based on empirical outcomes.

    Learns from:
    - False positives (rejected good files)
    - False negatives (accepted bad files)
    - User overrides
    - System performance
    """

    def __init__(
        self,
        policy_name: str,
        base_threshold: float,
        min_threshold: float,
        max_threshold: float,
        history_file: Optional[Path] = None
    ):
        """
        Initialize adaptive policy.

        Args:
            policy_name: Name of policy (e.g., 'truncation_threshold')
            base_threshold: Starting threshold value
            min_threshold: Minimum allowed threshold (safety bound)
            max_threshold: Maximum allowed threshold
            history_file: Path to persist outcome history
        """
        self.policy_name = policy_name
        self.base_threshold = base_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.current_threshold = base_threshold

        self.history_file = history_file or (
            Path.home() / '.unpackr' / f'{policy_name}_history.json'
        )
        self.outcome_history: List[OperationOutcome] = []

        self._load_history()

    def decide_threshold(self, context: Optional[Dict] = None) -> float:
        """
        Decide threshold based on past outcomes.

        Args:
            context: Optional context for decision (file type, size, etc.)

        Returns:
            Adapted threshold value
        """
        if len(self.outcome_history) < 10:
            # Not enough data yet, use base threshold
            return self.base_threshold

        # Count recent false positives and false negatives
        recent_outcomes = self.outcome_history[-50:]  # Last 50 outcomes

        false_positives = sum(
            1 for o in recent_outcomes
            if o.outcome == OutcomeType.FALSE_POSITIVE
        )
        false_negatives = sum(
            1 for o in recent_outcomes
            if o.outcome == OutcomeType.FALSE_NEGATIVE
        )

        # Adapt threshold based on error balance
        if false_positives > false_negatives * 2:
            # Too strict - relax threshold
            adjustment = -0.05 * self.base_threshold
        elif false_negatives > false_positives * 2:
            # Too lenient - tighten threshold
            adjustment = 0.05 * self.base_threshold
        else:
            # Balanced - maintain current
            adjustment = 0.0

        # Apply adjustment with exponential smoothing
        self.current_threshold = (
            0.9 * self.current_threshold +
            0.1 * (self.base_threshold + adjustment)
        )

        # Enforce bounds
        self.current_threshold = max(
            self.min_threshold,
            min(self.max_threshold, self.current_threshold)
        )

        logger.debug(
            f"Policy {self.policy_name}: threshold={self.current_threshold:.3f} "
            f"(FP={false_positives}, FN={false_negatives})"
        )

        return self.current_threshold

    def record_outcome(self, outcome: OperationOutcome):
        """
        Record an operation outcome for learning.

        Args:
            outcome: The outcome to record
        """
        self.outcome_history.append(outcome)

        # Limit history size
        if len(self.outcome_history) > 1000:
            self.outcome_history = self.outcome_history[-1000:]

        self._save_history()

    def get_statistics(self) -> Dict:
        """
        Get statistics about policy performance.

        Returns:
            Dictionary with accuracy metrics
        """
        if not self.outcome_history:
            return {
                'total_decisions': 0,
                'accuracy': 0.0,
                'false_positive_rate': 0.0,
                'false_negative_rate': 0.0
            }

        total = len(self.outcome_history)
        true_pos = sum(1 for o in self.outcome_history if o.outcome == OutcomeType.TRUE_POSITIVE)
        true_neg = sum(1 for o in self.outcome_history if o.outcome == OutcomeType.TRUE_NEGATIVE)
        false_pos = sum(1 for o in self.outcome_history if o.outcome == OutcomeType.FALSE_POSITIVE)
        false_neg = sum(1 for o in self.outcome_history if o.outcome == OutcomeType.FALSE_NEGATIVE)

        accuracy = (true_pos + true_neg) / total if total > 0 else 0.0

        # Rates relative to actual positives/negatives
        actual_positives = true_pos + false_neg
        actual_negatives = true_neg + false_pos

        fpr = false_pos / actual_negatives if actual_negatives > 0 else 0.0
        fnr = false_neg / actual_positives if actual_positives > 0 else 0.0

        return {
            'total_decisions': total,
            'accuracy': accuracy,
            'false_positive_rate': fpr,
            'false_negative_rate': fnr,
            'current_threshold': self.current_threshold,
            'true_positives': true_pos,
            'true_negatives': true_neg,
            'false_positives': false_pos,
            'false_negatives': false_neg
        }

    def _load_history(self):
        """Load outcome history from file."""
        if not self.history_file.exists():
            return

        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                self.outcome_history = [
                    OperationOutcome.from_dict(o) for o in data['outcomes']
                ]
                self.current_threshold = data.get('current_threshold', self.base_threshold)
            logger.debug(f"Loaded {len(self.outcome_history)} outcomes for {self.policy_name}")
        except Exception as e:
            logger.warning(f"Failed to load history for {self.policy_name}: {e}")

    def _save_history(self):
        """Save outcome history to file."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump({
                    'policy_name': self.policy_name,
                    'current_threshold': self.current_threshold,
                    'outcomes': [o.to_dict() for o in self.outcome_history]
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save history for {self.policy_name}: {e}")


class AdaptiveTimeoutCalculator:
    """
    Calculates adaptive timeouts based on environment and file characteristics.

    Replaces static timeout calculations with adaptive ones that learn from
    actual performance.
    """

    def __init__(self, profiler: EnvironmentProfiler):
        """
        Initialize timeout calculator.

        Args:
            profiler: Environment profiler for performance characteristics
        """
        self.profiler = profiler
        self.profile = profiler.get_profile()

        # Base timeouts (in seconds)
        self.base_extraction_timeout = 300  # 5 minutes
        self.base_validation_timeout = 120  # 2 minutes

        # Observed operation times for learning
        self.extraction_times: List[Tuple[int, float]] = []  # (file_size, duration)
        self.validation_times: List[Tuple[int, float]] = []

    def calculate_extraction_timeout(self, file_size_bytes: int) -> int:
        """
        Calculate adaptive timeout for archive extraction.

        Args:
            file_size_bytes: Size of archive file

        Returns:
            Timeout in seconds
        """
        file_size_mb = file_size_bytes / (1024 * 1024)

        # Use learned extraction speed if available
        extraction_speed = self.profile.extraction_speed_mbps

        # Estimate time based on file size and extraction speed
        estimated_seconds = file_size_mb / extraction_speed

        # Add buffer based on disk type
        if self.profile.disk_type == DiskType.HDD:
            buffer_multiplier = 3.0  # HDDs need more time for seeks
        elif self.profile.disk_type == DiskType.SSD:
            buffer_multiplier = 2.0
        elif self.profile.disk_type == DiskType.NVME:
            buffer_multiplier = 1.5
        else:
            buffer_multiplier = 2.5  # Unknown, be conservative

        timeout = int(estimated_seconds * buffer_multiplier)

        # Enforce minimum and maximum bounds
        timeout = max(60, min(7200, timeout))  # 1 min to 2 hours

        logger.debug(
            f"Extraction timeout: {timeout}s for {file_size_mb:.1f}MB "
            f"(speed={extraction_speed:.1f} MB/s, disk={self.profile.disk_type.name})"
        )

        return timeout

    def calculate_validation_timeout(self, file_size_bytes: int, duration_seconds: float) -> int:
        """
        Calculate adaptive timeout for video validation.

        Args:
            file_size_bytes: Size of video file
            duration_seconds: Duration of video in seconds

        Returns:
            Timeout in seconds
        """
        # Decode speed varies by video complexity and CPU speed
        decode_fps = self.profile.video_decode_fps * self.profile.cpu_score

        # Estimate decode time
        estimated_decode = duration_seconds / decode_fps

        # Add buffer for analysis and overhead
        timeout = int(estimated_decode * 3.0 + 30)  # 3x buffer + 30s overhead

        # Enforce bounds
        timeout = max(30, min(600, timeout))  # 30s to 10 minutes

        logger.debug(
            f"Validation timeout: {timeout}s for {duration_seconds:.1f}s video "
            f"(decode_fps={decode_fps:.1f}, cpu_score={self.profile.cpu_score:.2f})"
        )

        return timeout

    def record_extraction_time(self, file_size_bytes: int, duration_seconds: float):
        """
        Record actual extraction time for learning.

        Args:
            file_size_bytes: Size of file that was extracted
            duration_seconds: Actual time taken
        """
        self.extraction_times.append((file_size_bytes, duration_seconds))

        # Limit history
        if len(self.extraction_times) > 100:
            self.extraction_times = self.extraction_times[-100:]

        # Update learned extraction speed
        if len(self.extraction_times) >= 5:
            # Calculate recent average speed
            recent = self.extraction_times[-10:]
            speeds = [
                (size_bytes / (1024 * 1024)) / duration
                for size_bytes, duration in recent
                if duration > 0
            ]
            if speeds:
                avg_speed = statistics.mean(speeds)
                self.profiler.update_learned_metrics(extraction_speed=avg_speed)
                self.profile = self.profiler.get_profile()

    def record_validation_time(self, duration_video_seconds: float, duration_actual_seconds: float):
        """
        Record actual validation time for learning.

        Args:
            duration_video_seconds: Duration of video content
            duration_actual_seconds: Actual time taken to validate
        """
        self.validation_times.append((duration_video_seconds, duration_actual_seconds))

        if len(self.validation_times) > 100:
            self.validation_times = self.validation_times[-100:]

        # Update learned decode FPS
        if len(self.validation_times) >= 5:
            recent = self.validation_times[-10:]
            fps_values = [
                video_dur / actual_dur
                for video_dur, actual_dur in recent
                if actual_dur > 0
            ]
            if fps_values:
                avg_fps = statistics.mean(fps_values)
                self.profiler.update_learned_metrics(video_decode_fps=avg_fps)
                self.profile = self.profiler.get_profile()
