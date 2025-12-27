# Deep Analysis: Elevating Unpackr to Research-Grade Software

## Executive Summary

Unpackr is already well-designed with solid defensive programming, comprehensive testing, and clear safety guarantees. To elevate it from "good production software" to "PhD-level research-grade software," we need to focus on three dimensions:

1. **Theoretical Soundness** - Formal reasoning about correctness
2. **Adaptive Intelligence** - Self-improving behavior from empirical feedback
3. **Systematic Defensiveness** - Exhaustive failure mode analysis and mitigation

This document provides detailed analysis of each dimension and actionable next steps.

---

## Part 1: Current State Assessment

### Strengths (What's Already Excellent)

**1. Safety-First Architecture**
- Fail-closed validation (when uncertain, reject)
- Path traversal protection
- Command injection prevention
- Double-check pattern before deletion
- Comprehensive logging with attribution

**2. Modern Software Engineering**
- 100% test pass rate (94 tests)
- Type hints and defensive validation
- Thread-safe operations
- Atomic file operations (temp + rename)
- Privacy-aware design (hashed paths by default)

**3. User-Centric Design**
- Clear mental model (inputs → pipeline → outputs)
- Dry-run mode for validation
- Progressive cleanup (work saved even if cancelled)
- Explainable actions (logs show WHY decisions were made)

### Gaps (Where PhD-Level Thinking Would Help)

**1. Lack of Formal Verification**
- Safety guarantees are tested but not *proven*
- No mathematical model of state transitions
- Invariants are implicit, not explicit and checked

**2. Static Decision Logic**
- Video validation uses fixed heuristics
- No learning from outcomes (was that truncation detection accurate?)
- No adaptation to user's environment (HDD vs SSD, network drives)

**3. Incomplete Failure Mode Analysis**
- Error handling is reactive (crash → fix → deploy)
- No systematic enumeration of failure modes
- No proactive fault injection testing

---

## Part 2: Theoretical Soundness

### Problem: Implicit vs Explicit Guarantees

**Current approach:** Safety Contract is documented prose
```markdown
**Guarantees:**
- Never writes outside destination directory
- Never deletes content folders
- Never moves videos that fail validation
```

**PhD approach:** Formal invariants as executable predicates
```python
class SafetyInvariants:
    """Executable predicates that MUST hold true at all times."""

    @staticmethod
    def never_write_outside_destination(operation: FileOperation) -> bool:
        """I1: All writes target destination root or subdirectories."""
        if operation.type == "WRITE":
            return operation.path.resolve().is_relative_to(DESTINATION_ROOT)
        return True

    @staticmethod
    def never_delete_validated_video(operation: FileOperation) -> bool:
        """I2: Videos that passed validation are only MOVED, never DELETED."""
        if operation.type == "DELETE" and operation.target.is_video():
            validation_result = ValidationCache.get(operation.target)
            return validation_result is None or validation_result.decision != "PASS"
        return True

    @staticmethod
    def content_folders_preserved(operation: FileOperation) -> bool:
        """I3: Folders meeting preservation thresholds are never deleted."""
        if operation.type == "DELETE_FOLDER":
            folder = operation.target
            return not (
                folder.music_file_count >= config.min_music_files or
                (folder.image_file_count >= config.min_image_files and
                 folder.image_total_bytes >= 10_485_760) or
                folder.document_count >= config.min_documents
            )
        return True

# Runtime verification - check before EVERY destructive operation
def execute_operation(op: FileOperation):
    # Pre-condition check
    for invariant_check in SafetyInvariants.__dict__.values():
        if callable(invariant_check) and not invariant_check.__name__.startswith('_'):
            if not invariant_check(op):
                raise InvariantViolation(f"Invariant {invariant_check.__name__} violated")

    # Execute
    op.execute()

    # Post-condition check (verify outcome matches intent)
    op.verify_postcondition()
```

**Benefits:**
- **Testability**: Run invariant checks in CI/CD on every operation in test suite
- **Debugging**: Violations pinpoint exactly which guarantee was broken
- **Documentation**: Invariants are both specification AND runtime checks
- **Confidence**: If invariants pass after 10,000 test operations, safety is *demonstrated*, not just asserted

### State Machine Modeling

**Current:** Implicit state transitions in folder processing
**PhD:** Explicit FSM with proven reachability properties

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional

class FolderState(Enum):
    """Explicit states in folder processing lifecycle."""
    DISCOVERED = auto()
    SCANNING = auto()
    CLASSIFYING = auto()
    PROCESSING = auto()
    VALIDATED = auto()
    CLEANED = auto()
    DELETED = auto()
    PRESERVED = auto()
    ERROR = auto()

