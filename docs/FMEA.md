# Failure Mode and Effects Analysis (FMEA)

## Document Purpose

This document provides an exhaustive enumeration of all identified failure modes in the unpackr system, their potential effects, severity ratings, detection methods, and mitigation strategies.

**FMEA Methodology:**
- **Severity (S):** Impact if failure occurs (1-10, 10 = catastrophic data loss)
- **Occurrence (O):** Likelihood of failure (1-10, 10 = very frequent)
- **Detection (D):** Ability to detect before impact (1-10, 10 = cannot detect)
- **RPN (Risk Priority Number):** S × O × D (higher = more critical)

**Status:** Living document - updated as new failure modes are identified

---

## Category 1: Disk I/O Failures

### FM-001: Disk Full During Archive Extraction

**Description:** Available disk space exhausted while extracting archive contents.

**Potential Effects:**
- Partial file extraction leaving incomplete/corrupt files
- Source archive deleted before extraction verified
- Destination folder in inconsistent state
- Further operations blocked

**Severity:** 8 (potential data loss if archive deleted)

**Occurrence:** 6 (common with large archives on limited storage)

**Detection:** 3 (disk space checked before extraction)

**RPN:** 144 (HIGH PRIORITY)

**Current Mitigations:**
- Pre-extraction disk space check with 1.5x buffer (`StateValidator.check_disk_space`)
- Extraction skipped if insufficient space
- Error logged with space requirements

**Recommended Improvements:**
- [ ] Implement progressive extraction (extract → validate → delete in batches)
- [ ] Add disk space monitoring during extraction
- [ ] Implement cleanup of partial extraction on failure
- [ ] Add user notification when approaching disk full

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_disk_full_during_extraction`

---

### FM-002: Permission Denied on File Delete

**Description:** Insufficient permissions to delete processed files after successful operations.

**Potential Effects:**
- Processed files remain in source, causing duplicates
- Cleanup operations fail silently
- Disk space not reclaimed
- Manual intervention required

**Severity:** 4 (no data loss, but operational issue)

**Occurrence:** 5 (moderate - depends on user permissions, AV software)

**Detection:** 5 (exceptions caught but may not be visible)

**RPN:** 100 (MEDIUM PRIORITY)

**Current Mitigations:**
- Exceptions caught and logged
- Processing continues for other files
- Error messages indicate manual cleanup needed

**Recommended Improvements:**
- [ ] Add permission check before processing
- [ ] Provide clear user guidance for permission issues
- [ ] Implement retry logic with user elevation prompt
- [ ] Create "needs manual cleanup" report

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_permission_denied_on_delete`

---

### FM-003: Permission Denied on File Move

**Description:** Cannot move validated video to destination due to permission restrictions.

**Potential Effects:**
- Validated video stuck in source location
- Destination incomplete
- Processing appears successful but file not moved
- User confusion about file location

**Severity:** 6 (operational failure, no data loss but missed objective)

**Occurrence:** 4 (less common than delete permission issues)

**Detection:** 4 (exception caught but outcome unclear)

**RPN:** 96 (MEDIUM PRIORITY)

**Current Mitigations:**
- Move failures caught and logged
- Source file remains untouched
- Error message with file details

**Recommended Improvements:**
- [ ] Pre-flight permission check on destination
- [ ] Fallback copy mechanism if move fails
- [ ] Clear reporting of unmoved files
- [ ] Option to run with elevated privileges

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_permission_denied_on_move`

---

### FM-004: Read Error During Validation

**Description:** I/O error when reading video file for health validation.

**Potential Effects:**
- Video cannot be validated (false negative)
- May be incorrectly classified as corrupt
- Disk errors not distinguished from corrupt files
- Potentially good video rejected

**Severity:** 5 (incorrect rejection of valid files)

**Occurrence:** 3 (rare - usually indicates hardware issues)

**Detection:** 6 (errors caught but root cause ambiguous)

**RPN:** 90 (MEDIUM PRIORITY)

**Current Mitigations:**
- Read exceptions caught and logged
- Video marked as failed validation
- Other videos continue processing

**Recommended Improvements:**
- [ ] Distinguish I/O errors from corruption
- [ ] Implement retry logic for transient errors
- [ ] S.M.A.R.T. disk health check integration
- [ ] Separate reporting for hardware vs file issues

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_read_error_during_validation`

