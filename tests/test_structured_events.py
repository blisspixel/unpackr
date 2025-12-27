"""
Test suite for structured_events module.

Tests cover:
- Event creation and serialization
- Event emission to multiple sinks
- Event querying and filtering
- Event analysis
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.structured_events import (
    StructuredEvent,
    EventType,
    EventSeverity,
    EventEmitter,
    EventBuilder,
    EventAnalyzer
)


class TestStructuredEvent:
    """Test structured event data structure."""

    def test_event_creation(self):
        """Test creating a structured event."""
        event = StructuredEvent(
            event_id="test123",
            event_type=EventType.VIDEO_DISCOVERED,
            timestamp=datetime.now(),
            severity=EventSeverity.INFO,
            message="Test message",
            context={'path': '/test.mp4'},
            metadata={'size': 1000}
        )

        assert event.event_id == "test123"
        assert event.event_type == EventType.VIDEO_DISCOVERED
        assert event.severity == EventSeverity.INFO
        assert event.context['path'] == '/test.mp4'

    def test_event_serialization(self):
        """Test event serialization to dict/JSON."""
        event = StructuredEvent(
            event_id="test123",
            event_type=EventType.VIDEO_DISCOVERED,
            timestamp=datetime.now(),
            severity=EventSeverity.INFO,
            message="Test message",
            context={'path': '/test.mp4'}
        )

        # To dict
        data = event.to_dict()
        assert isinstance(data, dict)
        assert data['event_type'] == 'VIDEO_DISCOVERED'
        assert data['severity'] == 'INFO'

        # To JSON
        json_str = event.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed['event_id'] == "test123"

    def test_event_deserialization(self):
        """Test event deserialization from dict."""
        data = {
            'event_id': 'test123',
            'event_type': 'VIDEO_DISCOVERED',
            'timestamp': datetime.now().isoformat(),
            'severity': 'INFO',
            'message': 'Test message',
            'context': {'path': '/test.mp4'},
            'metadata': {},
            'session_id': 'session1',
            'parent_event_id': None
        }

        event = StructuredEvent.from_dict(data)
        assert event.event_id == 'test123'
        assert event.event_type == EventType.VIDEO_DISCOVERED
        assert event.severity == EventSeverity.INFO


class TestEventEmitter:
    """Test event emission."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def log_file(self, temp_dir):
        return temp_dir / "events.jsonl"

    @pytest.fixture
    def emitter(self, log_file):
        return EventEmitter(
            log_file=log_file,
            session_id="test_session",
            enable_console=False,  # Disable for testing
            enable_file=True
        )

    def test_emitter_initialization(self, emitter, log_file):
        """Test emitter initializes correctly."""
        assert emitter.log_file == log_file
        assert emitter.session_id == "test_session"
        assert len(emitter.event_buffer) == 0

    def test_emit_event(self, emitter):
        """Test emitting a single event."""
        event = emitter.emit(
            EventType.VIDEO_DISCOVERED,
            "Test video discovered",
            severity=EventSeverity.INFO,
            context={'path': '/test.mp4'}
        )

        assert event is not None
        assert event.event_type == EventType.VIDEO_DISCOVERED
        assert event.session_id == "test_session"
        assert len(emitter.event_buffer) == 1

    def test_emit_to_file(self, emitter, log_file):
        """Test events are written to file."""
        emitter.emit(
            EventType.VIDEO_DISCOVERED,
            "Test video",
            context={'path': '/test.mp4'}
        )

        # File should exist and contain JSON line
        assert log_file.exists()
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data['event_type'] == 'VIDEO_DISCOVERED'

    def test_multiple_events(self, emitter):
        """Test emitting multiple events."""
        for i in range(5):
            emitter.emit(
                EventType.VIDEO_DISCOVERED,
                f"Video {i}",
                context={'path': f'/test{i}.mp4'}
            )

        assert len(emitter.event_buffer) == 5
        assert len(emitter.get_session_events()) == 5

    def test_query_by_event_type(self, emitter):
        """Test querying events by type."""
        emitter.emit(EventType.VIDEO_DISCOVERED, "Video 1")
        emitter.emit(EventType.ARCHIVE_DISCOVERED, "Archive 1")
        emitter.emit(EventType.VIDEO_DISCOVERED, "Video 2")

        videos = emitter.query_events(event_type=EventType.VIDEO_DISCOVERED)
        assert len(videos) == 2

        archives = emitter.query_events(event_type=EventType.ARCHIVE_DISCOVERED)
        assert len(archives) == 1

    def test_query_by_severity(self, emitter):
        """Test querying events by severity."""
        emitter.emit(EventType.VIDEO_DISCOVERED, "Info", severity=EventSeverity.INFO)
        emitter.emit(EventType.VIDEO_VALIDATION_FAILED, "Error", severity=EventSeverity.ERROR)
        emitter.emit(EventType.VIDEO_DISCOVERED, "Info 2", severity=EventSeverity.INFO)

        errors = emitter.query_events(severity=EventSeverity.ERROR)
        assert len(errors) == 1

        infos = emitter.query_events(severity=EventSeverity.INFO)
        assert len(infos) == 2

    def test_query_by_time_range(self, emitter):
        """Test querying events by time range."""
        now = datetime.now()

        # Emit events with different timestamps
        emitter.emit(EventType.VIDEO_DISCOVERED, "Old event")
        emitter.event_buffer[-1].timestamp = now - timedelta(hours=2)

        emitter.emit(EventType.VIDEO_DISCOVERED, "Recent event")
        emitter.event_buffer[-1].timestamp = now - timedelta(minutes=5)

        emitter.emit(EventType.VIDEO_DISCOVERED, "Current event")

        # Query last hour
        recent = emitter.query_events(since=now - timedelta(hours=1))
        assert len(recent) == 2

    def test_parent_event_tracking(self, emitter):
        """Test parent-child event relationships."""
        parent = emitter.emit(EventType.ARCHIVE_EXTRACTION_STARTED, "Parent")

        child1 = emitter.emit(
            EventType.VIDEO_DISCOVERED,
            "Child 1",
            parent_event_id=parent.event_id
        )
        child2 = emitter.emit(
            EventType.VIDEO_DISCOVERED,
            "Child 2",
            parent_event_id=parent.event_id
        )

        assert child1.parent_event_id == parent.event_id
        assert child2.parent_event_id == parent.event_id