class FolderStateMachine:
    """Explicit state machine with validated transitions."""

    ALLOWED_TRANSITIONS = {
        FolderState.DISCOVERED: {FolderState.SCANNING, FolderState.ERROR},
        FolderState.SCANNING: {FolderState.CLASSIFYING, FolderState.ERROR},
        FolderState.CLASSIFYING: {FolderState.PROCESSING, FolderState.PRESERVED, FolderState.ERROR},
        FolderState.PROCESSING: {FolderState.VALIDATED, FolderState.ERROR},
        FolderState.VALIDATED: {FolderState.CLEANED, FolderState.ERROR},
        FolderState.CLEANED: {FolderState.DELETED, FolderState.PRESERVED, FolderState.ERROR},
        # Terminal states
        FolderState.DELETED: set(),
        FolderState.PRESERVED: set(),
        FolderState.ERROR: set(),
    }

    def transition(self, folder: Folder, to_state: FolderState, reason: str):
        """State transition with validation."""
        current = folder.state

        # Validate transition is legal
        if to_state not in self.ALLOWED_TRANSITIONS.get(current, set()):
            raise IllegalStateTransition(
                f"Cannot transition from {current} to {to_state}. "
                f"Allowed: {self.ALLOWED_TRANSITIONS[current]}"
            )

        # Log transition for audit trail
        self.event_log.record(StateTransition(
            folder_id=folder.id,
            from_state=current,
            to_state=to_state,
            timestamp=now(),
            reason=reason
        ))

        folder.state = to_state

    def verify_terminal_state_reachable(self):
        """Prove every folder reaches a terminal state (DELETED, PRESERVED, or ERROR)."""
        # Analyze state graph: ensure no cycles except ERROR self-loop
        # Run model checker to verify: forall folders, eventually(terminal_state)
        pass
```

**Benefits:**
- **Illegal transitions impossible**: Can't accidentally delete folder that was never validated
- **Debugging**: State history shows exactly what happened
- **Testing**: Can verify all state transitions are tested
- **Proof**: Can formally verify "every folder reaches terminal state" (no infinite loops)

### Proof-Carrying Code

**Concept:** Attach machine-checkable proofs to critical operations

```python
@requires(lambda self: self.video.validation_state == ValidationState.PASSED)
@ensures(lambda self, result: result.success implies self.video.path_at_destination())
def move_video_to_destination(self, video: Video) -> MoveResult:
    """Move video to destination. Proven to only move validated videos."""
    # Precondition enforced by @requires
    # Postcondition verified by @ensures
    ...
```

**Tools:**
- `icontract` library for runtime contract checking
- `mypy` with strict mode for static verification
- Custom invariant checker that runs before/after operations

---

## Part 2: Adaptive Intelligence

### Problem: Static Heuristics Don't Adapt

**Current:**
- Video truncation threshold: fixed 70% of expected size
- Timeout calculation: fixed formula based on file size
- Sample detection: fixed 50MB threshold

**What if:**
- Your hardware is faster than assumed (wasting time with too-long timeouts)
- Your downloads are consistently truncated at 65% (threshold should adapt)
- Your workflow has many legitimate small videos (50MB is wrong threshold)

### Solution 1: Empirical Feedback Loop

```python
class AdaptivePolicy:
    """Self-tuning policy based on empirical outcomes."""

    def __init__(self):
        self.outcome_history = deque(maxlen=1000)  # Last 1000 decisions
        self.environment_profile = EnvironmentProfile()

    def decide_truncation_threshold(self, video: Video) -> float:
        """Adapt threshold based on past false positives/negatives."""

        # Analyze historical outcomes
        false_positives = [
            o for o in self.outcome_history
            if o.rejected_as_truncated and o.user_overrode_decision
        ]

        false_negatives = [
            o for o in self.outcome_history
            if o.accepted_as_healthy and o.playback_failed
        ]

        # Adjust threshold to minimize total error
        if len(false_positives) > len(false_negatives):
            # Too strict - lower threshold
            return self.base_threshold * 0.95
        elif len(false_negatives) > len(false_positives):
            # Too lenient - raise threshold
            return self.base_threshold * 1.05
        else:
            return self.base_threshold

    def learn_from_outcome(self, video: Video, decision: Decision, outcome: Outcome):
        """Update policy based on actual outcome."""
        self.outcome_history.append(HistoricalOutcome(
            video_size=video.size,
            bitrate=video.bitrate,
            duration=video.duration,
            decision=decision,
            outcome=outcome,
            timestamp=now()
        ))

        # Adjust policy weights
        self._retrain_model()
