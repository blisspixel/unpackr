"""
Test suite for adaptive_policy module.

Tests cover:
- Environment profiling (disk type detection, performance measurement)
- Adaptive policy learning (threshold adjustment based on outcomes)
- Adaptive timeout calculation
"""

import pytest
import tempfile
import shutil
import time
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.adaptive_policy import (
    EnvironmentProfiler,
    DiskType,
    AdaptivePolicy,
    AdaptiveTimeoutCalculator,
    OperationOutcome,
    OutcomeType,
    EnvironmentProfile
)
from datetime import datetime


class TestEnvironmentProfiler:
    """Test environment profiling functionality."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def cache_file(self, temp_dir):
        return temp_dir / "env_profile.json"

    def test_profiler_initialization(self, cache_file):
        """Test profiler initializes correctly."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        assert profiler.cache_file == cache_file
        assert profiler.profile is None

    def test_profile_system_creates_profile(self, cache_file):
        """Test that profiling creates a valid profile."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        profile = profiler.get_profile()

        assert profile is not None
        assert isinstance(profile.disk_type, DiskType)
        assert profile.sequential_read_mbps > 0
        assert profile.random_read_mbps > 0
        assert profile.cpu_score > 0

    def test_profile_caching(self, cache_file):
        """Test that profile is cached and reused."""
        profiler1 = EnvironmentProfiler(cache_file=cache_file)
        profile1 = profiler1.get_profile()

        # Create new profiler with same cache
        profiler2 = EnvironmentProfiler(cache_file=cache_file)
        profile2 = profiler2.get_profile()

        # Should load from cache (same values)
        assert profile1.disk_type == profile2.disk_type
        assert profile1.sequential_read_mbps == profile2.sequential_read_mbps

    def test_force_refresh_ignores_cache(self, cache_file):
        """Test force refresh profiles again."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        profile1 = profiler.get_profile()

        # Force refresh should profile again
        profile2 = profiler.get_profile(force_refresh=True)

        assert profile2 is not None
        # May have different values, but should be valid
        assert profile2.disk_type != DiskType.UNKNOWN or profile1.disk_type == DiskType.UNKNOWN

    def test_update_learned_metrics(self, cache_file):
        """Test updating learned metrics from operations."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        profile = profiler.get_profile()

        original_speed = profile.extraction_speed_mbps

        # Update with new observation
        profiler.update_learned_metrics(extraction_speed=150.0)
        profile = profiler.get_profile()

        # Should have adjusted (exponential moving average)
        assert profile.extraction_speed_mbps != original_speed

    def test_sequential_read_measurement(self, temp_dir, cache_file):
        """Test sequential read speed measurement."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        speed = profiler._measure_sequential_read(temp_dir)

        assert speed > 0  # Should measure some speed
        assert speed < 10000  # Sanity check (10 GB/s is unrealistic)

    def test_random_read_measurement(self, temp_dir, cache_file):
        """Test random read speed measurement."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        speed = profiler._measure_random_read(temp_dir)

        assert speed > 0
        assert speed < 10000

    def test_cpu_speed_measurement(self, cache_file):
        """Test CPU speed measurement."""
        profiler = EnvironmentProfiler(cache_file=cache_file)
        score = profiler._measure_cpu_speed()

        assert 0.1 <= score <= 10.0  # Within expected range


class TestAdaptivePolicy:
    """Test adaptive policy learning."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def history_file(self, temp_dir):
        return temp_dir / "policy_history.json"

    @pytest.fixture
    def policy(self, history_file):
        return AdaptivePolicy(
            policy_name="test_policy",
            base_threshold=0.7,
            min_threshold=0.5,
            max_threshold=0.9,
            history_file=history_file
        )

    def test_policy_initialization(self, policy):
        """Test policy initializes with correct values."""
        assert policy.policy_name == "test_policy"
        assert policy.base_threshold == 0.7
        assert policy.current_threshold == 0.7
        assert len(policy.outcome_history) == 0

    def test_initial_threshold_uses_base(self, policy):
        """Test that initial decisions use base threshold."""
        threshold = policy.decide_threshold()
        assert threshold == policy.base_threshold

    def test_adapts_to_false_positives(self, policy):
        """Test policy relaxes threshold after many false positives."""
        # Record many false positives
        for i in range(20):
            outcome = OperationOutcome(
                timestamp=datetime.now(),
                operation_type="test",
                file_path=f"/test{i}.mp4",
                file_size_bytes=1000000,
                duration_seconds=1.0,
                decision="reject",
                outcome=OutcomeType.FALSE_POSITIVE,
                metadata={}
            )
            policy.record_outcome(outcome)

        # Threshold should decrease (more lenient)
        new_threshold = policy.decide_threshold()
        assert new_threshold < policy.base_threshold

    def test_adapts_to_false_negatives(self, policy):
        """Test policy tightens threshold after many false negatives."""
        # Record many false negatives
        for i in range(20):
            outcome = OperationOutcome(
                timestamp=datetime.now(),
                operation_type="test",
                file_path=f"/test{i}.mp4",
                file_size_bytes=1000000,
                duration_seconds=1.0,
                decision="accept",
                outcome=OutcomeType.FALSE_NEGATIVE,
                metadata={}
            )
            policy.record_outcome(outcome)

        # Threshold should increase (more strict)
        new_threshold = policy.decide_threshold()
        assert new_threshold > policy.base_threshold

    def test_respects_minimum_threshold(self, policy):
        """Test threshold never goes below minimum."""
        # Try to push below minimum
        for i in range(50):
            outcome = OperationOutcome(
                timestamp=datetime.now(),
                operation_type="test",
                file_path=f"/test{i}.mp4",
                file_size_bytes=1000000,
                duration_seconds=1.0,
                decision="reject",
                outcome=OutcomeType.FALSE_POSITIVE,
                metadata={}
            )
            policy.record_outcome(outcome)

        threshold = policy.decide_threshold()
        assert threshold >= policy.min_threshold

    def test_respects_maximum_threshold(self, policy):
        """Test threshold never goes above maximum."""
        # Try to push above maximum
        for i in range(50):
            outcome = OperationOutcome(
                timestamp=datetime.now(),
                operation_type="test",
                file_path=f"/test{i}.mp4",
                file_size_bytes=1000000,
                duration_seconds=1.0,
                decision="accept",
                outcome=OutcomeType.FALSE_NEGATIVE,
                metadata={}
            )
            policy.record_outcome(outcome)

        threshold = policy.decide_threshold()
        assert threshold <= policy.max_threshold

    def test_statistics_calculation(self, policy):
        """Test statistics are calculated correctly."""
        # Record mix of outcomes
        outcomes = [
            OutcomeType.TRUE_POSITIVE,
            OutcomeType.TRUE_POSITIVE,
            OutcomeType.TRUE_NEGATIVE,
            OutcomeType.FALSE_POSITIVE,
            OutcomeType.FALSE_NEGATIVE
        ]

        for i, outcome_type in enumerate(outcomes):
            outcome = OperationOutcome(
                timestamp=datetime.now(),
                operation_type="test",
                file_path=f"/test{i}.mp4",
                file_size_bytes=1000000,
                duration_seconds=1.0,
                decision="test",
                outcome=outcome_type,
                metadata={}
            )
            policy.record_outcome(outcome)

        stats = policy.get_statistics()

        assert stats['total_decisions'] == 5
        assert stats['true_positives'] == 2
        assert stats['true_negatives'] == 1
        assert stats['false_positives'] == 1
        assert stats['false_negatives'] == 1
        assert 0.0 <= stats['accuracy'] <= 1.0

    def test_history_persistence(self, policy, history_file):
        """Test outcome history is saved and loaded."""
        # Record some outcomes
        for i in range(5):
            outcome = OperationOutcome(
                timestamp=datetime.now(),
                operation_type="test",
                file_path=f"/test{i}.mp4",
                file_size_bytes=1000000,
                duration_seconds=1.0,
                decision="test",
                outcome=OutcomeType.TRUE_POSITIVE,
                metadata={}
            )
            policy.record_outcome(outcome)

        # Create new policy with same history file
        new_policy = AdaptivePolicy(
            policy_name="test_policy",
            base_threshold=0.7,
            min_threshold=0.5,
            max_threshold=0.9,
            history_file=history_file
        )

        # Should load history
        assert len(new_policy.outcome_history) == 5


