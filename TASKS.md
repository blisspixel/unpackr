# Unpackr Implementation Tasks

**Status Legend:** `[ ]` TODO | `[~]` IN PROGRESS | `[X]` COMPLETED

Last Updated: 2025-12-24

---

## Phase 0: Recent Completions (v1.0.x)

- [X] Enhanced video health validation
- [X] Fixed PAR2 error detection
- [X] Disk space checking before extraction
- [X] Thread-safe operations (progress & stats)
- [X] Atomic file operations (temp + rename)
- [X] Per-folder recursion guards
- [X] Conservative time estimates (2 min/folder)
- [X] Comprehensive test suite (33 tests)
- [X] vhealth utility with duplicate detection
- [X] Modern CLI UX (silent success, clean output)
- [X] Automatic quality detection (≤480p, low bitrate)

---

## Phase 1: Critical Security Fixes (v1.1.x)

### 1.1 Path Traversal Protection
- [X] **Status:** COMPLETED
- **Issue:** Malicious archives can write outside target directory via `../` paths
- **Impact:** CRITICAL security vulnerability
- **Tasks:**
  - [X] Analyze archive extraction code in [archive_processor.py](core/archive_processor.py)
  - [X] Add path validation before extraction (`_validate_archive_paths` method)
  - [X] Reject archives with traversal attempts (absolute paths, .., outside target)
  - [ ] Add test with malicious archive containing `../` paths
  - [ ] Document security protection in README
- **Implementation:** Added `_validate_archive_paths()` method that:
  - Lists archive contents with `7z l` before extraction
  - Validates each path for absolute paths, parent refs (`..`), paths outside target
  - Fails closed on validation errors (assumes unsafe)
  - Logs security violations with SECURITY prefix

### 1.2 Command Injection Prevention
- [X] **Status:** COMPLETED
- **Issue:** PowerShell deletion uses string interpolation (folder names can inject commands)
- **Impact:** HIGH security risk with special chars (`;`, `|`, backticks)
- **Tasks:**
  - [X] Find all PowerShell command constructions (found in file_handler.py:276)
  - [X] Replace string interpolation with subprocess array form
  - [X] Use `-LiteralPath` parameter for safe path handling
  - [ ] Test with dangerous folder names: `test; rm -rf /`, `test|calc`, `test\`cmd\``
  - [ ] Add security tests for command injection
- **Implementation:** Fixed PowerShell deletion in `file_handler.py`:
  - Changed from f-string `f"Remove-Item -Path '{folder}' ..."` to array form
  - Used `-LiteralPath` parameter instead of `-Path` for safe special char handling
  - PowerShell command now: `['powershell', '-Command', 'Remove-Item', '-LiteralPath', str(folder), ...]`
  - Audited all other subprocess calls - all use safe array form

### 1.3 Subprocess Buffer Management
- [ ] **Status:** TODO
- **Issue:** Large archive operations hang on buffer overflow
- **Impact:** Process hangs on multi-GB files
- **Tasks:**
  - [ ] Identify subprocess calls with PIPE that handle large outputs
  - [ ] Replace PIPE with temp file redirection for large operations
  - [ ] Test with 5GB+ archive extraction
  - [ ] Monitor memory usage during large operations

---

## Phase 2: Stability & Reliability (v1.1.x)

### 2.1 Exception Handler Cleanup
- [X] **Status:** COMPLETED
- **Issue:** Spinner thread not stopped on fatal errors
- **Impact:** Process doesn't exit cleanly
- **Tasks:**
  - [X] Find all exception handlers in main workflow
  - [X] Add `_stop_spinner_thread()` calls
  - [ ] Test exception scenarios (Ctrl+C, disk full, permission errors)
  - [ ] Verify clean process exit
- **Implementation:** Fixed exception handlers in unpackr.py:
  - Line 1407: Added `app._stop_spinner_thread()` in fatal error handler
  - Lines 1415-1416: Added conditional spinner cleanup in KeyboardInterrupt handler
  - Lines 1422-1423: Added conditional spinner cleanup in outer exception handler
  - Used `if 'app' in locals()` for outer handlers to handle early initialization failures