```

**Key insight:** The tool should *notice* when its decisions are consistently wrong and adapt.

### Solution 2: Environment Profiling

```python
class EnvironmentProfile:
    """Learn characteristics of user's environment."""

    def __init__(self):
        self.extraction_speeds = []  # MB/s observations
        self.disk_type = None  # HDD vs SSD
        self.network_drives = set()

    def infer_disk_type(self, path: Path) -> DiskType:
        """Infer HDD vs SSD from seek time patterns."""
        # Measure: random access vs sequential access time ratio
        # SSD: ratio ~1.0, HDD: ratio >10.0
        random_speed = self._measure_random_access(path)
        sequential_speed = self._measure_sequential_access(path)
        ratio = sequential_speed / random_speed

        if ratio < 2.0:
            return DiskType.SSD
        elif ratio > 10.0:
            return DiskType.HDD
        else:
            return DiskType.UNKNOWN

    def calculate_optimal_timeout(self, archive_size: int, path: Path) -> int:
        """Calculate timeout based on observed environment speed."""
        disk_type = self.infer_disk_type(path)

        # Use historical speeds for this disk type
        relevant_speeds = [
            s for s in self.extraction_speeds
            if s.disk_type == disk_type
        ]

        if relevant_speeds:
            # Use p10 speed (conservative - 10th percentile slowest)
            p10_speed = percentile(relevant_speeds, 0.10)
            timeout = archive_size / p10_speed * 1.5  # 50% safety margin
        else:
            # Fall back to conservative default
            timeout = archive_size / (5 * 1024 * 1024) * 2.0

        return max(MIN_TIMEOUT, min(timeout, MAX_TIMEOUT))
```

**Key insight:** Tool should *measure* user's environment and adapt thresholds accordingly.

### Solution 3: Reinforcement from User Feedback

```python
class UserFeedbackLoop:
    """Learn from user corrections."""

    def record_user_override(self, video: Video, original_decision: Decision, user_decision: Decision):
        """User manually moved a rejected video - learn from this."""
        feature_vector = self.extract_features(video)

        # Store as training example
        self.training_data.append(TrainingExample(
            features=feature_vector,
            model_decision=original_decision,
            correct_decision=user_decision,
            weight=1.0  # User feedback is high-confidence
        ))

        # Periodically retrain model
        if len(self.training_data) % 100 == 0:
            self._retrain_classifier()
```

**Key insight:** When user manually corrects a decision, that's high-value training data.

---

## Part 3: Systematic Defensiveness

### Problem: Reactive vs Proactive Error Handling

**Current:** Error handling is added after bugs are discovered
**PhD:** Exhaustive failure mode enumeration BEFORE writing code

### FMEA (Failure Mode and Effects Analysis)

```markdown
| Component | Failure Mode | Cause | Effect | Detection | Mitigation | Severity | Priority |
|-----------|--------------|-------|--------|-----------|------------|----------|----------|
| Archive Extraction | Path traversal | Malicious archive | Arbitrary file write | Pre-extraction validation | Whitelist paths | CRITICAL | P0 |
| Video Validation | False negative | Corrupt header but valid metadata | Broken video moved to dest | Full decode test | Frame sampling | HIGH | P1 |
| Folder Deletion | Race condition | Contents added after check | Data loss | Double-check pattern | Re-validate before delete | CRITICAL | P0 |
| Disk Space | Insufficient space mid-extract | Parallel writes by other process | Partial extraction | Pre-check + re-check | Reserve safety margin | MEDIUM | P2 |
| Network Drive | Timeout on slow connection | Network latency spike | Operation hang | Dynamic timeout | Exponential backoff | LOW | P3 |
```

**Process:**
1. Enumerate every possible failure for each component
2. Analyze root causes and impacts
3. Design detection mechanisms (how do we know it happened?)
4. Implement mitigations BEFORE deployment
5. Prioritize by severity × likelihood

### Chaos Engineering

**Concept:** Intentionally inject failures to verify resilience

```python
class ChaosMonkey:
    """Systematically inject failures to test error handling."""

    def test_disk_full_during_extraction(self):
        """Simulate disk full mid-extraction."""
        with mock_disk_space(available=100_000_000):  # 100MB
            # Start extracting 500MB archive
            result = process_archive(large_archive)

            # Verify: Partial extraction cleaned up
            assert not any(partial_files_exist())

            # Verify: Error logged with context
            assert "disk full" in last_log_entry()

            # Verify: Subsequent operations continue
            assert app.can_process_next_folder()

    def test_permission_denied_on_delete(self):
        """Simulate permission denied during cleanup."""
        with mock_permissions(path="/locked/folder", denied=True):
            result = delete_folder("/locked/folder")

            # Verify: Graceful degradation (logged, not crashed)
            assert result == DeleteResult.FAILED
            assert "permission denied" in last_log_entry()

            # Verify: Folder tracked for retry
            assert "/locked/folder" in app.failed_deletions

    def test_corrupt_archive_list(self):
        """Simulate 7z returning corrupt listing."""
        with mock_subprocess_output("7z l", return_code=1, stderr="corrupt"):
            result = validate_archive_paths(archive)

            # Verify: Fail-closed (reject archive)
            assert result == ValidationResult.REJECTED

            # Verify: Reason logged
            assert "corrupt listing" in last_log_entry()