---

### FM-005: Disk Full Mid-Write

**Description:** Disk fills up while writing a file.

**Potential Effects:**
- Partial file written and left on disk
- No cleanup of incomplete file
- Disk space consumed by unusable file
- Subsequent operations may fail

**Severity:** 5 (disk space wasted, cleanup needed)

**Occurrence:** 5 (can happen with large files)

**Detection:** 4 (exception caught but cleanup may not occur)

**RPN:** 100 (MEDIUM PRIORITY)

**Current Mitigations:**
- Write exceptions caught
- Error logged

**Recommended Improvements:**
- [ ] Implement write transaction pattern (write to temp, then rename)
- [ ] Add cleanup of partial writes on exception
- [ ] Verify file integrity after write
- [ ] Add to temp file cleanup verification (I9)

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_disk_full_mid_write`

---

## Category 2: Archive Extraction Failures

### FM-010: Corrupt Archive Header

**Description:** Archive file has corrupt or invalid header, preventing 7z from reading metadata.

**Potential Effects:**
- Extraction fails immediately
- Cannot determine if archive is incomplete vs corrupt
- Archive may be incorrectly deleted
- Loss of potentially recoverable data

**Severity:** 7 (potential data loss if deleted)

**Occurrence:** 4 (moderate - corrupt downloads, disk errors)

**Detection:** 3 (7z exit code indicates error)

**RPN:** 84 (MEDIUM PRIORITY)

**Current Mitigations:**
- Extraction errors detected via exit code
- Archives preserved on extraction failure
- Error logged with 7z output

**Recommended Improvements:**
- [ ] Implement archive validation before extraction attempt
- [ ] Try multiple extraction methods (7z, unrar, fallback)
- [ ] Distinguish corruption from incomplete download
- [ ] Move corrupt archives to quarantine vs delete

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_corrupt_archive_header`

---

### FM-011: Incomplete Multi-Part Archive

**Description:** Multi-part archive set is incomplete (missing .part001, .part003, etc.).

**Potential Effects:**
- Extraction fails mid-process
- Partial extraction left behind
- User unclear which parts are missing
- Manual intervention difficult

**Severity:** 5 (extraction fails, but detectable)

**Occurrence:** 6 (common with failed downloads)

**Detection:** 4 (detected during extraction, not before)

**RPN:** 120 (HIGH PRIORITY)

**Current Mitigations:**
- Extraction failures caught
- Warning logged for incomplete 7z sets (FM detects .7z.100 without .7z.001)

**Recommended Improvements:**
- [ ] Pre-extraction validation of part completeness
- [ ] Clear reporting of which parts are missing
- [ ] Keep incomplete sets for potential completion
- [ ] Generate checksums for partial sets

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_incomplete_multipart_archive`

---

### FM-012: Extraction Timeout

**Description:** Archive extraction exceeds configured timeout (stuck process, extremely large file).

**Potential Effects:**
- Extraction process killed
- Partial extraction left behind
- Source archive state unclear
- User unsure if retry would help

**Severity:** 6 (operational failure, potential partial state)

**Occurrence:** 3 (rare - very large files or corrupt archives)

**Detection:** 2 (timeout explicitly detected)

**RPN:** 36 (LOW PRIORITY)

**Current Mitigations:**
- Dynamic timeout calculation based on file size
- Process killed after timeout
- Timeout logged with file details
- Extended timeout for large files (>1GB)

**Recommended Improvements:**
- [ ] Add progress monitoring during extraction
- [ ] Distinguish hung process from slow extraction
- [ ] Implement resumable extraction
- [ ] Adaptive timeout based on observed extraction speed

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_extraction_timeout`

---

### FM-013: Password Protected Archive

**Description:** Archive requires password for extraction, not provided.

**Potential Effects:**
- Extraction fails with password error
- Archive preserved but cannot process
- User unclear which archives need passwords
- Manual intervention required for each

**Severity:** 3 (no data loss, operational block)

**Occurrence:** 5 (moderate - depends on source)

**Detection:** 2 (7z error clearly indicates password needed)

**RPN:** 30 (LOW PRIORITY)

**Current Mitigations:**
- Password errors detected from 7z output
- Archive preserved (not deleted)
- Error logged

