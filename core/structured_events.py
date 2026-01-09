"""
Structured Event Logging System

Replaces string-based logging with structured events that are:
- Machine-readable (JSON)
- Queryable and analyzable
- Type-safe
- Consistent format

Design Philosophy:
- Every significant operation emits structured events
- Events include context, timing, outcomes
- Events are append-only (never modified)
- Events support telemetry and analytics

References:
- docs/DEEP_ANALYSIS.md - Structured Events section
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum, auto
import uuid


logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events that can occur."""
    # Archive operations
    ARCHIVE_DISCOVERED = auto()
    ARCHIVE_VALIDATION_STARTED = auto()
    ARCHIVE_VALIDATION_PASSED = auto()
    ARCHIVE_VALIDATION_FAILED = auto()
    ARCHIVE_EXTRACTION_STARTED = auto()
    ARCHIVE_EXTRACTION_COMPLETED = auto()
    ARCHIVE_EXTRACTION_FAILED = auto()
    ARCHIVE_DELETED = auto()

    # PAR2 operations
    PAR2_REPAIR_STARTED = auto()
    PAR2_REPAIR_COMPLETED = auto()
    PAR2_REPAIR_FAILED = auto()

    # Video operations
    VIDEO_DISCOVERED = auto()
    VIDEO_VALIDATION_STARTED = auto()
    VIDEO_VALIDATION_PASSED = auto()
    VIDEO_VALIDATION_FAILED = auto()
    VIDEO_MOVED = auto()
    VIDEO_DELETED = auto()

    # File operations
    FILE_SANITIZED = auto()
    FILE_MOVED = auto()
    FILE_DELETED = auto()
    FOLDER_CLEANED = auto()
    FOLDER_DELETED = auto()

    # Safety and errors
    SAFETY_INVARIANT_VIOLATED = auto()
    DISK_SPACE_WARNING = auto()
    PERMISSION_DENIED = auto()
    OPERATION_TIMEOUT = auto()

    # Adaptive learning
    POLICY_THRESHOLD_ADJUSTED = auto()
    ENVIRONMENT_PROFILED = auto()
    OUTCOME_RECORDED = auto()

    # Session tracking
    SESSION_STARTED = auto()
    SESSION_COMPLETED = auto()
    SESSION_FAILED = auto()


