# Unpackr

**Modern CLI tool for automated Usenet video processing** - Clean, fast, reliable.

## What It Does

Fully automated download processor that turns messy Usenet folders into organized video collections:

1. **Repairs** - PAR2 verification & repair first
2. **Extracts** - Multi-part RAR archives (smart .part001 handling)
3. **Validates** - FFmpeg health checks on every video
4. **Moves** - Good videos saved immediately
5. **Cleans** - Corrupt files, samples, and junk deleted
6. **Protects** - Music/image/document folders preserved

**Smart Features:**
- Processes oldest folders first (ongoing downloads safe)
- Auto-kills orphaned processes from previous runs
- Multi-pass cleanup for locked files
- Configurable safety limits (timeouts, recursion depth)
- Real-time progress with animated status

**Modern Terminal UI:**
```
  unpackr

  [██████████░░░░░░░░░░] 45% │ 68/457
  found: 45  moved: 42  bad: 3  extracted: 8  repaired: 2  cleaned: 12  junk: 87
  speed: 2.0 folders/min  time left: 3:43:27  saved: 4.5 hrs

  > Validate video 1/2: Movie.Title.2024.mkv
  ⠙ working
```
- Clean ASCII art header with modern progress bar
- Live stats: success rate (found vs moved), work done (extracted/repaired), cleanup (folders/junk files)
- Time saved estimate (vs manual processing at ~4 min/folder)
- Animated spinner for continuous feedback
- Random easter egg comments for entertainment during long runs

**Defensive & Adaptive:**
- Automatic process cleanup on failures
- PowerShell fallback for stubborn deletions
- Retry logic with exponential backoff
- Multi-pass cleanup for locked files

## Typical Usenet Workflow

**The Problem:** Download folder with 50+ releases, each with:
- 700+ multi-part RAR files (.part001-.part710)
- PAR2 recovery files
- Subfolders with extracted videos
- NFO, SFV, URL junk files
- Maybe corrupt or incomplete downloads

**The Solution:** One command cleans everything
```powershell
python unpackr.py --source "G:\Downloads" --destination "G:\Videos"
```

**What Happens:**
1. Scans all folders (oldest first)
2. For each folder:
   - PAR2 verifies archives (repairs if needed, or deletes if corrupt)
   - Extracts .part001 only (7z handles the rest)
   - **Validates and moves videos one-by-one** (you see results immediately)
   - Deletes junk and cleans up
3. Multi-pass cleanup catches any locked files
4. **Result:** Clean download folder, all good videos in output

**What It Preserves:**
- Folders with music (3+ music files)
- Folders with images (5+ image files)
- Folders with documents
- Everything else gets cleaned

**You Come Back To:**
- ✅ All valid videos in your output folder
- ✅ Clean downloads folder (except preserved content)
- ✅ Detailed log of what happened
- ✅ No stuck processes or locked files

## Quick Start

```bash
# Install (creates 'unpackr' and 'unpackr-doctor' commands)
pip install -e .

# Check system setup
unpackr-doctor

# Run from anywhere
unpackr --source "C:\Downloads" --destination "D:\Videos"

# Or use positional arguments
unpackr "C:\source" "D:\destination"

# Or interactive mode (prompts for paths)
unpackr
```

## The Problem

Download folders cluttered with:
- Nested subfolders
- PAR2/RAR archives
- NFO/SFV junk files
- Sample videos
- Corrupt files

Manually extracting, validating, and organizing wastes time.

## The Solution

Unpackr automates everything:
1. Extracts RAR archives
2. Repairs damaged files (PAR2)
3. Validates video health (FFmpeg)
4. Moves good videos to destination
5. Deletes corrupt files
6. Cleans up junk and empty folders

Smart Detection:
- Preserves music/document folders
- Removes sample files
- Skips content-only folders

## Installation

### 1. Install Unpackr

```bash
# Clone or download, then install
cd unpackr
pip install -e .
```

This installs:
- Python dependencies (tqdm, psutil, colorama)
- Creates `unpackr` and `unpackr-doctor` commands globally

### 2. Install External Tools