**Recommended Improvements:**
- [ ] Maintain password database/keychain
- [ ] Prompt user for password interactively
- [ ] Mark password-protected archives for batch processing
- [ ] Support password files (passwords.txt)

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_password_protected_archive`

---

### FM-014: Path Traversal in Archive (SECURITY)

**Description:** Archive contains paths like `../../etc/passwd` attempting to write outside destination.

**Potential Effects:**
- **CRITICAL:** Files written to arbitrary locations
- Potential system compromise
- Overwrite of critical system files
- Privilege escalation vector

**Severity:** 10 (CRITICAL SECURITY VULNERABILITY)

**Occurrence:** 2 (rare but exists in malicious archives)

**Detection:** 1 (validation explicitly checks before extraction)

**RPN:** 20 (LOW DUE TO DETECTION, BUT CRITICAL IF MISSED)

**Current Mitigations:**
- `_validate_archive_paths()` checks all paths before extraction
- Extractions blocked if path traversal detected
- SECURITY warning logged
- Archive preserved for analysis
- Safety Invariant I1 enforces destination boundary

**Recommended Improvements:**
- [ ] Double validation (before + during extraction)
- [ ] Security audit log for blocked archives
- [ ] Automatic reporting of malicious archives
- [ ] Hash-based malware detection integration

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_path_traversal_in_archive`

---

### FM-015: Nested Archive Loop (Zip Bomb)

**Description:** Archive contains archive contains archive... (decompression bomb).

**Potential Effects:**
- Infinite extraction loop
- Disk space exhaustion
- System resource exhaustion
- Operation never completes

**Severity:** 8 (resource exhaustion, potential DOS)

**Occurrence:** 2 (rare - malicious archives or accidents)

**Detection:** 2 (loop counter explicitly enforced)

**RPN:** 32 (LOW PRIORITY)

**Current Mitigations:**
- `archive_extraction_loop_limit` enforced (default 100)
- Loop counter incremented for each extraction
- Error logged when limit reached
- Extraction terminated

**Recommended Improvements:**
- [ ] Track expansion ratio (compressed vs extracted size)
- [ ] Enforce maximum total extracted size
- [ ] Detect circular archive references
- [ ] Whitelist known safe nested archives

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_nested_archives_loop_prevention`

---

## Category 3: Video Processing Failures

### FM-020: Corrupt Video Header

**Description:** Video file has corrupt header, ffprobe cannot parse metadata.

**Potential Effects:**
- Cannot determine video properties
- May incorrectly reject valid video
- Cannot calculate expected file size
- Validation inconclusive

**Severity:** 5 (operational issue, potentially false negative)

**Occurrence:** 5 (moderate - corrupt downloads, encoding errors)

**Detection:** 3 (ffprobe error detected, but ambiguous)

**RPN:** 75 (MEDIUM PRIORITY)

**Current Mitigations:**
- ffprobe errors caught
- Video marked as corrupt/failed
- Error logged with ffprobe output

**Recommended Improvements:**
- [ ] Attempt header repair with ffmpeg
- [ ] Try alternative metadata parsers
- [ ] Distinguish corrupt header from corrupt stream
- [ ] Partial validation for videos with readable portions

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_corrupt_video_header`

---

### FM-021: Missing Video Metadata

**Description:** Video file has no duration, resolution, or bitrate in metadata.

**Potential Effects:**
- Cannot perform quality checks
- Cannot validate file size
- Unknown if video is playable
- May incorrectly accept/reject

**Severity:** 4 (reduces validation effectiveness)

**Occurrence:** 4 (uncommon but possible with exotic formats)

**Detection:** 6 (missing fields not always detected)

**RPN:** 96 (MEDIUM PRIORITY)

**Current Mitigations:**
- Metadata parsing uses defaults if fields missing
- Validation continues with available information

