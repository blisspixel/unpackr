# Unpackr Roadmap

Planned improvements organized in logical implementation order. Focus on security, reliability, and performance.

## Recently Completed

- **Enhanced video health validation** - Detects truncated/corrupt videos that were previously missed
- **Fixed PAR2 error detection** - Properly distinguishes repair failures from successes
- **Disk space checking** - Validates space before extraction (prevents partial extractions)
- **Thread-safe operations** - Progress updates and statistics are now thread-safe
- **Atomic file operations** - Files moved via temp file + atomic rename
- **Per-folder recursion guards** - Recursion depth resets for each folder (was accumulating globally)
- **Conservative time estimates** - Time saved estimates reduced to 2 min/folder for believability
- **Comprehensive test suite** - 33 tests passing with fixtures for easy testing

## Phase 1: Critical Security Fixes

Address security vulnerabilities before adding features.

### 1. Path Traversal Protection
- **Issue:** Malicious archives can extract files outside target directory using `../` paths
- **Impact:** Security vulnerability - arbitrary file write
- **Fix:** Validate all paths in archive before extraction, reject any with traversal attempts
- **Test:** Add test cases with malicious archives containing `../` paths

### 2. Command Injection Prevention
- **Issue:** PowerShell folder deletion uses string interpolation with folder names
- **Impact:** Folder names with special characters (`;`, `|`, backticks) can execute commands
- **Fix:** Use subprocess array form instead of string interpolation everywhere
- **Test:** Add test cases with dangerous folder names

### 3. Subprocess Buffer Management
- **Issue:** Large archive operations can exceed buffer limits causing subprocess to hang
- **Impact:** Process hangs on multi-GB files
- **Fix:** Use temporary files instead of PIPE for large outputs
- **Test:** Add test with multi-GB archive extraction

## Phase 2: Stability & Reliability

Fix known bugs and edge cases.

### 4. Exception Handler Cleanup
- **Issue:** Spinner thread not stopped on fatal errors
- **Impact:** Process doesn't exit cleanly
- **Fix:** Add `_stop_spinner_thread()` to exception handler
- **Test:** Add test that triggers exception, verify clean exit

### 5. Memory Leak Fix
- **Issue:** `failed_deletions` list grows unbounded over long runs
- **Impact:** Memory consumption in 24+ hour runs
- **Fix:** Use `collections.deque(maxlen=1000)` for bounded storage
- **Test:** Add test that simulates long run with many failures

### 6. Folder Deletion Race Condition
- **Issue:** Folder contents can change between the "is deletable" check and actual deletion
- **Impact:** Potential data loss or failed deletions
- **Fix:** Add folder-level locking or implement double-check pattern
- **Test:** Add concurrency test that modifies folder during deletion check

### 7. Configuration Validation
- **Issue:** Invalid config causes runtime errors
- **Impact:** Poor UX for configuration mistakes
- **Fix:** Validate config on load with clear, actionable error messages
- **Test:** Add tests with invalid configs, verify helpful error messages

## Phase 3: Performance Optimization

Improve performance without sacrificing reliability.

### 8. Optimize Folder Scanning
- **Current:** Walks every file multiple times (O(n²) complexity)
- **Target:** Use `os.scandir` for single-pass scanning
- **Impact:** 2-3x faster pre-scan on large datasets (10,000+ files)
- **Test:** Add benchmark test comparing old vs new scanning

### 9. Dynamic Timeouts
- **Current:** Hardcoded 5-minute RAR timeout fails on large files
- **Target:** Calculate timeout based on file size (assume 10MB/s extraction rate)
- **Impact:** Handles 50GB+ archives that take 30+ minutes without false timeouts
- **Test:** Add test with various archive sizes, verify appropriate timeouts

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

## Implementation Guidelines

When implementing roadmap items:

1. **Write tests first** (TDD approach) - Ensure item is testable before implementing
2. **One item at a time** - Complete, test, and validate before moving to next
3. **Update tests** - Ensure all existing tests still pass
4. **Update documentation** - Keep README and ROADMAP current
5. **Test in real environment** - Run on actual Usenet downloads before marking complete
6. **Privacy review** - For any logging/storage feature, verify no sensitive data leaks

## Versioning

- **1.0.x** - Bug fixes and small improvements
- **1.1.x** - Phase 1-2 (Security & Stability)
- **1.2.x** - Phase 3-4 (Performance & Usability)
- **1.3.x** - Phase 5 (Observability & Metrics)
- **2.0.x** - Phase 6+ (Advanced Features & Architecture)

---

**Last Updated:** 2024-12-24

**Next Review:** After each phase completion
