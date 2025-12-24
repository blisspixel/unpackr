# Unpackr

**Turn messy folders of archives into clean, working videos.**

You have folders full of multi-part RARs, PAR2 files, corrupted videos, samples, and junk files. Unpackr repairs what's fixable, extracts what's archived, validates what plays, and removes what doesn't. You get only the videos that work, organized and ready to watch.

**Conservative by design:** Unpackr only post-processes files already on your disk. It does not download content, manage clients, or connect to external services. It operates locally with fail-closed validation (when uncertain, reject rather than proceed), comprehensive logging, and clear audit trails.

## Before → After

```
Before (messy download folder):
MyVideo/
├── MyVideo.part01.rar
├── MyVideo.part02.rar
├── MyVideo.part03.rar
├── MyVideo.par2
├── MyVideo.vol00+01.par2
├── MyVideo.vol01+02.par2
├── sample.mkv (15MB)
├── MyVideo.nfo
├── MyVideo.sfv
└── Poster.jpg

After processing:
Destination/
└── MyVideo.mkv (validated, playable)

Source/ (cleaned up)
└── MyVideo/
    └── Poster.jpg (preserved - non-video content)
```

## What It Does (End-to-End)

1. **Repairs** - Runs PAR2 verification and repair on corrupted archives
2. **Extracts** - Unpacks multi-part RAR/7z archives
3. **Validates** - Checks videos play correctly (detects truncation, corruption)
4. **Moves** - Only working videos go to destination
5. **Cleans** - Removes junk files (NFO, SFV, samples) and empty folders
6. **Protects** - Preserves folders with music, images, or documents
7. **Reports** - Logs every operation with full context for audit

The workflow processes folders oldest-first (safe for ongoing downloads) and validates videos one-by-one so you see results immediately.

## What It Does NOT Do

- Does not download or fetch content from servers
- Does not manage download clients or automation tools
- Does not scrape metadata or rename based on online databases
- Does not organize by genre, year, or media library conventions
- Does not modify or delete files in the destination directory

## Mental Model

Think of Unpackr as a pipeline that transforms messy Usenet downloads into validated video files:

**Inputs:**
- Messy folders containing RAR archives, PAR2 files, videos, and junk files
- Source directory with mixed content (completed and ongoing downloads)

**Outputs:**
- Validated videos moved to destination directory
- Junk files removed (NFO, SFV, URL, etc.)
- Empty folders cleaned up
- Content folders preserved (music, images, documents)

**Guarantees (Safety Contract):**
- Never writes outside destination directory; all work happens in source directory
- Never deletes content folders (music/images/documents meeting configured thresholds)
- Never moves/deletes a video unless it passes health validation
- Fails closed when uncertain (rejects suspicious archives/videos)
- In dry-run mode, performs no destructive operations
- Destination is write-only (videos added, never modified or deleted)

**Failure Handling:**
- Automatic retries with exponential backoff
- Multi-pass cleanup for locked files
- Detailed logging of all operations and errors
- Run `unpackr-doctor` for diagnostics

This model guides all design decisions: definitive automation for unattended operation with strong safety guarantees.

## Safe First Run

```bash
# 1. Install dependencies
pip install -e .

# 2. Check system is ready (validates tools installed)
unpackr-doctor

# 3. Test on one folder first (dry-run mode - no changes made)
unpackr --source "G:\test_folder" --destination "G:\Videos" --dry-run

# 4. Review what would happen, then run for real
unpackr --source "G:\test_folder" --destination "G:\Videos"

# 5. Once confident, run on full directory
unpackr --source "G:\Downloads" --destination "G:\Videos"
```

**Dry-run mode** shows exactly what would happen without moving or deleting anything. All operations logged with `[DRY-RUN]` prefix. Always test on a single folder first before processing your entire collection.

**Note:** When running from the project directory, use the `unpackr` command (which runs `unpackr.bat`). From other directories, the installed command at `C:\Users\<you>\AppData\Roaming\Python\Python310\Scripts\unpackr.exe` is used.