**Recommended Improvements:**
- [ ] Explicitly detect missing required fields
- [ ] Perform decode test when metadata insufficient
- [ ] Mark videos with missing metadata for review
- [ ] Support broader metadata sources (MediaInfo, ExifTool)

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_video_missing_metadata`

---

### FM-022: Video Decode Timeout

**Description:** Video decode test hangs (infinite loop in decoder, corrupt frames).

**Potential Effects:**
- ffmpeg process hangs indefinitely
- Resource consumption (CPU, memory)
- Validation pipeline stalls
- User intervention required

**Severity:** 6 (operational failure, resource leak)

**Occurrence:** 3 (uncommon - usually malformed streams)

**Detection:** 2 (timeout explicitly enforced)

**RPN:** 36 (LOW PRIORITY)

**Current Mitigations:**
- Decode test uses explicit timeout
- Process killed after timeout
- Video marked as failed
- Timeout logged

**Recommended Improvements:**
- [ ] Adaptive timeout based on video duration
- [ ] Monitor decode progress (frame count)
- [ ] Detect stuck decoder vs slow decode
- [ ] Sample-based decode (test multiple segments)

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_video_decode_timeout`

---

### FM-023: Truncated Video File

**Description:** Video file incomplete (download interrupted, disk full during write).

**Potential Effects:**
- Plays partially then fails
- Incorrect file size detection
- May pass validation but fail during playback
- User discovers issue after processing

**Severity:** 7 (false positive - bad video accepted)

**Occurrence:** 6 (common - interrupted downloads)

**Detection:** 3 (size validation detects most cases)

**RPN:** 126 (HIGH PRIORITY)

**Current Mitigations:**
- Size validation (actual vs expected from bitrate × duration)
- Rejection if actual < 70% of expected
- Decode test samples video

**Recommended Improvements:**
- [ ] Check for EOF marker in container format
- [ ] Verify index/seek table completeness
- [ ] Decode test should sample end of file
- [ ] Compare file size to container metadata

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_video_truncated_file`

---

### FM-024: Silent Data Corruption

**Description:** Video file corrupted but still parseable (bit flips, bad sectors).

**Potential Effects:**
- Passes validation but has artifacts
- Corruption discovered during playback
- User receives defective file
- Reputation damage

**Severity:** 8 (defective output, not detected)

**Occurrence:** 2 (rare but possible)

**Detection:** 8 (very difficult to detect)

**RPN:** 128 (HIGH PRIORITY)

**Current Mitigations:**
- Decode test samples video
- Corrupt frames may cause decode failure

**Recommended Improvements:**
- [ ] Implement checksum verification (if available)
- [ ] Full decode test option (slow but thorough)
- [ ] Compare hash before/after operations
- [ ] Detect frame decode errors during sample
- [ ] Add provenance tracking with checksums

**Test Coverage:** Not yet implemented

---

## Category 4: Resource Exhaustion

### FM-030: File Handle Exhaustion

**Description:** System limit on open files reached due to leaks or large batch processing.

**Potential Effects:**
- Cannot open new files
- Processing fails with cryptic errors
- Operations may hang
- Requires process restart

**Severity:** 6 (operational failure)

**Occurrence:** 3 (uncommon - OS limits are typically high)

**Detection:** 5 (error indicates "too many open files" but may be unclear)

**RPN:** 90 (MEDIUM PRIORITY)

**Current Mitigations:**
- Files opened and closed in limited scope
- Context managers ensure cleanup

**Recommended Improvements:**
- [ ] Implement file handle pooling
- [ ] Monitor open handle count
- [ ] Process in smaller batches if limit approached
- [ ] Explicit leak detection in tests
- [ ] Add to Safety Invariant I9 (resource cleanup)

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_too_many_open_files`

---

### FM-031: Memory Exhaustion

**Description:** System runs out of memory during processing of very large files.

**Potential Effects:**
- Process killed by OOM killer
- System thrashing (swap usage)
- Other applications affected
- Data corruption if killed mid-write

**Severity:** 8 (system instability, potential data loss)

**Occurrence:** 3 (uncommon unless processing massive files)

**Detection:** 6 (may crash before detection)

**RPN:** 144 (HIGH PRIORITY)

**Current Mitigations:**
- Streaming processing where possible
- No full-file reads for large files

**Recommended Improvements:**
- [ ] Monitor memory usage during operations
- [ ] Implement memory limits per operation
- [ ] Use memory-mapped files for large reads
- [ ] Batch processing with memory quotas
- [ ] Graceful degradation when memory low

**Test Coverage:** Partial (injector exists but full tests not implemented)

---

### FM-032: Zip Bomb Expansion

**Description:** Archive expands to many GB despite being small (10MB → 10GB).

**Potential Effects:**
- Disk space exhausted unexpectedly
- System becomes unstable
- Other operations fail
- Long cleanup time required

**Severity:** 7 (disk space exhaustion)