```

**Benefits:**
- **Exhaustive testing**: Cover failure modes that are hard to reproduce naturally
- **Regression prevention**: Failures stay fixed (test continues running)
- **Confidence**: If 50 chaos scenarios pass, resilience is *demonstrated*

### Fault Injection at Scale

```python
class FaultInjector:
    """Inject faults probabilistically during real runs."""

    def __init__(self, fault_rate: float = 0.01):
        self.fault_rate = fault_rate  # 1% of operations fail artificially
        self.enabled = config.chaos_mode

    def maybe_inject_fault(self, operation: str):
        """Randomly inject fault to test error handling in production."""
        if not self.enabled:
            return

        if random.random() < self.fault_rate:
            # Pick random failure mode for this operation type
            fault = self._select_fault_for_operation(operation)
            raise fault.exception_class(fault.message)

    # Use in production (when chaos_mode=true):
    def extract_archive(self, archive: Path):
        self.fault_injector.maybe_inject_fault("extract_archive")
        # ... actual extraction
```

**Use case:** Run in staging environment with chaos_mode=true to continuously verify error handling under stress.

---

## Part 4: Next-Level Capabilities

### 1. Provenance Tracking

**Concept:** Every output file has verifiable history

```python
@dataclass
class Provenance:
    """Complete lineage of how this file came to exist."""
    source_archive: Optional[Path]
    extraction_time: datetime
    validation_results: List[ValidationEvidence]
    policy_decision: PolicyDecision
    moved_by: str  # "unpackr v1.2.1"
    hash_chain: List[tuple[str, str]]  # [(sha256, timestamp), ...]

def attach_provenance(video: Path, provenance: Provenance):
    """Store provenance in NTFS alternate data stream."""
    # Windows: Use ADS for metadata
    provenance_json = provenance.to_json()
    video.write_text(provenance_json, stream=":provenance")

    # Alternatively: SQLite database of file_hash -> provenance
```

**Benefits:**
- **Auditability**: "Where did this file come from? Was it validated?"
- **Debugging**: "Why was this file accepted when others were rejected?"
- **Compliance**: Prove due diligence was done on every file

### 2. Diff-Based Validation

**Concept:** Detect silent corruption by comparing against known-good baseline

```python
class BaselineValidator:
    """Detect drift from known-good state."""

    def create_baseline(self, folder: Path):
        """Snapshot folder state as known-good."""
        baseline = Baseline(
            folder=folder,
            timestamp=now(),
            file_hashes={(f: sha256(f)) for f in folder.rglob('*')}
        )
        self.store_baseline(baseline)

    def detect_drift(self, folder: Path) -> List[DriftEvent]:
        """Compare current state to baseline."""
        baseline = self.load_baseline(folder)
        current_hashes = {f: sha256(f) for f in folder.rglob('*')}

        drifts = []
        for file, expected_hash in baseline.file_hashes.items():
            if file not in current_hashes:
                drifts.append(DriftEvent.DELETED(file))
            elif current_hashes[file] != expected_hash:
                drifts.append(DriftEvent.MODIFIED(file))

        for file in current_hashes:
            if file not in baseline.file_hashes:
                drifts.append(DriftEvent.ADDED(file))

        return drifts