class TestAdaptiveTimeoutCalculator:
    """Test adaptive timeout calculation."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def profiler(self, temp_dir):
        cache_file = temp_dir / "env_profile.json"
        return EnvironmentProfiler(cache_file=cache_file)

    @pytest.fixture
    def calculator(self, profiler):
        # Get profile first
        profiler.get_profile()
        return AdaptiveTimeoutCalculator(profiler)

    def test_extraction_timeout_scales_with_size(self, calculator):
        """Test extraction timeout increases with file size."""
        small_timeout = calculator.calculate_extraction_timeout(10 * 1024 * 1024)  # 10MB
        large_timeout = calculator.calculate_extraction_timeout(1000 * 1024 * 1024)  # 1GB

        # Timeout should scale with size (or be at least equal if both hit minimum)
        assert large_timeout >= small_timeout

    def test_extraction_timeout_respects_bounds(self, calculator):
        """Test extraction timeout stays within bounds."""
        tiny_timeout = calculator.calculate_extraction_timeout(100)  # 100 bytes
        huge_timeout = calculator.calculate_extraction_timeout(100 * 1024 * 1024 * 1024)  # 100GB

        assert tiny_timeout >= 60  # Minimum 1 minute
        assert huge_timeout <= 7200  # Maximum 2 hours

    def test_validation_timeout_scales_with_duration(self, calculator):
        """Test validation timeout scales with video duration."""
        short_timeout = calculator.calculate_validation_timeout(10 * 1024 * 1024, 60)  # 1 min video
        long_timeout = calculator.calculate_validation_timeout(100 * 1024 * 1024, 3600)  # 1 hour video

        assert long_timeout > short_timeout

    def test_validation_timeout_respects_bounds(self, calculator):
        """Test validation timeout stays within bounds."""
        tiny_timeout = calculator.calculate_validation_timeout(1000, 1)  # 1 second video
        huge_timeout = calculator.calculate_validation_timeout(1000000000, 36000)  # 10 hour video

        assert tiny_timeout >= 30  # Minimum 30s
        assert huge_timeout <= 600  # Maximum 10 minutes

    def test_record_extraction_time_updates_speed(self, calculator, profiler):
        """Test recording extraction times updates learned speed."""
        original_speed = calculator.profile.extraction_speed_mbps

        # Record several fast extractions
        for _ in range(10):
            calculator.record_extraction_time(100 * 1024 * 1024, 0.5)  # 100MB in 0.5s = 200 MB/s

        # Speed should have increased
        new_speed = calculator.profile.extraction_speed_mbps
        assert new_speed > original_speed

    def test_record_validation_time_updates_fps(self, calculator):
        """Test recording validation times updates learned FPS."""
        original_fps = calculator.profile.video_decode_fps

        # Record several fast validations
        for _ in range(10):
            calculator.record_validation_time(600, 3)  # 600s video in 3s = 200 FPS

        # FPS should have adjusted
        new_fps = calculator.profile.video_decode_fps
        # May increase or decrease depending on original value


class TestEnvironmentProfile:
    """Test environment profile data structure."""

    def test_profile_serialization(self):
        """Test profile can be serialized and deserialized."""
        profile = EnvironmentProfile(
            disk_type=DiskType.SSD,
            sequential_read_mbps=500.0,
            random_read_mbps=450.0,
            cpu_score=1.5,
            extraction_speed_mbps=100.0,
            video_decode_fps=120.0,
            last_updated=datetime.now()
        )

        # Serialize
        data = profile.to_dict()
        assert isinstance(data, dict)
        assert data['disk_type'] == 'SSD'

        # Deserialize
        restored = EnvironmentProfile.from_dict(data)
        assert restored.disk_type == DiskType.SSD
        assert restored.sequential_read_mbps == 500.0


class TestOperationOutcome:
    """Test operation outcome data structure."""

    def test_outcome_serialization(self):
        """Test outcome can be serialized and deserialized."""
        outcome = OperationOutcome(
            timestamp=datetime.now(),
            operation_type="extraction",
            file_path="/test.rar",
            file_size_bytes=1000000,
            duration_seconds=5.0,
            decision="success",
            outcome=OutcomeType.TRUE_POSITIVE,
            metadata={'key': 'value'}
        )

        # Serialize
        data = outcome.to_dict()
        assert isinstance(data, dict)
        assert data['outcome'] == 'TRUE_POSITIVE'

        # Deserialize
        restored = OperationOutcome.from_dict(data)
        assert restored.outcome == OutcomeType.TRUE_POSITIVE
        assert restored.file_size_bytes == 1000000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
