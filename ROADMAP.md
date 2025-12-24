# Unpackr Roadmap

Planned improvements organized in logical implementation order. Focus on security, reliability, and performance.

## Recently Completed (v1.0.x)

- Enhanced video health validation - Detects truncated/corrupt videos that were previously missed
- Fixed PAR2 error detection - Properly distinguishes repair failures from successes
- Disk space checking - Validates space before extraction (prevents partial extractions)
- Thread-safe operations - Progress updates and statistics are now thread-safe
- Atomic file operations - Files moved via temp file + atomic rename
- Per-folder recursion guards - Recursion depth resets for each folder (was accumulating globally)
- Conservative time estimates - Time saved estimates reduced to 2 min/folder for believability
- Comprehensive test suite - 33 tests passing with fixtures for easy testing

## Phase 1: Critical Security Fixes (COMPLETED - v1.1.x)

All critical security vulnerabilities have been addressed.

### 1. Path Traversal Protection (COMPLETED)
- **Issue:** Malicious archives can extract files outside target directory using `../` paths
- **Impact:** Security vulnerability - arbitrary file write
- **Implementation:** Added `_validate_archive_paths()` method that lists archive contents before extraction and validates each path for absolute paths, parent directory references, and paths outside target. Fails closed on validation errors.
- **Location:** core/archive_processor.py lines 281-367
- **Test:** Manual testing required with malicious archives containing `../` paths

### 2. Command Injection Prevention (COMPLETED)
- **Issue:** PowerShell folder deletion uses string interpolation with folder names
- **Impact:** Folder names with special characters (`;`, `|`, backticks) can execute commands
- **Implementation:** Changed PowerShell command construction from f-string to subprocess array form with `-LiteralPath` parameter for safe special character handling.
- **Location:** core/file_handler.py lines 273-279
- **Test:** Manual testing required with dangerous folder names like `test; rm -rf /`

### 3. Subprocess Buffer Management (COMPLETED)
- **Issue:** Large archive operations can exceed buffer limits causing subprocess to hang
- **Impact:** Process hangs on multi-GB files
- **Implementation:** Added `use_temp_files` parameter to `SubprocessSafety.run_with_timeout()` that redirects stdout/stderr to temporary files for large operations, preventing buffer overflow.
- **Location:** utils/safety.py lines 126-182
- **Test:** Manual testing required with 5GB+ archive extraction

## Phase 2: Stability & Reliability (COMPLETED - v1.1.x)

All stability issues have been resolved.

### 4. Exception Handler Cleanup (COMPLETED)
- **Issue:** Spinner thread not stopped on fatal errors
- **Impact:** Process doesn't exit cleanly
- **Implementation:** Added `_stop_spinner_thread()` calls to all exception handlers. Inner handler stops spinner directly, outer handlers check if app was initialized before stopping spinner.
- **Location:** unpackr.py lines 1407, 1415-1416, 1422-1423
- **Test:** Manual testing required with exception scenarios (Ctrl+C, disk full, permission errors)

### 5. Memory Leak Fix (COMPLETED)
- **Issue:** `failed_deletions` list grows unbounded over long runs
- **Impact:** Memory consumption in 24+ hour runs
- **Implementation:** Replaced unbounded list with `collections.deque(maxlen=1000)` for bounded storage. Automatically discards oldest entries when limit reached.
- **Location:** unpackr.py lines 18, 232, 992
- **Test:** Monitoring required on long runs with many failures

### 6. Folder Deletion Race Condition (COMPLETED)
- **Issue:** Folder contents can change between the "is deletable" check and actual deletion
- **Impact:** Potential data loss or failed deletions
- **Implementation:** Added double-check pattern in `safe_delete_folder()` that re-validates folder is still removable before deletion. Added `par2_error` and `archive_error` parameters for accurate re-validation.
- **Location:** core/file_handler.py lines 236-262, unpackr.py lines 583, 869, 1006
- **Test:** Concurrency testing required with folder modifications during deletion

### 7. Configuration Validation (COMPLETED)
- **Issue:** Invalid config causes runtime errors
- **Impact:** Poor UX for configuration mistakes
- **Implementation:** Added comprehensive `_validate_config()` method that checks numeric ranges, type validation, list content validation, and tool_paths structure. Validates config before applying, falls back to defaults on validation failure with helpful error messages.
- **Location:** core/config.py lines 48-68, 73-167
- **Test:** Manual testing required with invalid configs

## Phase 3: Performance Optimization (IN PROGRESS - v1.2.x)