## Installation

### 1. Install Python Package

```bash
cd unpackr
pip install -e .
```

This installs Python dependencies (tqdm, psutil, colorama) and creates three commands:
- `unpackr` - Main tool
- `unpackr-doctor` - Diagnostics
- `vhealth` - Video health checker (standalone utility)

### 2. Install External Tools

**Required:**
- **7-Zip** - For RAR extraction ([download](https://www.7-zip.org/))
- **par2cmdline** - For PAR2 repair ([download](https://github.com/Parchive/par2cmdline))

**Optional but recommended:**
- **ffmpeg** - For video validation ([download](https://ffmpeg.org/))
  - Without ffmpeg, video health checks are skipped (videos assumed good)

### 3. Configure Tool Paths (if needed)

The tool auto-detects common install locations. If your tools are elsewhere, edit `config_files/config.json`:

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe"],
    "par2": ["C:\\custom\\path\\par2.exe"],
    "ffmpeg": ["C:\\ffmpeg\\bin\\ffmpeg.exe"]
  }
}
```

Each tool path is an array - it tries paths in order until one works.

### 4. Verify Setup

```bash
unpackr-doctor
```

This checks:
- Python version (3.7+)
- Required packages installed
- External tools accessible
- Config file valid
- Write permissions
- Disk space

Fix any issues it reports before running.

## Usage

### Basic Usage

```bash
# From project directory
unpackr --source "G:\Downloads" --destination "G:\Videos"

# Short flags
unpackr -s "G:\Downloads" -d "G:\Videos"

# Positional (no flags)
unpackr "G:\Downloads" "G:\Videos"

# Interactive (prompts for paths)
unpackr
```

### Dry Run (Preview Mode)

Test without making changes:

```bash
unpackr --source "G:\test" --destination "G:\out" --dry-run
```

Shows what would happen without actually moving/deleting files. All operations logged with `[DRY-RUN]` prefix.

### Custom Config

```bash
unpackr --config "custom_config.json" -s "G:\Downloads" -d "G:\Videos"
```

### Video Health Check (Optional)

Run additional validation on destination after processing:

```bash
unpackr --vhealth -s "G:\Downloads" -d "G:\Videos"
```

Performs full health check on moved videos:
- Validates video integrity (full decode test)
- Detects corruption that may have slipped through
- Finds duplicate videos (exact matches and similar files)
- Identifies low quality videos (480p or lower, low bitrate)
- Prompts before deleting bad files

Not enabled by default (adds processing time). Recommended for important collections or if you notice playback issues.

## What Happens During Processing

### 1. Pre-Scan
```
[PRE-SCAN] Analyzing folders...
Found: 51 videos | 710 archives | 2 PAR2 sets | 127 junk files
```

Scans all folders and sorts by age (oldest first, so ongoing downloads aren't touched).

### 2. Process Each Folder

**PAR2 Repair (if PAR2 files present):**
- Verifies archive integrity first
- Repairs only if needed (faster)
- Deletes corrupted archives if repair fails

**Archive Extraction:**
- Extracts only `.part001` files (7-Zip handles the rest automatically)
- Skips `.part002+` to avoid duplicate extraction

**Video Validation:**
- **Comprehensive health checks** (new in recent update):
  - File size sanity checks
  - Duration and bitrate extraction
  - Truncation detection (rejects if <70% expected size)
  - Full decode test (verifies all frames readable)
  - Corruption keyword detection
- **Each video processed immediately** - you see results as they happen
- Corrupt/truncated videos are deleted, not moved

**Cleanup:**
- Deletes junk files (NFO, SFV, URL, etc.)
- Removes empty folders
- Tracks locked folders for retry

### 3. Multi-Pass Cleanup

Re-attempts folders that were locked:
- 3 passes with delays
- Auto-kills blocking processes
- Reports any still-locked folders at end

### Live Progress

```
  unpackr

  [████████████░░░░░░░░] 60% │ 18/30
  found: 24  moved: 21  bad: 3  extracted: 8  repaired: 5  cleaned: 15  junk: 142
  speed: 2.3 folders/min  time left: 0:08:45  saved: 36 min

  > Extracting: Release.part001.rar
  ⠙ working
```

Shows:
- Progress bar with percentage
- Stats: videos (found/moved/bad), work (extracted/repaired), cleanup (folders/junk)
- Speed, ETA, and time saved estimate (conservative 2 min/folder baseline)
- Current operation
- Animated spinner

**Random Comments:** Occasional progress messages appear during long runs (15% chance per folder, max once per 5 folders). On first run, `comments.sample.json` is copied to `comments.json` which you can customize. Your custom comments are gitignored so they stay private.

## Configuration

Edit `config_files/config.json`:

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe", "7z"],
    "par2": ["bin\\par2.exe", "par2"],
    "ffmpeg": ["ffmpeg"]
  },
  "video_extensions": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"],
  "music_extensions": [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma"],
  "image_extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
  "document_extensions": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx"],
  "removable_extensions": [".nfo", ".sfv", ".url", ".diz", ".txt", ".m3u"],
  "min_sample_size_mb": 50,
  "min_music_files": 3,
  "min_image_files": 5,
  "max_log_files": 5,
  "log_folder": "logs"
}
```

**Key settings:**
- `tool_paths` - Custom paths to external tools (arrays try in order)
- `min_sample_size_mb` - Videos smaller than this are considered samples (default: 50MB)
- `min_music_files` / `min_image_files` - How many files needed to preserve a folder
- `max_log_files` - Keep last N logs (default: 5)

## Safety Contract

Unpackr makes explicit promises about what it will and won't do. These guarantees are upheld through defensive coding, comprehensive validation, and fail-closed design:

### Core Guarantees

1. **Containment** - Never write outside destination directory; all extractions and operations stay within source directory
2. **Content Preservation** - Never delete folders meeting content thresholds (music ≥3 files, images ≥5 files, documents ≥1 file)
3. **Validated Operations** - Never move/delete a video unless it passes configured health checks
4. **Fail-Closed** - When validation is uncertain (corrupt archive list, unclear video state), reject rather than proceed
5. **Dry-Run Isolation** - In dry-run mode, perform zero destructive operations (no moves, deletes, or writes)
6. **Idempotent Operations** - File moves use atomic temp-file-then-rename; safe to retry without side effects
7. **Bounded Resources** - Runtime, recursion depth, and memory usage all have hard limits

### What Gets Deleted

Only these items are removed:
- Junk files (NFO, SFV, URL, DIZ, TXT, M3U) in folders with videos or archives
- Sample videos (< 50MB by default, configurable)
- Corrupt or truncated videos that fail health checks
- Empty folders (no files, only other empty folders)
- Folders after successful processing (all contents extracted/moved)

### What Never Gets Deleted

- Videos that pass health validation (moved to destination instead)
- Content folders with ≥3 music files, ≥5 images, or ≥1 document
- Folders with unrecognized file types (preserved as possibly important)
- Any file in destination directory (destination is write-only, never modified or deleted)

### How Safety is Enforced

- **Path validation** - All archive contents validated before extraction (no `..`, no absolute paths, no escapes)
- **Double-check pattern** - Folder state re-verified immediately before deletion (prevents race conditions)
- **Comprehensive logging** - Every operation logged with full context for audit
- **Multi-pass cleanup** - Locked folders retried with delays; never forced if still in use
- **Disk space checks** - 3x archive size verified free before extraction
- **Process isolation** - Subprocesses killed if timeout exceeded; resources cleaned up

This contract is tested by the test suite and upheld by all code paths. Future features (WAL-based transactions, policy engine) will strengthen these guarantees further.

## Common Failure Modes (and What Unpackr Does)

**Locked folder (file in use by another process)**
- Retries deletion with exponential backoff (3 attempts with delays)
- Falls back to PowerShell forced deletion if needed
- If still locked, logs and continues (reported at end)
- Never blocks entire run on single locked file

**Disk full during extraction**
- Checks 3x archive size available before starting
- If space runs out mid-extraction, logs error and skips
- Partial extractions cleaned up (no orphaned files)
- Continues with next folder

**Corrupt or incomplete archive**
- PAR2 repair attempted if PAR2 files present
- If repair fails or impossible, logs reason and deletes archives
- Folder marked for cleanup, never left in broken state
- Decision logged with full context

**Incomplete multi-part set (missing .part files)**
- 7-Zip extraction fails with clear error
- Logs specific missing parts
- Archives left in place for manual review
- Folder not deleted (might be ongoing download)

**Suspicious video (unusual codec, truncated, decode errors)**
- Fails closed: video deleted rather than moved to destination
- Reason logged (truncation detected, decode failed, etc.)
- Guarantees only working videos reach destination
- Conservative: when uncertain, reject

**Hung subprocess (extraction/repair takes too long)**
- Dynamic timeouts based on file size (50GB archives get 2 hours)
- If timeout exceeded, process killed cleanly
- Resources cleaned up (temp files, handles)
- Logs timeout with operation context

**Run with these diagnostics:** `unpackr-doctor` shows tool versions, paths, disk space, and validates configuration. When reporting issues, attach the debug output.

## Safety Features

### Security
- **Path traversal protection** - Archives validated before extraction to prevent malicious files from writing outside target directory
- **Command injection prevention** - All subprocess calls use array form with safe parameter handling
- **Buffer overflow protection** - Large operations use temp files instead of PIPE to prevent deadlock
- **Fail-closed validation** - When validation fails, assumes unsafe rather than proceeding

### Timeouts
- RAR extraction: Dynamic based on file size (min 5 min, max 2 hours)
- PAR2 repair: Dynamic based on PAR2 size (min 10 min, max 3 hours)
- Video validation: 60 seconds per file
- Global runtime: 4 hours total

### Protections
- Recursion limits (10 levels, reset per folder)
- Loop guards with auto-breaks
- Stuck detection (5 min timeout)
- Thread-safe progress updates
- Thread-safe statistics tracking
- Race condition prevention (double-check before deletion)
- Memory leak prevention (bounded deque for failure tracking)

### Validation
- Input sanitization (path traversal, null bytes)
- Configuration validation (numeric ranges, types, required fields)
- Disk space checks before extraction (3x archive size)
- File accessibility checks
- Atomic file operations (temp file + rename)

### Error Recovery
- Retry logic with exponential backoff
- Multi-pass cleanup for locked files
- Automatic process cleanup
- PowerShell fallback for stubborn deletions
- Graceful shutdown on interruption

## Recent Improvements

The codebase has undergone comprehensive security, stability, and performance improvements:

**Security (v1.1)**
1. **Path traversal protection** - Validates archive contents before extraction to prevent malicious files
2. **Command injection prevention** - Safe subprocess handling prevents shell injection attacks
3. **Buffer overflow protection** - Large operations use temp files to prevent deadlock

**Stability (v1.1)**
4. **Exception handler cleanup** - Proper spinner thread cleanup on all exit paths
5. **Memory leak fix** - Bounded deque prevents unbounded memory growth in long runs
6. **Race condition fix** - Double-check pattern prevents unsafe folder deletions
7. **Config validation** - Comprehensive validation with helpful error messages

**Performance (v1.2 - in progress)**
8. **Optimized scanning** - Uses os.scandir for 2-3x faster folder scanning with cached stats
9. **Dynamic timeouts** - File-size-based timeouts handle 50GB+ archives without timing out

**Quality (v1.0)**
10. **Enhanced video validation** - Catches truncated/corrupt videos that were previously missed
11. **Fixed PAR2 error detection** - Properly distinguishes repair failures from successes
12. **Disk space checking** - Validates space before extraction
13. **Thread safety** - Progress and stats updates are thread-safe
14. **Atomic file operations** - Files moved via temp file + atomic rename
15. **Per-folder recursion guards** - Recursion depth resets for each folder

All tests passing (33/33).

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Individual test suites
python -m pytest tests/test_comprehensive.py -v
python -m pytest tests/test_safety.py -v
python -m pytest tests/test_defensive.py -v
```

Total: 33 tests covering:
- Video validation (including enhanced checks)
- PAR2 error detection
- Safety limits and timeouts
- Input validation
- Path handling
- Config loading
- File operations

## Project Structure

```
unpackr/
├── unpackr.py              # Main entry point
├── unpackr.bat             # Windows launcher (for project dir usage)
├── doctor.py               # Diagnostics tool
├── setup.py                # Package installation
├── requirements.txt        # Python dependencies
│
├── config_files/           # Configuration
│   ├── config.json         # Main config
│   └── comments.json       # Easter egg comments
│
├── core/                   # Core processing modules
│   ├── __init__.py
│   ├── config.py           # Config loading/validation
│   ├── archive_processor.py # PAR2 repair, RAR extraction
│   ├── file_handler.py     # File operations (move, delete, sanitize)
│   └── video_processor.py  # Video validation
│
├── utils/                  # Utilities
│   ├── progress.py         # Progress display (thread-safe)
│   ├── safety.py           # Timeouts, loop guards, limits
│   ├── defensive.py        # Input validation, error recovery
│   └── system_check.py     # Tool detection
│
├── tests/                  # Test suites
│   ├── conftest.py         # Pytest fixtures
│   ├── test_comprehensive.py
│   ├── test_safety.py
│   ├── test_defensive.py
│   └── test_all.py
│
├── docs/                   # Documentation
├── logs/                   # Runtime logs (auto-created)
└── bin/                    # External tools (optional)
```

## How It Works (Technical)

### Architecture

1. **Pre-scan phase** - Classifies all folders (junk, content, or processable)
2. **Processing phase** - Oldest folders first
3. **Cleanup phase** - Multi-pass retry for locked files

### Folder Classification

- **Junk folders** - Empty or only junk files → deleted immediately
- **Content folders** - Music (3+ files), images (5+ files), documents → preserved
- **Video folders** - Everything else → processed

### Video Validation (Enhanced)

The video health check performs comprehensive validation:

1. **Size check** - Rejects files <1MB
2. **Metadata extraction** - Gets duration and bitrate via ffmpeg
3. **Duration validation** - Rejects files with no duration or <10 seconds
4. **Truncation detection** - Calculates expected size from bitrate/duration, rejects if actual <70%
5. **Full decode test** - Actually decodes video to end, checking for frame errors
6. **Corruption keywords** - Detects "Invalid data", "corrupt", "truncated", "moov atom not found", etc.

This catches partially extracted videos that have valid headers but incomplete/corrupt data.

### PAR2 Processing

Checks failure keywords FIRST (before success keywords):
- "repair failed"
- "repair impossible"
- "cannot repair"
- "insufficient"

This prevents false positives where corrupted archives were marked as OK.

### Archive Extraction

- Security validates all paths in archive before extraction (prevents path traversal attacks)
- Only extracts `.part001` files (7-Zip automatically handles remaining parts)
- Checks disk space before extraction (3x archive size for safety)
- Dynamic timeouts based on file size (handles 50GB+ archives)
- Logs extraction speed for monitoring

## Troubleshooting

### "7-Zip not found"
Install 7-Zip or add path to `tool_paths.7z` in config.json. Common location: `C:\Program Files\7-Zip\7z.exe`

### "par2cmdline not found"
Optional but recommended. Install from GitHub or add path to `tool_paths.par2` in config.json.

### "ffmpeg not found"
Optional. Without ffmpeg, video validation is skipped (videos assumed good). Install from ffmpeg.org for full validation.

### Videos not moving
- Check destination path exists and is writable
- Check logs for errors (`logs/unpackr-YYYYMMDD-HHMMSS.log`)
- Run with `--dry-run` to see what would happen
- Corrupt videos are deleted, not moved (check log for "Video health check FAILED")

### Hangs or slow performance
- Timeouts will trigger (check configured limits in safety.py)
- Large archives take time (~5 min per archive with 5min timeout)
- Network drives are slower than local
- Check logs for timeout messages

### Permission errors
- Run as Administrator if needed
- Check folder permissions
- Some files may be locked by other processes (multi-pass cleanup will retry)

### Command not found (when running `unpackr`)
From project directory: Make sure `unpackr.bat` exists (it was restored recently)
From other directories: Ensure Python Scripts directory is in PATH

## Logging

Every run creates a timestamped log:
```
logs/unpackr-20251224-143022.log
```

Logs include:
- All operations (extract, move, delete)
- Errors and warnings
- Safety interventions (timeouts, stuck detection)
- Video health check results (pass/fail with reasons)
- Performance metrics
- Final statistics

Keeps last 5 logs by default (configurable via `max_log_files`).

## Known Limitations

- **Windows-focused** - Designed for Windows (path handling, process management, batch files)
- **No undo** - File operations are permanent (moves and deletes are final)
- **Single-threaded** - Processes one folder at a time (multi-threading could cause issues with external tools)
- **FFmpeg required for full validation** - Without ffmpeg, videos are assumed good
- **Time estimates are estimates** - Based on 2 min/folder conservative baseline, actual varies widely

## FAQ

**Q: Will it delete my files?**
A: Only junk files (NFO, SFV, URL, etc.) and corrupt videos. Valid videos are moved, not deleted. Content folders (music/images/docs) are preserved. Test with `--dry-run` first.

**Q: Can I undo operations?**
A: No. Files are moved/deleted permanently. Back up important data before running.

**Q: What if I want to keep sample files?**
A: Set `min_sample_size_mb` to a large value (e.g., 5000) in config.json to effectively disable sample detection.

**Q: How do I know if a video was rejected?**
A: Check the log file. Search for "Video health check FAILED" to see which videos were rejected and why (truncated, corrupt, etc.).

**Q: Can I process multiple source folders?**
A: Run the tool multiple times with different sources, or manually combine folders before running.

**Q: Does it work on Linux/Mac?**
A: Not currently. Windows-specific features (batch files, process management, PowerShell fallback) would need adjustment.

**Q: How do I update?**
A: `git pull` (or download new version), then `pip install -e .` again. Config and logs are preserved.

## Disclaimer

**Use at your own risk.**

This tool performs automated file operations:
- Moving files
- Deleting files
- Extracting archives
- Killing processes

While designed with safety features, automated file handling has inherent risks:
- Accidental deletion
- File misplacement
- Data loss

**Strongly recommended:**
- Back up important data before running
- Test on non-critical folders first (use `--dry-run`)
- Review logs after processing
- Understand what the tool does before using it

The developers are not responsible for data loss or damage.

## Contributing

If you find bugs or have improvements:
1. Check logs for error details
2. Run tests to verify (`python -m pytest tests/`)
3. Document the issue clearly
4. Submit with reproduction steps

## License

Free to use for personal or commercial purposes. No warranties provided.

## Credits

Built as a personal utility to automate Usenet video processing. Designed with defensive programming and comprehensive safety mechanisms to handle real-world edge cases.

Recent improvements include enhanced video validation, thread safety, and comprehensive test coverage.

---

**Need help?** Check logs first (`logs/`), then run diagnostics (`unpackr-doctor`), then review this README.

**Coming back after 6 months?** Read "Recent Improvements" section above, run `unpackr-doctor` to verify setup, and check `tests/` to see what's covered.