class EventSeverity(Enum):
    """Severity levels for events."""
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class StructuredEvent:
    """
    A structured event with consistent format.

    All events have these core fields plus event-specific data.
    """
    event_id: str
    event_type: EventType
    timestamp: datetime
    severity: EventSeverity
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    parent_event_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.name,
            'timestamp': self.timestamp.isoformat(),
            'severity': self.severity.name,
            'message': self.message,
            'context': self.context,
            'metadata': self.metadata,
            'session_id': self.session_id,
            'parent_event_id': self.parent_event_id
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> 'StructuredEvent':
        """Create from dictionary."""
        data = data.copy()
        data['event_type'] = EventType[data['event_type']]
        data['severity'] = EventSeverity[data['severity']]
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class EventEmitter:
    """
    Emits structured events to various sinks.

    Sinks can include:
    - File (JSON lines)
    - Standard logging
    - In-memory buffer
    - External services (future)
    """

    def __init__(
        self,
        log_file: Optional[Path] = None,
        session_id: Optional[str] = None,
        enable_console: bool = True,
        enable_file: bool = True
    ):
        """
        Initialize event emitter.

        Args:
            log_file: Path to event log file (JSON lines format)
            session_id: Session identifier for grouping events
            enable_console: Emit to console via standard logging
            enable_file: Emit to file
        """
        self.log_file = log_file or (
            Path.home() / '.unpackr' / 'events.jsonl'
        )
        self.session_id = session_id or str(uuid.uuid4())
        self.enable_console = enable_console
        self.enable_file = enable_file

        # In-memory buffer for current session
        self.event_buffer: List[StructuredEvent] = []

        # Ensure log directory exists
        if self.enable_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        event_type: EventType,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        context: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """
        Emit a structured event.

        Args:
            event_type: Type of event
            message: Human-readable message
            severity: Event severity
            context: Context data (operation-specific)
            metadata: Additional metadata
            parent_event_id: ID of parent event (for event chains)

        Returns:
            The emitted event
        """
        event = StructuredEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(),
            severity=severity,
            message=message,
            context=context or {},
            metadata=metadata or {},
            session_id=self.session_id,
            parent_event_id=parent_event_id
        )

        # Add to buffer
        self.event_buffer.append(event)

        # Emit to console
        if self.enable_console:
            self._emit_to_console(event)

        # Emit to file
        if self.enable_file:
            self._emit_to_file(event)

        return event

    def _emit_to_console(self, event: StructuredEvent):
        """Emit event to console via standard logging."""
        # Map severity to logging level
        level_map = {
            EventSeverity.DEBUG: logging.DEBUG,
            EventSeverity.INFO: logging.INFO,
            EventSeverity.WARNING: logging.WARNING,
            EventSeverity.ERROR: logging.ERROR,
            EventSeverity.CRITICAL: logging.CRITICAL
        }

        log_level = level_map.get(event.severity, logging.INFO)

        # Format message with context
        context_str = ""
        if event.context:
            key_context = {k: v for k, v in event.context.items() if k in ['path', 'size', 'duration']}
            if key_context:
                context_str = " | " + ", ".join(f"{k}={v}" for k, v in key_context.items())

        logger.log(
            log_level,
            f"[{event.event_type.name}] {event.message}{context_str}"
        )

    def _emit_to_file(self, event: StructuredEvent):
        """Emit event to JSON lines file."""
        try:
            with open(self.log_file, 'a') as f:
                f.write(event.to_json() + '\n')
        except Exception as e:
            logger.error(f"Failed to write event to file: {e}")

    def get_session_events(self) -> List[StructuredEvent]:
        """Get all events for current session."""
        return self.event_buffer.copy()

    def query_events(
        self,
        event_type: Optional[EventType] = None,
        severity: Optional[EventSeverity] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> List[StructuredEvent]:
        """
        Query events with filters.

        Args:
            event_type: Filter by event type
            severity: Filter by severity
            since: Events after this timestamp
            until: Events before this timestamp

        Returns:
            Filtered list of events
        """
        filtered = self.event_buffer

        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]

        if severity:
            filtered = [e for e in filtered if e.severity == severity]

        if since:
            filtered = [e for e in filtered if e.timestamp >= since]

        if until:
            filtered = [e for e in filtered if e.timestamp <= until]

        return filtered