```

**Use case:** "Has my destination folder been tampered with?"

### 3. Speculative Execution

**Concept:** Start slow operations early, commit if preconditions pass

```python
class SpeculativeProcessor:
    """Start expensive operations before validation completes."""

    def process_folder(self, folder: Path):
        # Start extraction speculatively (in temp location)
        extraction_future = executor.submit(extract_to_temp, folder)

        # While extraction runs, do validation checks
        par2_ok = validate_par2(folder)
        disk_space_ok = check_disk_space(folder)

        # Wait for extraction
        extraction_result = extraction_future.result()

        if par2_ok and disk_space_ok and extraction_result.success:
            # Commit: Move extracted files to final location
            commit_extraction(extraction_result.temp_path, folder)
        else:
            # Rollback: Delete temp extraction
            cleanup_temp(extraction_result.temp_path)
```

**Benefits:**
- **Performance**: Extraction and validation happen in parallel
- **Safety**: Only commit if ALL validations pass
- **Clarity**: Explicit commit/rollback semantics

---

## Part 5: Refined Roadmap

### Immediate Priorities (Next 3-6 Months)

**P0: Formal Safety Invariants** [2 weeks]
- Write executable invariant predicates for Safety Contract guarantees
- Add runtime invariant checking before every destructive operation
- Add invariant validation to test suite (verify invariants hold across all 94 tests)
- **Impact:** Proven safety guarantees, not just tested
- **Files:** `core/safety_invariants.py`, update all destructive operations

**P1: Adaptive Timeout Calculation** [1 week]
- Profile user's environment (HDD vs SSD detection)
- Track historical extraction/repair speeds
- Calculate timeouts based on empirical performance
- **Impact:** No more false timeouts on slow systems, faster on fast systems
- **Files:** `utils/environment_profile.py`, update `utils/safety.py`

**P2: Comprehensive FMEA** [2 weeks]
- Document all possible failure modes for each component
- Design detection mechanisms (how do we know it failed?)
- Implement mitigations for high-severity failures
- **Impact:** Proactive resilience, not reactive bug fixes
- **Deliverable:** `docs/FMEA.md` + corresponding code changes

**P3: Chaos Testing Framework** [3 weeks]
- Build fault injection system (disk full, permission denied, corrupt data)
- Create 50+ chaos scenarios covering critical paths
- Run chaos tests in CI/CD
- **Impact:** Exhaustive resilience testing
- **Files:** `tests/chaos/`, integrate with pytest

### Medium-Term Goals (6-12 Months)

**Video Validation Policy Engine** [4 weeks]
- Replace fixed heuristics with evidence-based policy system
- Structured evidence: detector name, severity, confidence, message
- Policy aggregates evidence → decision (PASS/FAIL/SUSPICIOUS)
- **Impact:** Configurable strictness, explainable decisions
- **Files:** `core/validation_policy.py`, update `core/video_processor.py`

**WAL-Based Transactional Checkpointing** [6 weeks]
- SQLite write-ahead log for crash-consistent state
- Record intent BEFORE destructive operation
- Reconcile incomplete operations on restart
- **Impact:** Resume exactly where left off after crashes
- **Files:** `core/transaction_log.py`, update `unpackr.py`

**Empirical Feedback Loop** [3 weeks]
- Track outcomes of past decisions (false positives/negatives)
- Adapt thresholds based on historical accuracy
- Learn from user corrections (manual overrides)
- **Impact:** Self-improving validation accuracy
- **Files:** `core/adaptive_policy.py`, update decision points

**Structured Event System** [4 weeks]
- Replace string logging with structured events
- Privacy transform pipeline (Full/Medium/Minimal)
- Multiple sinks: file logger, metrics, notifications
- **Impact:** Parseable logs, safe sharing, automated analysis
- **Files:** `utils/event_logger.py`, replace all `logging` calls

### Long-Term Vision (12+ Months)

**Provenance Tracking** [3 weeks]
- Attach complete history to every output file
- Store in NTFS ADS or SQLite database
- **Impact:** Full auditability and traceability

**Baseline Drift Detection** [2 weeks]
- Snapshot destination folder as known-good
- Detect modifications/deletions/additions
- **Impact:** Tamper detection

**Cross-Platform Support** [8 weeks]
- Abstract platform-specific operations
- Linux/macOS implementations
- **Impact:** Broader audience

**Formal Verification with TLA+** [8+ weeks, research project]
- Model state machine in TLA+
- Prove safety properties (no data loss, terminal states reachable)
- **Impact:** Mathematical proof of correctness

---

## Part 6: Comparison to Current Roadmap

### What Current Roadmap Has Right

1. **Phased approach** - Security → Stability → Performance → Usability
2. **Concrete deliverables** - Each item has clear output
3. **Safety-first mindset** - Every feature must uphold Safety Contract
4. **Privacy awareness** - Hash paths, aggregate stats, configurable retention

### What's Missing (PhD-Level Additions)

1. **Formal verification** - Invariants, state machines, proofs
2. **Adaptive behavior** - Learning from outcomes, environment profiling
3. **Systematic resilience** - FMEA, chaos testing, fault injection
4. **Provenance** - Complete history tracking
5. **Speculative execution** - Parallel validation + extraction

### Refined Roadmap Structure

```
Phase 0: Foundations [CURRENT PRIORITY]
├─ P0: Formal Safety Invariants (executable predicates)
├─ P1: Adaptive Timeouts (environment profiling)
├─ P2: FMEA Documentation (exhaustive failure modes)
└─ P3: Chaos Testing (50+ fault injection scenarios)

