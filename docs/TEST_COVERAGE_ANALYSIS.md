# Test Coverage Analysis - Unpackr

## Executive Summary

**Current State:** 33 tests pass, but they miss critical user-facing issues
**Problem:** Tests focus on unit-level functionality, missing integration and UX issues
**Recent Failures:** Pre-scan terminal spam and countdown hang were not caught by tests

## What IS Currently Tested (33 passing tests)

### Unit Tests - Low-Level Functionality ✓

**Path Handling (9 tests)**
- Quote removal from paths
- Whitespace trimming
- Empty string handling
- UNC path support
- Special characters in paths

**Configuration (7 tests)**
- Module imports
- Default config loading
- Video extension detection
- Removable extension lists
- Config property access

**Data Structures (3 tests)**
- WorkPlan initialization
- WorkPlan folder addition
- Time estimate calculation

**Input Validation (6 tests)**
- Path validation (exists, type checking)
- String validation (length, null bytes)
- Integer validation (ranges, conversion)
- List validation (length constraints)

**Safety Mechanisms (7 tests)**
- Timeout guards
- Subprocess timeouts
- Loop iteration limits
- Recursion depth limits
- Operation timers
- Stuck detection
- Safety configuration values

**Error Recovery (3 tests)**
- Safe file deletion
- Safe file movement
- Safe text reading

### What These Tests Actually Validate

The current tests validate:
1. **Internal API contracts** - Functions return expected types
2. **Data structure integrity** - Objects initialize correctly
3. **Bounds checking** - Numeric values stay within limits
4. **Resource limits** - Timeouts and recursion limits are configured

These are valuable for preventing regressions in internal logic.

## What IS NOT Tested (Critical Gaps)

### Integration Tests - MISSING ✗

**End-to-End Workflows (0 tests)**
- Full run from scan → countdown → process → cleanup
- Multi-folder processing pipeline
- Error handling across module boundaries
- State transitions during processing

**Real File Operations (0 tests)**
- RAR extraction on actual multi-part archives
- PAR2 repair on actual corrupt files
- Video validation on real video files
- Folder cleanup after processing

**External Tool Integration (0 tests)**
- 7-Zip extraction behavior
- par2cmdline repair behavior
- FFmpeg validation behavior
- Tool failure handling

### User Experience Tests - MISSING ✗

**Terminal Display (0 tests)**
- Pre-scan progress updates (THE BUG WE JUST FIXED)
- Countdown visual feedback (THE BUG WE JUST FIXED)
- Progress bar rendering
- Color output on Windows console
- Unicode character display

**User Workflow (0 tests)**
- Interactive mode (no args)
- Command-line argument parsing
- Dry-run mode behavior
- Show-plan mode behavior
- Error message readability