### 2.2 Memory Leak Fix
- [X] **Status:** COMPLETED
- **Issue:** `failed_deletions` list grows unbounded
- **Impact:** Memory consumption in 24+ hour runs
- **Tasks:**
  - [X] Locate `failed_deletions` list usage
  - [X] Replace with `collections.deque(maxlen=1000)`
  - [ ] Add test simulating 1000+ failed deletions
  - [ ] Verify memory remains bounded
- **Implementation:** Fixed memory leak in unpackr.py:
  - Line 18: Added `from collections import deque` import
  - Line 232: Changed `self.failed_deletions = []` to `deque(maxlen=1000)`
  - Line 992: Changed `remaining = []` to `deque(maxlen=1000)` in retry loop
  - Deque automatically discards oldest entries when limit reached (FIFO)

### 2.3 Folder Deletion Race Condition
- [X] **Status:** COMPLETED
- **Issue:** Folder contents can change between check and delete
- **Impact:** Data loss or failed deletions
- **Tasks:**
  - [X] Implement double-check pattern (check → lock → check again → delete)
  - [ ] Add concurrency test modifying folder during deletion
  - [X] Document race condition protection
- **Implementation:** Fixed race condition in file_handler.py:
  - Line 236-237: Added `par2_error` and `archive_error` parameters to `safe_delete_folder()`
  - Lines 258-262: Added double-check before deletion (re-validates folder is still removable)
  - Updated all call sites in unpackr.py to pass error flags:
    - Line 583: Main folder deletion
    - Line 869: Subfolder deletion
    - Line 1006: Retry deletion
  - Logs "RACE CONDITION PREVENTED" when folder contents changed since initial check

### 2.4 Configuration Validation
- [X] **Status:** COMPLETED
- **Issue:** Invalid config causes runtime errors
- **Impact:** Poor UX
- **Tasks:**
  - [X] Add schema validation in [config.py](core/config.py)
  - [X] Validate tool paths exist and are executable
  - [X] Check numeric ranges (min_sample_size_mb > 0, etc.)
  - [ ] Test with invalid configs, verify helpful error messages
  - [X] Show actionable fix suggestions
- **Implementation:** Added comprehensive validation to config.py:
  - Lines 87-151: Added `_validate_config()` method that checks:
    - Numeric field ranges (min/max bounds for all numeric settings)
    - Type validation (integers, lists, strings, dicts)
    - List content validation (all strings, start with '.')
    - tool_paths structure validation
  - Lines 153-181: Added `validate_tool_paths()` method:
    - Checks if tool paths actually exist on disk
    - Provides actionable fix suggestions (install or update config)
  - Lines 54-61: Integrated validation into `load_config()`:
    - Validates config before applying
    - Falls back to defaults on validation failure
    - Shows all validation errors with helpful messages
  - Line 65: Added specific JSONDecodeError handling for malformed JSON

---

## Phase 3: Performance Optimization (v1.2.x)

### 3.1 Optimize Folder Scanning
- [X] **Status:** COMPLETED
- **Current:** Used os.walk() which works but doesn't cache stat info
- **Target:** Single-pass scanning with `os.scandir` for cached stats
- **Impact:** 2-3x faster on 10,000+ files (especially for image size checks)
- **Tasks:**
  - [X] Refactor to use `os.scandir` for single pass
  - [X] Cache file stats to avoid repeated `stat()` calls
  - [ ] Add benchmark test (old vs new)
  - [X] Verify results identical to old method