class EventBuilder:
    """
    Builder for creating common event patterns.

    Provides convenience methods for typical events with consistent formatting.
    """

    def __init__(self, emitter: EventEmitter):
        """
        Initialize event builder.

        Args:
            emitter: Event emitter to use
        """
        self.emitter = emitter

    # Archive events

    def archive_discovered(self, path: Path, size: int) -> StructuredEvent:
        """Emit archive discovered event."""
        return self.emitter.emit(
            EventType.ARCHIVE_DISCOVERED,
            f"Discovered archive: {path.name}",
            severity=EventSeverity.DEBUG,
            context={
                'path': str(path),
                'size_bytes': size,
                'size_mb': size / (1024 * 1024)
            }
        )

    def archive_extraction_started(
        self,
        path: Path,
        timeout: int,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """Emit archive extraction started event."""
        return self.emitter.emit(
            EventType.ARCHIVE_EXTRACTION_STARTED,
            f"Extracting archive: {path.name}",
            severity=EventSeverity.INFO,
            context={
                'path': str(path),
                'timeout_seconds': timeout
            },
            parent_event_id=parent_event_id
        )

    def archive_extraction_completed(
        self,
        path: Path,
        duration: float,
        files_extracted: int,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """Emit archive extraction completed event."""
        # Calculate extraction speed if file exists and duration > 0
        try:
            extraction_speed = (path.stat().st_size / (1024 * 1024)) / duration if duration > 0 else 0
        except (FileNotFoundError, OSError):
            extraction_speed = 0
        
        return self.emitter.emit(
            EventType.ARCHIVE_EXTRACTION_COMPLETED,
            f"Extracted {files_extracted} files from {path.name}",
            severity=EventSeverity.INFO,
            context={
                'path': str(path),
                'duration_seconds': duration,
                'files_extracted': files_extracted
            },
            metadata={
                'extraction_speed_mbps': extraction_speed
            },
            parent_event_id=parent_event_id
        )

    def archive_extraction_failed(
        self,
        path: Path,
        error: str,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """Emit archive extraction failed event."""
        return self.emitter.emit(
            EventType.ARCHIVE_EXTRACTION_FAILED,
            f"Failed to extract {path.name}: {error}",
            severity=EventSeverity.ERROR,
            context={
                'path': str(path),
                'error': error
            },
            parent_event_id=parent_event_id
        )

    # Video events

    def video_discovered(self, path: Path, size: int) -> StructuredEvent:
        """Emit video discovered event."""
        return self.emitter.emit(
            EventType.VIDEO_DISCOVERED,
            f"Discovered video: {path.name}",
            severity=EventSeverity.DEBUG,
            context={
                'path': str(path),
                'size_bytes': size,
                'size_mb': size / (1024 * 1024)
            }
        )

    def video_validation_started(
        self,
        path: Path,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """Emit video validation started event."""
        return self.emitter.emit(
            EventType.VIDEO_VALIDATION_STARTED,
            f"Validating video: {path.name}",
            severity=EventSeverity.DEBUG,
            context={'path': str(path)},
            parent_event_id=parent_event_id
        )

    def video_validation_passed(
        self,
        path: Path,
        duration: float,
        resolution: str,
        bitrate: int,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """Emit video validation passed event."""
        return self.emitter.emit(
            EventType.VIDEO_VALIDATION_PASSED,
            f"Video validation passed: {path.name}",
            severity=EventSeverity.INFO,
            context={
                'path': str(path),
                'duration_seconds': duration,
                'resolution': resolution,
                'bitrate_kbps': bitrate
            },
            parent_event_id=parent_event_id
        )

    def video_validation_failed(
        self,
        path: Path,
        reason: str,
        parent_event_id: Optional[str] = None
    ) -> StructuredEvent:
        """Emit video validation failed event."""
        return self.emitter.emit(
            EventType.VIDEO_VALIDATION_FAILED,
            f"Video validation failed: {path.name} - {reason}",
            severity=EventSeverity.WARNING,
            context={
                'path': str(path),
                'failure_reason': reason
            },
            parent_event_id=parent_event_id
        )

    # Safety events

    def safety_invariant_violated(
        self,
        invariant_name: str,
        operation: str,
        details: str
    ) -> StructuredEvent:
        """Emit safety invariant violation event."""
        return self.emitter.emit(
            EventType.SAFETY_INVARIANT_VIOLATED,
            f"SAFETY VIOLATION: {invariant_name} - {details}",
            severity=EventSeverity.CRITICAL,
            context={
                'invariant': invariant_name,
                'operation': operation,
                'details': details
            }
        )

    def disk_space_warning(
        self,
        path: Path,
        available_bytes: int,
        required_bytes: int
    ) -> StructuredEvent:
        """Emit disk space warning event."""
        return self.emitter.emit(
            EventType.DISK_SPACE_WARNING,
            f"Low disk space: {available_bytes / (1024**3):.1f} GB available",
            severity=EventSeverity.WARNING,
            context={
                'path': str(path),
                'available_bytes': available_bytes,
                'required_bytes': required_bytes,
                'available_gb': available_bytes / (1024**3),
                'required_gb': required_bytes / (1024**3)
            }
        )

    # Adaptive learning events

    def policy_threshold_adjusted(
        self,
        policy_name: str,
        old_threshold: float,
        new_threshold: float,
        reason: str
    ) -> StructuredEvent:
        """Emit policy threshold adjustment event."""
        return self.emitter.emit(
            EventType.POLICY_THRESHOLD_ADJUSTED,
            f"Policy {policy_name} adjusted: {old_threshold:.3f} → {new_threshold:.3f}",
            severity=EventSeverity.INFO,
            context={
                'policy_name': policy_name,
                'old_threshold': old_threshold,
                'new_threshold': new_threshold,
                'reason': reason
            }
        )

    def environment_profiled(
        self,
        disk_type: str,
        sequential_speed: float,
        random_speed: float
    ) -> StructuredEvent:
        """Emit environment profiling completed event."""
        return self.emitter.emit(
            EventType.ENVIRONMENT_PROFILED,
            f"Environment profiled: {disk_type} disk",
            severity=EventSeverity.INFO,
            context={
                'disk_type': disk_type,
                'sequential_read_mbps': sequential_speed,
                'random_read_mbps': random_speed
            }
        )

    # Session events

    def session_started(self, source_path: Path, destination_path: Path) -> StructuredEvent:
        """Emit session started event."""
        return self.emitter.emit(
            EventType.SESSION_STARTED,
            f"Processing session started",
            severity=EventSeverity.INFO,
            context={
                'source': str(source_path),
                'destination': str(destination_path),
                'session_id': self.emitter.session_id
            }
        )

    def session_completed(
        self,
        duration: float,
        files_processed: int,
        files_moved: int,
        files_deleted: int
    ) -> StructuredEvent:
        """Emit session completed event."""
        return self.emitter.emit(
            EventType.SESSION_COMPLETED,
            f"Session completed: {files_processed} files processed in {duration:.1f}s",
            severity=EventSeverity.INFO,
            context={
                'duration_seconds': duration,
                'files_processed': files_processed,
                'files_moved': files_moved,
                'files_deleted': files_deleted,
                'session_id': self.emitter.session_id
            }
        )


class EventAnalyzer:
    """
    Analyzes event logs for insights and patterns.

    Can detect:
    - Performance degradation
    - Error patterns
    - Success/failure rates
    - Operation timing trends
    """

    def __init__(self, log_file: Path):
        """
        Initialize event analyzer.

        Args:
            log_file: Path to event log file (JSON lines)
        """
        self.log_file = log_file
        self.events: List[StructuredEvent] = []

    def load_events(self, since: Optional[datetime] = None):
        """
        Load events from log file.

        Args:
            since: Only load events after this timestamp
        """
        self.events = []

        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        event = StructuredEvent.from_dict(data)

                        if since and event.timestamp < since:
                            continue

                        self.events.append(event)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue  # Skip malformed lines

            logger.info(f"Loaded {len(self.events)} events")
        except Exception as e:
            logger.error(f"Failed to load events: {e}")

    def get_success_rate(self, event_type_prefix: str) -> float:
        """
        Calculate success rate for operations.

        Args:
            event_type_prefix: Prefix to match (e.g., 'VIDEO_VALIDATION')

        Returns:
            Success rate (0.0 to 1.0) based on terminal states (passed/completed vs failed)
        """
        relevant_events = [
            e for e in self.events
            if e.event_type.name.startswith(event_type_prefix)
        ]

        if not relevant_events:
            return 0.0

        # Count only terminal states for meaningful success rate
        passed = sum(
            1 for e in relevant_events
            if 'COMPLETED' in e.event_type.name or 'PASSED' in e.event_type.name
        )
        failed = sum(
            1 for e in relevant_events
            if 'FAILED' in e.event_type.name
        )
        
        total_terminal = passed + failed
        if total_terminal == 0:
            return 0.0

        return passed / total_terminal

    def get_average_duration(self, event_type: EventType) -> Optional[float]:
        """
        Get average duration for completed operations.

        Args:
            event_type: Type of event to analyze

        Returns:
            Average duration in seconds, or None if no data
        """
        relevant_events = [
            e for e in self.events
            if e.event_type == event_type and 'duration_seconds' in e.context
        ]

        if not relevant_events:
            return None

        durations = [e.context['duration_seconds'] for e in relevant_events]
        return sum(durations) / len(durations)

    def get_error_summary(self) -> Dict[str, int]:
        """
        Get summary of errors by type.

        Returns:
            Dictionary mapping error types to counts
        """
        error_events = [
            e for e in self.events
            if e.severity in (EventSeverity.ERROR, EventSeverity.CRITICAL)
        ]

        summary = {}
        for event in error_events:
            event_type = event.event_type.name
            summary[event_type] = summary.get(event_type, 0) + 1

        return summary

    def detect_performance_degradation(
        self,
        event_type: EventType,
        window_size: int = 10
    ) -> bool:
        """
        Detect if operation is getting slower over time.

        Args:
            event_type: Type of operation to monitor
            window_size: Number of recent operations to compare

        Returns:
            True if performance degrading
        """
        relevant_events = [
            e for e in self.events
            if e.event_type == event_type and 'duration_seconds' in e.context
        ]

        if len(relevant_events) < window_size * 2:
            return False  # Not enough data

        # Compare recent window to earlier window
        recent = relevant_events[-window_size:]
        earlier = relevant_events[-window_size*2:-window_size]

        recent_avg = sum(e.context['duration_seconds'] for e in recent) / len(recent)
        earlier_avg = sum(e.context['duration_seconds'] for e in earlier) / len(earlier)

        # Consider degraded if 50% slower
        return recent_avg > earlier_avg * 1.5