class TestEventBuilder:
    """Test event builder convenience methods."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def builder(self, temp_dir):
        log_file = temp_dir / "events.jsonl"
        emitter = EventEmitter(log_file=log_file, enable_console=False)
        return EventBuilder(emitter)

    def test_archive_discovered(self, builder):
        """Test archive discovered event builder."""
        event = builder.archive_discovered(Path("/test.rar"), 1000000)

        assert event.event_type == EventType.ARCHIVE_DISCOVERED
        assert event.context['path'] == str(Path("/test.rar"))
        assert event.context['size_bytes'] == 1000000

    def test_archive_extraction_events(self, builder):
        """Test archive extraction event chain."""
        started = builder.archive_extraction_started(Path("/test.rar"), timeout=300)
        assert started.event_type == EventType.ARCHIVE_EXTRACTION_STARTED
        assert started.context['timeout_seconds'] == 300

        completed = builder.archive_extraction_completed(
            Path("/test.rar"),
            duration=10.5,
            files_extracted=15,
            parent_event_id=started.event_id
        )
        assert completed.event_type == EventType.ARCHIVE_EXTRACTION_COMPLETED
        assert completed.parent_event_id == started.event_id
        assert completed.context['files_extracted'] == 15

    def test_video_validation_events(self, builder):
        """Test video validation event chain."""
        started = builder.video_validation_started(Path("/test.mp4"))
        assert started.event_type == EventType.VIDEO_VALIDATION_STARTED

        passed = builder.video_validation_passed(
            Path("/test.mp4"),
            duration=600.0,
            resolution="1920x1080",
            bitrate=2500,
            parent_event_id=started.event_id
        )
        assert passed.event_type == EventType.VIDEO_VALIDATION_PASSED
        assert passed.context['resolution'] == "1920x1080"

    def test_safety_invariant_violated(self, builder):
        """Test safety violation event."""
        event = builder.safety_invariant_violated(
            "I2_video_protection",
            "delete",
            "Attempted to delete validated video"
        )

        assert event.event_type == EventType.SAFETY_INVARIANT_VIOLATED
        assert event.severity == EventSeverity.CRITICAL
        assert event.context['invariant'] == "I2_video_protection"

    def test_disk_space_warning(self, builder):
        """Test disk space warning event."""
        event = builder.disk_space_warning(
            Path("/destination"),
            available_bytes=1_000_000_000,  # 1GB
            required_bytes=5_000_000_000    # 5GB
        )

        assert event.event_type == EventType.DISK_SPACE_WARNING
        assert event.severity == EventSeverity.WARNING
        assert event.context['available_gb'] < event.context['required_gb']

    def test_session_events(self, builder):
        """Test session start/complete events."""
        started = builder.session_started(Path("/source"), Path("/destination"))
        assert started.event_type == EventType.SESSION_STARTED

        completed = builder.session_completed(
            duration=120.5,
            files_processed=50,
            files_moved=45,
            files_deleted=5
        )
        assert completed.event_type == EventType.SESSION_COMPLETED
        assert completed.context['files_processed'] == 50


class TestEventAnalyzer:
    """Test event log analysis."""

    @pytest.fixture
    def temp_dir(self):
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def log_file_with_events(self, temp_dir):
        """Create log file with sample events."""
        log_file = temp_dir / "events.jsonl"
        emitter = EventEmitter(log_file=log_file, enable_console=False)
        builder = EventBuilder(emitter)

        # Create sample events
        for i in range(10):
            builder.video_validation_started(Path(f"/test{i}.mp4"))

            if i < 8:
                # 8 pass
                builder.video_validation_passed(
                    Path(f"/test{i}.mp4"),
                    duration=600.0,
                    resolution="1920x1080",
                    bitrate=2500
                )
            else:
                # 2 fail
                builder.video_validation_failed(
                    Path(f"/test{i}.mp4"),
                    reason="corrupt"
                )

        return log_file

    @pytest.fixture
    def analyzer(self, log_file_with_events):
        analyzer = EventAnalyzer(log_file_with_events)
        analyzer.load_events()
        return analyzer

    def test_load_events(self, analyzer):
        """Test loading events from file."""
        assert len(analyzer.events) > 0

    def test_success_rate_calculation(self, analyzer):
        """Test success rate calculation."""
        # Should be 80% (8 passed, 2 failed)
        success_rate = analyzer.get_success_rate("VIDEO_VALIDATION")
        assert 0.7 < success_rate < 0.9  # Approximately 80%

    def test_error_summary(self, analyzer):
        """Test error summary generation."""
        summary = analyzer.get_error_summary()

        # Should have failures but no critical errors in our sample data
        # (Failed validations are warnings, not errors)
        # So summary might be empty or have warnings
        assert isinstance(summary, dict)

    def test_average_duration(self, temp_dir):
        """Test average duration calculation."""
        log_file = temp_dir / "duration_test.jsonl"
        emitter = EventEmitter(log_file=log_file, enable_console=False)
        builder = EventBuilder(emitter)

        # Create events with known durations
        for duration in [5.0, 10.0, 15.0]:
            builder.archive_extraction_completed(
                Path("/test.rar"),
                duration=duration,
                files_extracted=10
            )

        analyzer = EventAnalyzer(log_file)
        analyzer.load_events()

        avg = analyzer.get_average_duration(EventType.ARCHIVE_EXTRACTION_COMPLETED)
        assert avg == 10.0  # Average of 5, 10, 15

    def test_performance_degradation_detection(self, temp_dir):
        """Test performance degradation detection."""
        log_file = temp_dir / "perf_test.jsonl"
        emitter = EventEmitter(log_file=log_file, enable_console=False)
        builder = EventBuilder(emitter)

        # Create events: first 10 fast, next 10 slow
        for i in range(10):
            builder.archive_extraction_completed(
                Path(f"/test{i}.rar"),
                duration=5.0,  # Fast
                files_extracted=10
            )

        for i in range(10, 20):
            builder.archive_extraction_completed(
                Path(f"/test{i}.rar"),
                duration=20.0,  # Slow (4x slower)
                files_extracted=10
            )

        analyzer = EventAnalyzer(log_file)
        analyzer.load_events()

        # Should detect degradation
        degraded = analyzer.detect_performance_degradation(
            EventType.ARCHIVE_EXTRACTION_COMPLETED,
            window_size=10
        )
        assert degraded is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