Improve performance without sacrificing reliability.

### 8. Optimize Folder Scanning (COMPLETED)
- **Current:** Used os.walk() which works but doesn't cache stat info
- **Target:** Use `os.scandir` for single-pass scanning with cached stats
- **Implementation:** Replaced os.walk() with custom `scan_recursive()` helper using os.scandir. Uses DirEntry objects which cache stat() information, avoiding extra syscalls. Generator-based for memory efficiency.
- **Impact:** 2-3x faster pre-scan on large datasets (10,000+ files), especially noticeable with folders containing 1000+ image files
- **Location:** unpackr.py lines 287-330
- **Test:** Benchmark testing recommended comparing old vs new scanning

### 9. Dynamic Timeouts (COMPLETED)
- **Current:** Hardcoded 5-minute RAR timeout and 10-minute PAR2 timeout fail on large files
- **Target:** Calculate timeout based on file size with conservative speed assumptions
- **Implementation:** Added `calculate_rar_timeout()` and `calculate_par2_timeout()` methods. RAR assumes 10MB/s extraction with 50% buffer (min 5min, max 2hr). PAR2 assumes 5MB/s repair with 100% buffer (min 10min, max 3hr). Logs extended timeouts for visibility.
- **Impact:** Handles 50GB+ archives that take 30+ minutes without false timeouts
- **Location:** utils/safety.py lines 49-97, core/archive_processor.py lines 102-105, 182-185
- **Test:** Manual testing required with various archive sizes (100MB, 1GB, 10GB, 50GB)

### 10. Improved Video Validation
- **Current:** `'-c:v', 'copy'` only checks container, not actual frame data
- **Target:** Add frame decode sampling (every 300th frame)
- **Impact:** Catch more corrupt videos with valid containers
- **Tradeoff:** Slower validation (~2x time), more accurate
- **Test:** Add test with corrupt video that has valid container

## Phase 4: Usability Improvements

Quality of life features for better user experience.

### 11. Cancellation Support
- **Current:** Ctrl+C waits for operation to complete (up to 10 minutes)
- **Target:** Check cancellation token in loops, exit quickly
- **Impact:** Better UX when user wants to stop
- **Test:** Add test that cancels mid-operation, verify quick exit

### 12. Checkpoint & Resume
- **Current:** No progress persistence - restart means starting over
- **Target:** Save checkpoint after each folder, resume on restart
- **Impact:** Critical for 24+ hour runs with potential interruptions
- **Implementation:** JSON checkpoint file with atomic writes, no personal data stored
- **Privacy:** Only store folder paths, operation status, statistics - no file content or user info
- **Test:** Add test that stops mid-run, verify resume from checkpoint

### 13. Enhanced Dry-Run Reporting
- **Current:** Shows what would happen, but no comparison
- **Target:** Export JSON report for diff with actual run results
- **Impact:** Verify tool behaves as expected before running
- **Test:** Add test comparing dry-run report with actual run

## Phase 5: Observability & Metrics

Track performance and identify issues without storing sensitive data.

### 14. Privacy-Aware Logging Enhancement
- **Current:** Logs everything including full file paths
- **Target:** Configurable privacy modes:
  - **Full** - Current behavior (full paths, all details)
  - **Medium** - Hash file paths, keep folder structure (default)
  - **Minimal** - Only operation counts and errors, no paths
- **Impact:** Better privacy without losing debugging ability
- **Test:** Add tests for each privacy mode, verify appropriate data redaction

### 15. Metrics & Observability
- **Collect:** Operation durations, bottlenecks, success rates (aggregated only)
- **Export:** JSON, CSV formats
- **Privacy:** Only aggregate statistics, no individual file information
- **Use Case:** Identify performance regressions, optimize workflow
- **Test:** Add test that generates metrics, verify no personal data

### 16. Notification System
- **Channels:** Email, Discord, Pushbullet, Slack
- **Events:** Completion, errors, X folders processed
- **Privacy:** Only send summary statistics, no file paths or names
- **Use Case:** Long runs (24+ hours) finish while you're away
- **Test:** Add test for each notification channel (mocked)

## Phase 6: Advanced Features (Optional)

Features that add complexity but provide value for specific use cases.

### 17. SQLite State Management
- **Use Cases:**
  - Deduplicate files by checksum
  - Track processing history (aggregated only)
  - Performance metrics over time
- **Privacy:** Opt-in feature, hash all file paths, configurable retention period
- **Benefit:** Avoid reprocessing same files
- **Test:** Add tests for database operations, verify privacy settings