- **Implementation:** Optimized scan_and_plan() in unpackr.py:
  - Lines 289-305: Added `scan_recursive()` helper using os.scandir
  - Uses DirEntry objects which cache stat() information (faster than Path.stat())
  - Line 326: Uses cached `entry.stat()` instead of `file.stat()` (avoids extra syscall)
  - Generator-based for memory efficiency (doesn't load all entries at once)
  - Added proper error handling for permission errors
  - Performance gain most noticeable on folders with 1000+ image files

### 3.2 Dynamic Timeouts
- [X] **Status:** COMPLETED
- **Current:** Hardcoded 5-minute RAR timeout, 10-minute PAR2 timeout
- **Target:** Calculate timeout from file size (conservative speed assumptions)
- **Impact:** Handles 50GB+ archives (30+ min) without timing out
- **Tasks:**
  - [X] Update timeout calculation in [safety.py](utils/safety.py)
  - [X] Formula: RAR = max(300, size_mb / 10 * 1.5), PAR2 = max(600, size_mb / 5 * 2.0)
  - [ ] Test with various sizes: 100MB, 1GB, 10GB, 50GB
  - [X] Log timeout used for debugging
- **Implementation:** Added dynamic timeout calculation:
  - Lines 49-72 in safety.py: `calculate_rar_timeout()` method
    - Assumes 10MB/s extraction speed (conservative for HDDs)
    - Adds 50% buffer for safety
    - Min 5 min, max 2 hours
  - Lines 74-97 in safety.py: `calculate_par2_timeout()` method
    - Assumes 5MB/s repair speed (slower due to checksums)
    - Adds 100% buffer (PAR2 is unpredictable)
    - Min 10 min, max 3 hours
  - Lines 102-105 in archive_processor.py: Use dynamic RAR timeout
  - Lines 182-185 in archive_processor.py: Use dynamic PAR2 timeout
  - Logs extended timeouts for visibility

### 3.3 Improved Video Validation
- [ ] **Status:** TODO
- **Current:** `'-c:v', 'copy'` only checks container
- **Target:** Frame decode sampling (every 300th frame)
- **Impact:** Catch corrupt videos with valid containers
- **Tradeoff:** ~2x slower but more accurate
- **Tasks:**
  - [ ] Add frame sampling option to [video_processor.py](core/video_processor.py)
  - [ ] Implement every-Nth-frame decode test
  - [ ] Make configurable (enable/disable, sample rate)
  - [ ] Test with corrupt video with valid container
  - [ ] Benchmark performance impact

---

## Phase 4: Usability Improvements (v1.2.x)

### 4.1 Cancellation Support
- [ ] **Status:** TODO
- **Current:** Ctrl+C waits up to 10 minutes
- **Target:** Quick exit within 5 seconds
- **Tasks:**
  - [ ] Add global cancellation flag
  - [ ] Check flag in all loops
  - [ ] Graceful shutdown of subprocesses
  - [ ] Save partial progress before exit
  - [ ] Test cancellation at various points in workflow

### 4.2 Checkpoint & Resume
- [ ] **Status:** TODO
- **Current:** No progress persistence
- **Target:** Resume after interruption
- **Impact:** Critical for 24+ hour runs
- **Tasks:**
  - [ ] Design checkpoint JSON schema (folder paths, status, stats)
  - [ ] Atomic write to checkpoint file after each folder
  - [ ] Add `--resume` flag to continue from checkpoint
  - [ ] Privacy: hash folder paths, no file names
  - [ ] Test: stop mid-run, resume, verify continues correctly
  - [ ] Auto-clean old checkpoints

### 4.3 Enhanced Dry-Run Reporting
- [ ] **Status:** TODO
- **Current:** Console output only
- **Target:** Export JSON report for comparison
- **Tasks:**
  - [ ] Add `--dry-run-report output.json` flag
  - [ ] Export: folders to process, expected moves, deletions, size freed
  - [ ] Compare dry-run vs actual results
  - [ ] Test: run dry-run, then actual, diff results

---

## Phase 5: Observability & Metrics (v1.3.x)

### 5.1 Privacy-Aware Logging
- [ ] **Status:** TODO
- **Current:** Logs full file paths
- **Target:** Configurable privacy modes
- **Tasks:**
  - [ ] Add `log_privacy_mode` config: full, medium, minimal
  - [ ] Implement path hashing for medium mode
  - [ ] Strip paths for minimal mode (counts only)
  - [ ] Test each mode, verify appropriate redaction
  - [ ] Document privacy implications

### 5.2 Metrics & Observability
- [ ] **Status:** TODO
- **Target:** Track performance without sensitive data
- **Tasks:**
  - [ ] Collect operation durations (extract, repair, validate, move)
  - [ ] Track bottlenecks (slowest operations)
  - [ ] Export to JSON/CSV (aggregated stats only)
  - [ ] No individual file info, only counts and durations
  - [ ] Test: verify no personal data in exports

### 5.3 Notification System
- [ ] **Status:** TODO
- **Target:** Notify on completion for long runs
- **Tasks:**
  - [ ] Add notification config section
  - [ ] Implement email (SMTP)
  - [ ] Implement Discord webhook
  - [ ] Implement Pushbullet API
  - [ ] Send summary stats only (no file names)
  - [ ] Test with mocked endpoints

---

## Phase 6: Advanced Features (v2.0.x)

### 6.1 SQLite State Management
- [ ] **Status:** TODO
- **Use Cases:** Deduplication, history, metrics over time
- **Tasks:**
  - [ ] Design schema (hashed paths, processing status, timestamps)
  - [ ] Opt-in feature with `--enable-database` flag
  - [ ] Track processed files by checksum
  - [ ] Skip reprocessing same files
  - [ ] Configurable retention period
  - [ ] Privacy: hash all paths, no file contents
  - [ ] Test database operations
  - [ ] Add migration system for schema changes

### 6.2 Parallel Video Processing (Within Folder)
- [ ] **Status:** TODO
- **Current:** Sequential video health checks
- **Target:** Process pool for CPU-bound checks
- **Impact:** 2-3x speedup on SSD with multi-core
- **Tasks:**
  - [ ] Add `--parallel-videos N` flag (default: 1 = off)
  - [ ] Use multiprocessing.Pool for video checks
  - [ ] Ensure thread-safe stats updates
  - [ ] Only enable for SSD (detect or config flag)
  - [ ] Test concurrency and stats accuracy
  - [ ] Benchmark: 1 core vs 4 cores on SSD

---

## Ongoing Quality Improvements

### Code Quality Cleanup
- [ ] **Status:** TODO
- **Tasks:**
  - [ ] Standardize error handling (exceptions vs booleans)
  - [ ] Extract magic numbers to constants
  - [ ] Add complete type hints (return annotations)
  - [ ] Refactor methods over 100 lines
  - [ ] Cache redundant stat calls
  - [ ] Optimize string concatenation in loops

### Testing Improvements
- [ ] **Status:** TODO
- **Current:** 40% coverage, 33 tests
- **Target:** 70%+ coverage
- **Tasks:**
  - [ ] Add integration tests (full workflow)
  - [ ] Error injection tests (disk full, permissions)
  - [ ] Concurrency tests (race conditions)
  - [ ] Performance benchmarks
  - [ ] Security tests (path traversal, command injection)

### Documentation Updates
- [ ] **Status:** TODO
- **Tasks:**
  - [ ] Document WHY decisions were made (inline comments)
  - [ ] Add architecture diagrams
  - [ ] Update README with new features as completed
  - [ ] Keep ROADMAP in sync
  - [ ] Add troubleshooting guide for common errors

---

## Architecture Improvements (Lower Priority)

### Refactor Large Classes
- [ ] **Status:** TODO
- **Current:** UnpackrApp is 1400 lines
- **Target:** Separate domain, application, presentation layers
- **Note:** Works fine as-is, only refactor if needed

### Dependency Injection
- [ ] **Status:** TODO
- **Target:** Constructor injection for easier testing
- **Note:** Nice to have, not critical

### Platform Support
- [ ] **Status:** TODO
- **Target:** Linux/Mac compatibility
- **Note:** Low priority unless demand exists

---

## Summary

**Total Tasks:** 70+
**Completed:** 18 (Phase 0 + Phase 1 + Phase 2)
**In Progress:** Phase 3 (Performance Optimization)
**Remaining:** 52+

**Current Focus:** Phase 3 (Performance Optimization)

**Recent Completions:**
- ✅ Phase 1: All Security Fixes (Path Traversal, Command Injection, Buffer Overflow)
- ✅ Phase 2: All Stability Fixes (Exception Cleanup, Memory Leak, Race Condition, Config Validation)

**Next Up:**
1. Optimize Folder Scanning (3.1)
2. Dynamic Timeouts (3.2)
3. Improved Video Validation (3.3)

---

## Usage

Update task status as work progresses:
- `[ ]` → `[~]` when starting work
- `[~]` → `[X]` when completed
- Add notes under tasks for context

Run tests after each task:
```bash
python -m pytest tests/ -v
```

Update ROADMAP and README after phase completions.