**Required:**
- **7-Zip** - RAR extraction ([download](https://www.7-zip.org/))
- **par2cmdline** - PAR2 repair ([download](https://github.com/Parchive/par2cmdline))

**Optional:**
- **ffmpeg** - Video validation ([download](https://ffmpeg.org/))

The config automatically searches common install locations. To specify custom paths, edit `config_files/config.json`:

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe", "7z"],
    "par2": ["bin\\par2.exe", "par2"],
    "ffmpeg": ["ffmpeg"]
  }
}
```

### 3. Verify Setup

```bash
unpackr-doctor
```

Runs diagnostics and reports any issues.

## Usage

### Interactive Mode

Just run without arguments and it will prompt you:
```powershell
python unpackr.py
```

### Command-Line Mode

Specify source and destination:
```powershell
# Long format
python unpackr.py --source "C:\Downloads" --destination "D:\Videos"

# Short format
python unpackr.py -s "C:\Downloads" -d "D:\Videos"
```

Or if installed as command:
```powershell
unpackr --source "C:\Downloads" --destination "D:\Videos"
unpackr -s "C:\Downloads" -d "D:\Videos"
```

### Dry-Run Mode (Test Without Changes)

Preview what would happen without actually moving/deleting anything:
```powershell
python unpackr.py --source "C:\Downloads" --destination "D:\Videos" --dry-run
```
Shows:
- Which videos would be moved
- Which files would be deleted
- Which folders would be cleaned
- All operations logged with `[DRY-RUN]` prefix

### Custom Configuration

Use a different config file:
```powershell
python unpackr.py --config "custom_config.json"
```

### Path Handling

Paths work with or without quotes:
```powershell
# With quotes (if spaces in path)
python unpackr.py --source "C:\My Downloads" --destination "D:\My Videos"

# Without quotes (if no spaces)
python unpackr.py --source C:\Downloads --destination D:\Videos
```

## What Happens During Processing

### 1. Pre-Scan Analysis
```
[PRE-SCAN] Analyzing 25/25 folders...
Found: 51 videos | 710 archives | 2 PAR2 sets | 127 junk files
```
Quickly scans and sorts folders by age (oldest first).

### 2. For Each Folder (Oldest First)

**Step 2a: PAR2 Verify/Repair** (if PAR2 files present)
```
Verifying/Repairing PAR2: Release.par2 (8 files, 45.3MB)
PAR2 verification passed (no repair needed) in 3.2s
```
- Verifies archive integrity first
- Only repairs if needed (faster!)
- If repair fails → deletes corrupted archives immediately

**Step 2b: Extract Archives** (only .part001, skips .part002+)
```
Extracting [34.2MB] Release.part001.rar
Extracted Release.part001.rar (34.2MB in 45.2s, 0.8MB/s)
```
- Filters multi-part RARs (only extracts first part)
- 7-Zip automatically handles remaining parts
- Real-time extraction speed display

**Step 2c: Process Videos** (immediate one-by-one)
```
Checking video: Movie.Title.2024.mkv
MOVED: Movie.Title.2024.mkv (1250.3MB) -> G:\out
```
- **Each video validated and moved immediately**
- You see videos appearing in output as they're processed
- Corrupt videos deleted on the spot

**Step 2d: Cleanup Folder**
- Deletes remaining junk (NFO, SFV, etc.)
- Attempts folder deletion (with retries)
- If locked → tracks for multi-pass cleanup later

### 3. Multi-Pass Cleanup (After All Folders)
```
Retry pass 1/3: Attempting 2 failed deletions...
Successfully deleted 2 folders on retry
```
- Re-attempts folders that were locked
- 3 passes with 30-second delays
- Kills blocking processes automatically

### Live Progress Display
```
  unpackr

  [████████████░░░░░░░░] 60% │ 18/30
  found: 24  moved: 21  bad: 3  extracted: 8  repaired: 5  cleaned: 15  junk: 142
  speed: 2.3 folders/min  time left: 0:08:45  saved: 1.2 hrs

  > Extracting: Release.part001.rar
  ⠙ working
```

**What You See:**
- **Progress bar** - Visual completion with modern block characters
- **Stats** - Videos (found/moved/bad), work done (extracted/repaired), cleanup (folders/junk files)
- **Speed & ETA** - Processing rate, time remaining, and time saved vs manual processing
- **Current action** - What's happening right now
- **Spinner** - Animated indicator (updates continuously during long operations)

### Final Summary
```
Moved: 51 videos | Extracted: 8 archives | Repaired: 5 PAR2
Deleted: 127 junk files | Cleaned: 25 folders
Failed: 2 folders (still locked - retry manually)
```

## Configuration

Edit `config_files/config.json` to customize:

```json
{
  "video_extensions": [".mp4", ".avi", ".mkv", ".mov", "..."],
  "music_extensions": [".mp3", ".flac", ".wav", "..."],
  "removable_extensions": [".nfo", ".sfv", ".url", "..."],
  "min_sample_size_mb": 50,
  "max_log_files": 5,
  "log_folder": "logs"
}
```

**What You Can Customize:**
- Video/music/image/document file extensions
- Minimum file counts to identify content folders
- Sample file size threshold
- Log retention (keeps last 5 by default)

## Examples

### Example 1: Clean Downloads Folder
```powershell
python unpackr.py --source "C:\Downloads" --destination "D:\Videos"
```
Processes everything in Downloads, moves videos to D:\Videos.

### Example 2: Test Mode
```powershell
python unpackr.py --source "C:\test" --destination "C:\test_output"
```
Test on a small folder first.

### Example 3: Network Drive
```powershell
python unpackr.py --source "\\NAS\downloads" --destination "D:\Videos"
```
Works with network paths.

## Safety Features

### Timeout Protection
- RAR extraction: 5 minutes per archive
- PAR2 repair: 10 minutes per operation
- Video validation: 60 seconds per file
- Global runtime: 4 hours total

### Loop Guards
- Max iterations with auto-breaks
- Recursion limits (10 levels)
- Stuck detection (5min)

### Input Validation
- Path validation (null bytes, traversal)
- State checks (disk space, permissions)
- Error recovery with retries

Designed to handle errors gracefully and avoid common hanging scenarios.

## Requirements

### Python Dependencies
- tqdm>=4.62.0
- psutil>=5.8.0
- colorama>=0.4.4

### External Tools
- 7-Zip (required)
- par2cmdline (optional)
- ffmpeg (optional)

## Testing

```powershell
python tests/test_comprehensive.py
python tests/test_safety.py
python tests/test_defensive.py
```

Total: 80+ tests

## Project Structure

```
Unpackr/
├── unpackr.py              # Main script (run this)
├── unpackr.bat             # Windows launcher (for command usage)
├── build.py                # Build standalone .exe
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── INSTALL.md              # Installation guide
│
├── bin/                    # External executables
├── config_files/           # Configuration
│   └── config.json
├── scripts/                # Utility scripts
├── core/                   # Business logic modules
├── utils/                  # Helper utilities
├── tests/                  # Test suites
├── docs/                   # Additional documentation
├── logs/                   # Runtime logs (auto-created)
└── archive/                # Historical versions
```

See `docs/PROJECT_STRUCTURE.md` for details.

## Install as Command (Optional)

To run `unpackr` from anywhere (instead of `python unpackr.py`):

```powershell
# Copy batch file to PATH (requires admin)
copy unpackr.bat C:\Windows\System32\

# Now run from anywhere:
cd C:\
unpackr --source "C:\Downloads" --destination "D:\Videos"
```

See `INSTALL.md` for other installation options (no admin, PATH setup, PowerShell alias).

For building standalone .exe, see `docs/BUILD.md`.

## Documentation

- README.md - This file
- INSTALL.md - Install as command guide
- docs/QUICK_REFERENCE.md - Quick start
- docs/PROJECT_STRUCTURE.md - Organization
- docs/BUILD.md - Build standalone .exe

## Troubleshooting

### "7-Zip not found"
Install 7-Zip and ensure it's in PATH. Usually installed to:
- `C:\Program Files\7-Zip\7z.exe`

### "Python not recognized" (when using unpackr.bat)
Add Python to PATH or use full command: `python unpackr.py`

### Videos not moving
- Check destination path exists and is writable
- Check logs for errors
- Verify videos are valid (not corrupted)

### Hangs/Slow Performance
- Timeouts will kick in (check configured limits)
- Large archives take time (5 min per archive)
- Network drives are slower than local

### Permission Errors
- Run as Administrator if needed
- Check folder permissions
- Some files may be locked by other processes

## Logging

Every run creates a log file:
```
logs/unpackr-20251009-143022.log
```

Logs include:
- Files processed
- Errors encountered
- Safety interventions (timeouts)
- Performance metrics
- Final statistics

Keeps last 5 logs by default (configurable).

## Frequently Asked Questions

**Q: Does it work on Linux/Mac?**
A: Written for Windows but could be adapted. Path handling and external tools would need adjustment.

**Q: Will it delete my files?**
A: Only junk files (NFO, SFV, etc.) and corrupt videos. Test on a copy first!

**Q: Can I undo operations?**
A: No undo. Files are moved/deleted. Always back up important data.

**Q: What if I want to keep sample files?**
A: Edit config.json and increase `min_sample_size_mb` to a large value (e.g., 1000).

**Q: Can I process multiple folders at once?**
A: Run it once per folder, or run multiple instances with different sources.

**Q: How do I update the script?**
A: Replace `unpackr.py` and module files. Config and logs are preserved.

## Disclaimer

**Use at your own risk.**

This utility performs file operations including:
- Moving files
- Deleting files
- Extracting archives

While designed with safety features, automated file handling carries risks:
- Accidental deletion
- File misplacement
- Data loss

**Recommendations:**
- Back up important data before running
- Test on non-critical folders first
- Review logs after processing
- Understand what it does before running

The developers are not responsible for data loss or damage.

## License

Use freely for personal or commercial purposes. No warranties provided.

## Credits

A personal utility project for automating video download cleanup. Built with defensive programming and safety mechanisms to handle real-world edge cases.

---

**For more details:** See docs/ folder for additional documentation.

**For issues:** Check logs/ folder for detailed error information.

**For updates:** Pull latest version and run tests to verify.