**Windows-Specific Issues (0 tests)**
- Console encoding (cp1252 vs UTF-8) - THE BUG WE JUST FIXED
- Carriage return behavior (`\r` doesn't work) - THE BUG WE JUST FIXED
- Path handling (backslashes, UNC paths)
- PowerShell forced deletion
- Locked file retries

### Configuration Tests - PARTIAL ✓/✗

**What IS tested:**
- Default config loads
- Properties accessible

**What IS NOT tested:**
- Invalid JSON handling
- Tool path validation
- Config file updates
- Tool path fallback (multiple paths tried in order)
- Numeric range validation enforcement
- List validation enforcement

### Error Scenarios - MISSING ✗

**Common Failure Modes (0 tests)**
- Corrupt archive extraction failure
- PAR2 repair failure (not enough parity)
- Video validation failure (truncated file)
- Disk space insufficient
- Folder locked by another process
- Process orphaned (killed during operation)

**Edge Cases (0 tests)**
- Empty source directory
- Source equals destination
- Nested archives (RAR within RAR)
- Duplicate video filenames
- Extremely long paths (> 260 chars on Windows)
- Unicode filenames

### Performance Tests - MISSING ✗

**Scalability (0 tests)**
- Processing 1000+ folders
- Handling 10,000+ files
- Memory usage over time
- Progress tracking accuracy at scale

**Timeouts (0 tests)**
- Max runtime enforcement
- Stuck operation detection
- Long-running extraction handling

## Why Current Tests Didn't Catch Recent Bugs

### Bug 1: Pre-scan Terminal Spam
**Issue:** Pre-scan printed 486 lines instead of updating same line
**Root Cause:** `\r` (carriage return) doesn't work on Windows

**Why tests missed it:**
- No tests for terminal output rendering
- No tests for Windows-specific console behavior
- No tests that actually run the pre-scan code path
- Tests don't validate visual output, only return values

### Bug 2: Countdown Appearing Hung
**Issue:** Countdown slept for 10 seconds with no visual feedback
**Root Cause:** No countdown numbers displayed, just static message

**Why tests missed it:**
- No tests for countdown function
- No tests for user-perceived responsiveness
- No tests that validate visual feedback during waits
- Tests don't measure UX, only functional correctness

### Bug 3: Unicode Encoding Crashes
**Issue:** App crashed with `UnicodeEncodeError` on emoji symbols
**Root Cause:** Windows console defaults to cp1252, not UTF-8

**Why tests missed it:**
- Tests run in pytest environment (different encoding behavior)
- No tests that capture actual console output
- No tests for Windows-specific encoding issues
- Tests don't validate that output DISPLAYS, only that it doesn't crash

## Required Test Improvements

### Priority 1: Integration Tests (CRITICAL)

**End-to-End Smoke Test**
```python
def test_full_pipeline_smoke():
    """
    Test complete workflow: scan → countdown → process → cleanup
    Uses temp directory with mock archives, videos, junk files
    Validates that:
    - Pre-scan completes without spam
    - Countdown shows visual feedback
    - Processing completes successfully
    - Statistics are accurate
    - Cleanup removes expected files
    """
```

**Windows Console Output Test**
```python
def test_windows_console_output():
    """
    Test that terminal output works on Windows console
    Validates:
    - UTF-8 encoding configured correctly
    - Progress bars render (█░)
    - Spinners display (⠋⠙⠹)
    - No Unicode emoji crashes (✓⚠✗)
    - Carriage returns handled correctly
    """
```

**Real Archive Processing Test**
```python
def test_real_archive_extraction():
    """
    Test RAR extraction on actual multi-part archive
    Validates:
    - Multi-part RAR extraction succeeds
    - PAR2 verification runs
    - Extracted files are valid
    - Archive cleanup occurs
    """
```

### Priority 2: User Workflow Tests (HIGH)

**Interactive Mode Test**
```python
def test_interactive_mode():
    """
    Test interactive mode with simulated user input
    Validates:
    - Prompts for source/destination
    - Countdown can be cancelled (Ctrl+C)
    - Pre-flight plan displays
    - User confirmation works
    """
```

**Command-Line Argument Test**
```python
def test_cli_arguments_full():
    """
    Test all CLI argument combinations
    Validates:
    - --source and --destination
    - Positional arguments
    - --dry-run behavior
    - --show-plan behavior
    - --vhealth execution
    - Invalid argument handling
    """
```

### Priority 3: Error Handling Tests (HIGH)

**Corrupt Archive Test**
```python
def test_corrupt_archive_handling():
    """
    Test behavior with corrupt RAR file
    Validates:
    - Error is detected
    - PAR2 repair attempted
    - If repair fails, folder marked as failed
    - Logging captures error details
    """
```

**Disk Space Insufficient Test**
```python
def test_insufficient_disk_space():
    """
    Test behavior when disk space is too low
    Validates:
    - Pre-extraction check detects low space
    - Extraction is skipped
    - Error message is actionable
    - No partial extractions left behind
    """
```

### Priority 4: Configuration Tests (MEDIUM)

**Invalid Config Handling Test**
```python
def test_invalid_config_json():
    """
    Test behavior with malformed config.json
    Validates:
    - Invalid JSON detected
    - Defaults used as fallback
    - User warned about config issue
    - App continues running
    """
```

**Tool Path Validation Test**
```python
def test_tool_path_fallback():
    """
    Test multiple tool paths tried in order
    Validates:
    - First path tried
    - Falls back to second path if first fails
    - All paths exhausted before error
    - Clear error message if all paths fail
    """
```

### Priority 5: Performance Tests (MEDIUM)

**Large Scale Test**
```python
def test_large_scale_processing():
    """
    Test processing 100+ folders
    Validates:
    - Progress tracking stays accurate
    - Memory usage stays bounded
    - Statistics track correctly
    - ETA calculation remains reasonable
    """
```

## Recommended Test Structure

```
tests/
├── unit/                          # Current tests (keep these)
│   ├── test_paths.py
│   ├── test_config.py
│   ├── test_validation.py
│   └── test_safety.py
├── integration/                   # NEW - Priority 1
│   ├── test_full_pipeline.py      # End-to-end workflow
│   ├── test_windows_console.py    # Console output on Windows
│   ├── test_archive_processing.py # Real archive extraction
│   └── test_video_validation.py   # Real video checks
├── workflow/                      # NEW - Priority 2
│   ├── test_interactive_mode.py
│   ├── test_cli_arguments.py
│   └── test_dry_run.py
├── error_handling/                # NEW - Priority 3
│   ├── test_corrupt_archives.py
│   ├── test_disk_space.py
│   ├── test_locked_files.py
│   └── test_tool_failures.py
└── performance/                   # NEW - Priority 5
    ├── test_scale.py
    └── test_memory.py
```

## How to Achieve "PhD Level" Coverage

### Principles

1. **Test Real Behavior, Not Just Code**
   - Don't just test that functions return the right type
   - Test that the USER EXPERIENCE is correct
   - Validate visual output, timing, responsiveness

2. **Test What Actually Breaks**
   - Look at recent bug fixes
   - Every bug = missing test that should have caught it
   - Add regression tests for every fix

3. **Test Cross-Platform Differences**
   - Windows console encoding
   - Windows path handling
   - Windows locked file behavior
   - Linux/Mac differences

4. **Test Integration Points**
   - Where modules interact
   - Where external tools are called
   - Where filesystem is accessed
   - Where user input is processed

5. **Test Error Paths, Not Just Happy Paths**
   - What happens when tools fail?
   - What happens when disk is full?
   - What happens when files are locked?
   - What happens when config is invalid?

### Coverage Metrics

**Current Coverage (Estimated):**
- Unit tests: 80% (good internal API coverage)
- Integration tests: 5% (minimal workflow validation)
- User workflow tests: 0% (no UX validation)
- Error scenario tests: 10% (basic error recovery only)
- **Overall effective coverage: 20%**

**Target Coverage:**
- Unit tests: 90% (maintain high internal coverage)
- Integration tests: 80% (validate all major workflows)
- User workflow tests: 90% (validate all CLI paths)
- Error scenario tests: 70% (validate common failures)
- **Overall effective coverage: 85%**

### Test Quality Indicators

**Current Indicators (Why Tests Failed to Catch Bugs):**
- ✗ Tests run in isolation (not real console)
- ✗ Tests use mocks instead of real tools
- ✗ Tests don't validate visual output
- ✗ Tests don't check timing/responsiveness
- ✗ Tests don't validate Windows-specific behavior

**Target Indicators (PhD Level):**
- ✓ Tests run in real console environment
- ✓ Tests use real tools (7z, par2, ffmpeg) when possible
- ✓ Tests validate terminal output rendering
- ✓ Tests check user-perceived responsiveness
- ✓ Tests validate platform-specific behavior
- ✓ Every bug fix includes regression test
- ✓ Tests fail BEFORE the bug is fixed
- ✓ Tests pass AFTER the bug is fixed

## Action Items

### Immediate (Next Session)

1. **Create test_integration_basic.py**
   - Test pre-scan progress display (would have caught Bug 1)
   - Test countdown visual feedback (would have caught Bug 2)
   - Test Windows console encoding (would have caught Bug 3)

2. **Create test_windows_specific.py**
   - Test UTF-8 encoding configuration
   - Test carriage return handling
   - Test Unicode character display

3. **Create test_cli_real_usage.py**
   - Test actual `python unpackr.py --source X --destination Y` execution
   - Capture stdout/stderr
   - Validate no crashes, no hangs, no spam

### Short Term (This Week)

4. **Create test_archive_real.py**
   - Use actual test archive files (check them into repo)
   - Test extraction, PAR2, video validation on real files

5. **Create test_error_scenarios.py**
   - Test corrupt archive handling
   - Test disk space handling
   - Test tool failure handling

6. **Add regression tests for all recent bugs**
   - Every bug in git history = missing test

### Long Term (Ongoing)

7. **Test coverage monitoring**
   - Run `pytest --cov` regularly
   - Track coverage percentage
   - Require 80%+ effective coverage

8. **Every new feature = new test**
   - No PR without tests
   - Test must validate UX, not just API

9. **Bug template includes test requirement**
   - Every bug report → create test that reproduces it
   - Fix the bug
   - Verify test now passes

## Conclusion

**Current State:**
- 33 tests pass ✓
- But they test the wrong things ✗
- Unit-level coverage is high, but integration coverage is near zero
- Tests don't catch real user-facing issues

**Required State:**
- 100+ tests ✓
- Tests validate real workflows ✓
- Tests catch UX issues (terminal spam, hangs, crashes) ✓
- Tests run on Windows with real console behavior ✓
- Every bug has a regression test ✓

**When you can trust your tests:**
- Tests fail BEFORE you fix a bug
- Tests pass AFTER you fix a bug
- Tests fail if you reintroduce the bug
- Running tests gives confidence that the app ACTUALLY WORKS

**Current tests say:** "The internal APIs work correctly"
**PhD-level tests should say:** "The app works correctly for real users in real scenarios"