### 18. Parallel Video Processing (Within Folder Only)
- **Current:** Videos processed sequentially within each folder
- **Target:** Process pool for video health checks only (CPU-bound operation)
- **Impact:** 2-3x speedup on multi-core systems with SSD storage
- **Considerations:**
  - Only beneficial with SSD storage - HDD would get slower due to seek penalties
  - Requires careful stats synchronization
  - Complexity tradeoff vs modest gains
  - See Decision Log for why folder-level parallelism is intentionally avoided
- **Test:** Add concurrency tests, verify thread safety

## Ongoing Quality

Continuous improvements alongside feature development.

### Testing
- **Current:** 40% test coverage, 33 tests
- **Target:** 70%+ coverage
- **Focus:**
  - Integration tests for full workflow
  - Error injection tests (disk full, permissions, corrupted files)
  - Concurrency tests (race conditions)
  - Performance benchmarks
  - Security tests (path traversal, command injection)

### Documentation
- **Inline Documentation:** Document WHY decisions were made, not just WHAT code does
- **Examples:** Sample detection algorithm rationale, folder classification logic
- **Keep Updated:** Update README and ROADMAP as features are completed

### Code Quality Cleanup
- **Inconsistent error handling** - Standardize on exceptions, remove boolean/None returns
- **Magic numbers** - Extract to constants with clear names
- **Incomplete type hints** - Add return type annotations
- **Long methods** - Refactor methods over 100 lines
- **Redundant stat calls** - Cache file stats
- **String concatenation in loops** - Optimize stats display

## Architecture Improvements (Lower Priority)

Only tackle these when adding major features that would benefit from refactoring.

### Refactor Large Classes
- **Current:** `UnpackrApp` is 1400 lines mixing UI and business logic
- **Target:** Separate domain model, application layer, presentation layer
- **Benefit:** Easier testing, better maintainability
- **Note:** Works fine as-is, refactor only if adding major features

### Dependency Injection
- **Current:** Classes directly instantiate dependencies
- **Target:** Constructor injection with factory pattern
- **Benefit:** Easier mocking in tests

### Platform Support
- **Linux/Mac Compatibility**
- **Current:** Windows-specific (PowerShell, path handling)
- **Target:** Platform abstraction layer
- **Note:** Low priority unless demand exists

## Non-Goals

Explicitly **not** on the roadmap to maintain focus:

- **GUI Interface** - CLI is core design, terminal UX is intentional
- **Cloud Integration** - Local processing by design for privacy/speed
- **Multi-user Support** - Single-user tool
- **Plugin System** - Adds complexity, prefer core features
- **Real-time Dashboard** - Overkill for use case, terminal UI sufficient
- **Parallel Folder Processing** - See Decision Log below

## Decision Log

### Why sequential folder processing (not parallel)?

Sequential folder processing is intentionally chosen for performance and safety reasons:

**Disk I/O is the bottleneck, not CPU:**
- HDD sequential read: 100-200 MB/s
- HDD random read: 1-5 MB/s (20-100x slower)
- HDD seek time: 10-15ms per operation
- Parallel operations cause disk thrashing with excessive seeking

**Real-world performance impact:**
- Sequential: Process 1GB video in 10 seconds
- Parallel (4 videos): Each takes 50 seconds due to constant head seeking
- Result: Parallel is 2x slower despite using "all cores"

**Design optimized for typical use case:**
- Overnight batch processing on spinning disks (common for Usenet setups)
- Processing files within the same folder together maximizes locality of reference
- Sequential access patterns keep disk head in same area
- Current design is optimal for HDD workloads

**Additional safety benefits:**
- External tools (7z, par2) won't conflict on same files
- Error recovery is simpler (no coordination between parallel operations)
- Easier to reason about state and debug issues
- Progress tracking is straightforward

**Note on SSDs:** Even with SSD storage, the benefit of parallel folder processing would be minimal since archive extraction and PAR2 repair are already parallelized internally by the tools themselves. Video validation could benefit from parallelism within a folder (Phase 6), but cross-folder parallelism adds complexity with negligible gains.

### Why not async/await?
- External tools block anyway (7z, par2, ffmpeg)
- Multiprocessing better for CPU-bound video checks
- Async adds complexity without meaningful benefit

### Why SQLite over PostgreSQL?
- No server setup required
- Single file database (easy backup)
- Sufficient for single-user tool
- Keep dependencies minimal