**Occurrence:** 2 (rare - malicious archives)

**Detection:** 3 (pre-extraction space check helps, but may not catch)

**RPN:** 42 (LOW-MEDIUM PRIORITY)

**Current Mitigations:**
- Disk space check with 1.5x buffer
- Extraction skipped if insufficient space

**Recommended Improvements:**
- [ ] Check compressed vs uncompressed size before extraction
- [ ] Enforce maximum expansion ratio (e.g., 100:1)
- [ ] Progressive extraction with monitoring
- [ ] Abort if expansion exceeds threshold

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_very_large_archive_extraction`

---

### FM-033: Archive with Thousands of Small Files

**Description:** Archive contains 10,000+ small files (many metadata operations).

**Potential Effects:**
- Slow extraction due to file creation overhead
- High memory usage for file tracking
- Filesystem metadata overhead
- Progress appears hung

**Severity:** 4 (performance issue)

**Occurrence:** 5 (common with image collections, documentation)

**Detection:** 2 (can track file count during extraction)

**RPN:** 40 (LOW PRIORITY)

**Current Mitigations:**
- Progress callbacks provide user feedback
- No inherent file count limit

**Recommended Improvements:**
- [ ] Warn user about high file count
- [ ] Batch file creation operations
- [ ] Optimize for many-small-files scenario
- [ ] Consider rejecting non-video archives with excessive files

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_thousands_of_small_files_in_archive`

---

## Category 5: Timing and Concurrency

### FM-040: File Deleted During Processing

**Description:** File deleted by external process (user, antivirus, other tool) while being processed.

**Potential Effects:**
- FileNotFoundError during operations
- Inconsistent state (validation passed but file gone)
- Confusing error messages
- May incorrectly report success

**Severity:** 5 (operational failure, confusing state)

**Occurrence:** 4 (moderate - depends on user behavior, AV software)

**Detection:** 3 (FileNotFoundError caught, but late in pipeline)

**RPN:** 60 (MEDIUM PRIORITY)

**Current Mitigations:**
- File existence checked at various points
- Exceptions caught and logged