Phase 1: Intelligence
├─ Video Validation Policy Engine
├─ Empirical Feedback Loop
└─ Self-Tuning Thresholds

Phase 2: Observability
├─ Structured Event System
├─ Provenance Tracking
└─ Drift Detection

Phase 3: Resilience
├─ WAL-Based Checkpointing
├─ Speculative Execution
└─ Transactional Guarantees

Phase 4: Verification
├─ TLA+ Formal Model
├─ Property-Based Testing (Hypothesis library)
└─ Automated Proof Checking
```

### Rationale for Reordering

**Why Formal Invariants First?**
- Current Safety Contract is prose - make it executable code
- Provides foundation for all future features
- Low effort, high confidence boost
- Catches bugs that tests miss

**Why Adaptive Behavior Before Observability?**
- Adaptive timeouts solve immediate user pain (false timeouts)
- Environment profiling enables smarter defaults
- Provides feedback for observability system to learn from

**Why Chaos Testing Before WAL?**
- WAL is complex - must be battle-tested
- Chaos testing finds edge cases in existing code
- Validates error handling before adding crash recovery

**Why Provenance Before Formal Verification?**
- Provenance provides data for verification
- Proof requires understanding actual system behavior
- Empirical foundation before theoretical proofs

---

## Part 7: Implementation Principles

### 1. Make Invariants Executable

Every safety guarantee should be a function that returns bool.

**Before:**
> "Never deletes content folders (≥10 music files)"

**After:**
```python
def invariant_content_folders_preserved(op: FileOperation) -> bool:
    if op.type == OperationType.DELETE_FOLDER:
        return not is_content_folder(op.target)
    return True
```

### 2. Measure Everything

Every operation should emit structured events.

**Before:**
```python
logging.info(f"Extracted {archive}")
```

**After:**
```python
events.emit(Event(
    type="archive_extracted",
    archive_size_mb=archive.stat().st_size / (1024**2),
    duration_seconds=elapsed,
    extraction_speed_mbps=size_mb / elapsed,
    tool="7z",
    success=True
))
```

### 3. Learn From Outcomes

Every decision should track its outcome.

**Before:**
```python
if is_truncated(video):
    delete(video)
```

**After:**
```python
decision = policy.decide(video)
execute(decision)
outcomes.record(DecisionOutcome(
    video=video,
    decision=decision,
    features=extract_features(video),
    timestamp=now()
))
# Later: Did user manually restore this video? Learn from that.
```

### 4. Test Failure Modes Explicitly

Every error handler should have a test that triggers it.

**Before:**
```python
try:
    extract(archive)
except DiskFullError:
    log.error("Disk full")
```

**After:**
```python
def test_disk_full_during_extraction():
    with mock_disk_space(0):
        with pytest.raises(DiskFullError):
            extract(large_archive)
        assert "Disk full" in captured_logs()
```

---

## Conclusion

**What we're doing:** Building reliable automation for messy video processing

**How to do it better:**
1. **Make safety guarantees executable** (formal invariants)
2. **Add adaptive intelligence** (learn from outcomes)
3. **Test exhaustively** (chaos engineering, FMEA)
4. **Track everything** (structured events, provenance)
5. **Prove correctness** (state machines, formal verification)

**Next concrete actions:**
1. Write `core/safety_invariants.py` with 10 executable predicates
2. Add invariant checks before every delete/move operation
3. Create `tests/chaos/` with disk-full, permission-denied, corrupt-data scenarios
4. Profile environment (HDD/SSD detection) and adapt timeouts
5. Document all failure modes in `docs/FMEA.md`

This elevates Unpackr from "good software" to "research-grade software with PhD-level rigor."