### Why 2-minute time estimate?
- Conservative baseline for manual processing
- Accounts for: open folder, check PAR2, extract archives, verify video, move, cleanup
- Users often take longer, making tool look better
- Better to under-promise and over-deliver

### Privacy-First Approach to Logging and Metrics
- Default to privacy-preserving modes
- Hash or omit file paths unless explicitly needed for debugging
- Aggregate statistics only, never individual file details
- Configurable retention periods for all stored data
- Clear user control over what data is logged/tracked

## Code Style Guide

Write code that is clean, professional, clever, and humble. Think like a defensive developer.

### Principles

**Clean**
- No emojis in user-facing output (use text: "ok", "err", "Healthy", "Corrupt")
- No decorative separators (avoid `===`, `---`, `***`)
- Use whitespace and indentation for visual hierarchy
- Minimal, purposeful color (Green=success, Red=error, Yellow=warning, Dim=metadata)

**Professional**
- Avoid over-the-top validation ("You're absolutely right!", excessive praise)
- Use clear, direct language without superlatives
- Prioritize technical accuracy over politeness
- Error messages should be actionable, not apologetic

**Clever**
- Optimize for common workflows (pre-scan before expensive operations)
- Provide sensible defaults (sort by size, oldest-first processing)
- Anticipate user needs (offer to delete bad files immediately)
- Performance matters (use caching, avoid redundant operations)

**Humble**
- Acknowledge limitations honestly (no FFmpeg = no validation)
- Conservative estimates (2 min/folder baseline for time saved)
- Admit uncertainty when appropriate
- No false confidence in uncertain outcomes

### UI/UX Guidelines (2025 Best Practices)

**Modern CLI Design:**
```
Good:
vhealth v1.0
Video health checker and validator

Found 367 video files
Pre-scanning for samples...

Bad:
============================================================
VIDEO HEALTH CHECKER
============================================================
```

**Status Messages:**
```
Good:
  ok   filename.mp4
  err  badfile.mkv (corrupted)

Bad:
  ✓ Deleted: filename.mp4
  ✗ Failed: badfile.mkv (corrupted)
```

**Output Formatting:**
```
Good:
Summary

  Healthy     330
  Corrupt       2
  Samples      37
  Total       369

Bad:
============================================================
Health Check Summary
============================================================

✓ Healthy:     330
✗ Corrupt:       2
⚠ Samples:      37
```

**Progress Display:**
```
Good:
[142/367] filename.mp4
  HEALTHY

Bad:
[142/367] filename.mp4
[SAFETY] Video metadata check: filename.mp4 failed with code 1
  ✓ HEALTHY
```

### Defensive Programming

**Always Validate:**
- Input sanitization (path traversal, null bytes, special characters)
- Bounds checking (array indices, file sizes, timeouts)
- Resource limits (max iterations, memory usage, disk space)
- Expected exit codes (ffmpeg returns 1 for metadata checks - that's normal)

**Error Handling:**
- Use exceptions for exceptional conditions
- Return booleans for expected failures
- Log errors with context (operation, file name, parameters)
- Provide actionable error messages

**Safety Mechanisms:**
- Timeouts on all external operations
- Loop guards with max iterations
- Thread-safe shared state (use locks)
- Atomic file operations (temp file + rename)

**Privacy:**
- Hash file paths in logs when possible
- Aggregate statistics only (no individual file tracking)
- Configurable log levels (Full/Medium/Minimal)
- Clear retention policies

## Implementation Guidelines

When implementing roadmap items:

1. **Write tests first** (TDD approach) - Ensure item is testable before implementing
2. **One item at a time** - Complete, test, and validate before moving to next
3. **Update tests** - Ensure all existing tests still pass
4. **Update documentation** - Keep README and ROADMAP current
5. **Test in real environment** - Run on actual Usenet downloads before marking complete
6. **Privacy review** - For any logging/storage feature, verify no sensitive data leaks
7. **Style check** - Follow the code style guide above

## Versioning

- **1.0.x** - Initial release with bug fixes and small improvements
- **1.1.x** - Phase 1-2 completed (Security & Stability fixes)
- **1.2.x** - Phase 3-4 (Performance & Usability improvements) - In progress
- **1.3.x** - Phase 5 (Observability & Metrics)
- **2.0.x** - Phase 6+ (Advanced Features & Architecture)

---

**Last Updated:** 2025-12-24

**Next Review:** After Phase 3 completion

**Current Status:** Phase 1 and 2 completed. Phase 3 two-thirds complete (8 of 10 items done).