**Recommended Improvements:**
- [ ] Implement file locking during processing
- [ ] Detect file vanishing vs never existed
- [ ] Clearer error messages for this specific case
- [ ] Add provenance tracking to detect external modification

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_file_deleted_during_processing`

---

### FM-041: File Modified During Processing

**Description:** File contents change while being processed (in-place update, corruption).

**Potential Effects:**
- Validation based on old content, operation on new
- Inconsistent results
- May accept corrupt version
- Difficult to debug

**Severity:** 7 (data integrity issue)

**Occurrence:** 3 (uncommon unless user actively modifying)

**Detection:** 8 (very difficult to detect)

**RPN:** 168 (HIGH PRIORITY)

**Current Mitigations:**
- None currently

**Recommended Improvements:**
- [ ] **Implement hash verification before/after critical operations**
- [ ] **File locking to prevent concurrent modification**
- [ ] **Detect mtime changes during processing**
- [ ] **Add to Safety Invariant I10 (provenance with hashing)**

**Test Coverage:** Not yet implemented

---

### FM-042: Filesystem Becomes Read-Only

**Description:** Filesystem remounted read-only (disk errors, admin action, USB unplugged).

**Potential Effects:**
- Write operations fail with permission errors
- Confusion between permission denied and read-only FS
- Cannot complete processing
- Partial state left behind

**Severity:** 6 (operational failure)

**Occurrence:** 2 (rare unless hardware issues)

**Detection:** 5 (error indicates permission denied, not read-only)

**RPN:** 60 (MEDIUM PRIORITY)

**Current Mitigations:**
- Write exceptions caught
- Error logged

**Recommended Improvements:**
- [ ] Detect read-only filesystem specifically
- [ ] Provide clear guidance for read-only condition
- [ ] Offer to retry when filesystem writeable again
- [ ] Pre-flight filesystem writability check

**Test Coverage:** `tests/chaos/test_chaos_scenarios.py::test_filesystem_becomes_readonly`

---

### FM-043: Race Condition in Folder Cleanup

**Description:** Multiple processes attempt to clean up same folder simultaneously.

**Potential Effects:**
- FileNotFoundError during cleanup
- Incomplete cleanup
- Error logs despite successful outcome
- Confusion about which process owns folder

**Severity:** 3 (cosmetic issue, no data loss)

**Occurrence:** 3 (uncommon unless running multiple instances)

**Detection:** 6 (errors logged but may be harmless)

**RPN:** 54 (MEDIUM PRIORITY)

**Current Mitigations:**
- Exceptions during cleanup caught
- Cleanup failures logged but not fatal

**Recommended Improvements:**
- [ ] Implement folder-level locking
- [ ] Detect ENOENT errors as non-failures
- [ ] Coordinate cleanup between processes
- [ ] Add idempotency to cleanup operations

**Test Coverage:** Not yet implemented

---

## Category 6: Configuration and State

### FM-050: Missing Required Configuration

**Description:** Config object missing required attributes (video_extensions, removable_extensions).

**Potential Effects:**
- FileHandler initialization fails
- ValidationError raised
- Processing cannot start
- May fail after partial processing

**Severity:** 7 (complete operational failure)

**Occurrence:** 2 (rare - would be caught in development)

**Detection:** 1 (explicit validation at initialization)

**RPN:** 14 (LOW PRIORITY)

**Current Mitigations:**
- Config validation at FileHandler init
- ValidationError with clear message
- Defensive checks in utils.defensive

**Recommended Improvements:**
- [ ] Schema validation for Config object
- [ ] Default values for all optional config
- [ ] Config validation tool/script
- [ ] Fail-fast on startup with config errors

**Test Coverage:** `tests/test_file_handler.py::test_init_with_invalid_config`

---

### FM-051: Corrupted Application State

**Description:** Internal state (ValidationCache, stats) becomes inconsistent due to exception.

**Potential Effects:**
- Incorrect decisions based on stale state
- Memory leaks from uncleaned cache
- False positives/negatives in validation
- Difficult to debug

**Severity:** 6 (incorrect behavior)

**Occurrence:** 3 (possible if exceptions occur)

**Detection:** 7 (very difficult to detect)

**RPN:** 126 (HIGH PRIORITY)

**Current Mitigations:**
- Limited - cache is module-level dictionary
- Cache cleared in test fixtures

**Recommended Improvements:**
- [ ] **Implement state checkpointing**
- [ ] **Add state validation invariants**
- [ ] **Automatic state reset on errors**
- [ ] **Immutable state where possible**
- [ ] **Add to Safety Invariant system**

**Test Coverage:** Partial (cache clearing tested, corruption not tested)

---

## Category 7: External Dependencies

### FM-060: 7z Binary Not Found

**Description:** 7z executable not available on system PATH.

**Potential Effects:**
- Archive extraction fails completely
- All archives skipped
- Error messages may be unclear
- User must install 7z manually

**Severity:** 8 (complete feature failure)

**Occurrence:** 5 (moderate - depends on user environment)

**Detection:** 2 (subprocess will fail clearly)

**RPN:** 80 (MEDIUM-HIGH PRIORITY)

**Current Mitigations:**
- Subprocess errors caught
- Error logged

**Recommended Improvements:**
- [ ] Check for 7z on startup
- [ ] Provide clear installation instructions
- [ ] Support alternative extractors (unrar, unzip)
- [ ] Bundle 7z or provide installer
- [ ] Graceful degradation (skip archives)

**Test Coverage:** Not yet implemented

---

### FM-061: ffmpeg/ffprobe Not Found

**Description:** ffmpeg/ffprobe not available for video validation.

**Potential Effects:**
- Video validation completely disabled
- Cannot determine video quality
- All videos accepted or all rejected
- Core functionality unavailable

**Severity:** 9 (critical feature loss)

**Occurrence:** 5 (moderate - depends on user environment)

**Detection:** 2 (subprocess will fail clearly)

**RPN:** 90 (HIGH PRIORITY)

**Current Mitigations:**
- Subprocess errors caught
- Error logged

**Recommended Improvements:**
- [ ] **Check for ffmpeg on startup**
- [ ] **Fail fast with clear message**
- [ ] **Provide installation instructions**
- [ ] **Fall back to basic checks (extension, size)**
- [ ] **Bundle ffmpeg or provide installer**

**Test Coverage:** Not yet implemented

---

### FM-062: par2 Binary Not Found

**Description:** par2 not available for PAR2 repair operations.

**Potential Effects:**
- PAR2 repair skipped
- Corrupt archives not repaired
- Downloads with errors remain corrupt
- Feature silently disabled

**Severity:** 5 (feature loss, but not critical)

**Occurrence:** 6 (common - par2 less widely installed)

**Detection:** 3 (errors logged but may go unnoticed)

**RPN:** 90 (HIGH PRIORITY)

**Current Mitigations:**
- PAR2 errors caught
- Processing continues without repair

**Recommended Improvements:**
- [ ] Check for par2 on startup
- [ ] Warn user if par2 unavailable
- [ ] Provide installation instructions
- [ ] Bundle par2 or provide installer
- [ ] Clearer logging when PAR2 skipped

**Test Coverage:** Not yet implemented

---

## Category 8: User Input and CLI

### FM-070: Invalid Path Provided

**Description:** User provides non-existent or invalid path as input.

**Potential Effects:**
- Operation fails immediately
- Confusing error message
- Wasted user time
- May crash if not handled

**Severity:** 3 (user error, no data loss)

**Occurrence:** 7 (common user error)

**Detection:** 2 (can validate immediately)

**RPN:** 42 (LOW-MEDIUM PRIORITY)

**Current Mitigations:**
- Path existence checked in processing
- Errors logged

**Recommended Improvements:**
- [ ] Validate paths before starting processing
- [ ] Provide clear error messages
- [ ] Suggest corrections (typos)
- [ ] Interactive path picker for GUI

**Test Coverage:** `tests/test_file_handler.py::test_find_video_files_nonexistent_path`

---

### FM-071: Relative Path Confusion

**Description:** User provides relative path, unclear what it's relative to.

**Potential Effects:**
- Wrong directory processed
- Files moved to unexpected location
- User confusion about results
- Data organization incorrect

**Severity:** 6 (incorrect operation)

**Occurrence:** 5 (common user confusion)

**Detection:** 4 (path resolves, but to wrong location)

**RPN:** 120 (HIGH PRIORITY)

**Current Mitigations:**
- Paths resolved to absolute
- Working directory maintained

**Recommended Improvements:**
- [ ] Always display absolute paths in logs
- [ ] Confirm with user before starting
- [ ] Require absolute paths in config
- [ ] Show source → destination mapping before processing

**Test Coverage:** Not yet implemented

---

## Summary Statistics

**Total Failure Modes Documented:** 31

**By Severity:**
- Critical (9-10): 3
- High (7-8): 9
- Medium (4-6): 15
- Low (1-3): 4

**By RPN (Risk Priority Number):**
- Critical (>150): 3
- High (100-150): 9
- Medium (50-99): 11
- Low (<50): 8

**Top 10 Highest Risk (by RPN):**
1. FM-041: File Modified During Processing (RPN: 168)
2. FM-001: Disk Full During Extraction (RPN: 144)
3. FM-031: Memory Exhaustion (RPN: 144)
4. FM-024: Silent Data Corruption (RPN: 128)
5. FM-023: Truncated Video File (RPN: 126)
6. FM-051: Corrupted Application State (RPN: 126)
7. FM-011: Incomplete Multi-Part Archive (RPN: 120)
8. FM-071: Relative Path Confusion (RPN: 120)
9. FM-002: Permission Denied on File Delete (RPN: 100)
10. FM-005: Disk Full Mid-Write (RPN: 100)

---

## Next Actions

**Immediate (Critical RPN > 150):**
1. Implement hash verification before/after operations (FM-041)
2. Add file locking during processing (FM-041)
3. Implement state checkpointing (FM-051)

**High Priority (RPN 100-150):**
1. Progressive archive extraction with validation (FM-001)
2. Implement memory monitoring and limits (FM-031)
3. EOF marker validation for videos (FM-023, FM-024)
4. Multi-part archive pre-validation (FM-011)

**Medium Priority (RPN 50-99):**
1. Check for external tool availability on startup (FM-060, FM-061, FM-062)
2. Implement retry logic for transient errors (FM-004)
3. Add file locking for concurrent operations (FM-040, FM-043)

**Continuous:**
- Update this document as new failure modes discovered
- Add test coverage for all documented failure modes
- Track RPN reduction over time as mitigations implemented

---

**Document Version:** 1.0
**Last Updated:** 2025-12-26
**Next Review:** When implementing Phase 0 or Phase 1 features
