# Unpackr

**Set It and Forget It** - Your Automated Usenet Video Cleanup Tool

## What It Does

**Fully automated Usenet/newsgroup download processor** that handles messy download folders:

1. **Verifies/Repairs** with PAR2 first (required for Usenet)
2. **Extracts** multi-part RAR archives (handles .part001-.part999)
3. **Validates** video health with FFmpeg
4. **Moves** good videos immediately (one-by-one as validated)
5. **Deletes** corrupt files, samples, and junk
6. **Cleans up** automatically with multi-pass locked file handling

**Usenet-Optimized Workflow:**
- Processes oldest folders first (handles ongoing downloads)
- PAR2 verify/repair before extraction (saves time on good files)
- Multi-part RAR filtering (only extracts .part001, not every part)
- Handles folders with brackets and special characters
- Automatically kills stuck processes (7z, par2, ffmpeg)

**Modern Progress Display:**
- Real-time stats (videos moved, archives extracted, speed)
- Live throughput metrics (folders/min)
- Detailed operation logging (extraction speed, file sizes)
- Multi-line progress with ETA

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

### Automated Installation (Recommended)
```powershell
# Run the installer script
.\install.ps1        # PowerShell version (full-featured)
# OR
.\install.bat        # Batch version (simple)
```

### Manual Installation
```powershell
# Install dependencies
pip install -r requirements.txt

# Run interactive mode
python unpackr.py

# Run with arguments
python unpackr.py --source "G:\Downloads" --destination "G:\Videos"
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

### Step 1: Install Python Dependencies

```powershell
pip install -r requirements.txt
```

This installs: tqdm, psutil, colorama

### Step 2: Configure External Tools

**Required** (critical for Usenet):
- **7-Zip** - For RAR extraction ([download](https://www.7-zip.org/))
- **par2cmdline** - For PAR2 repair (included in `bin/par2.exe` or [download](https://github.com/Parchive/par2cmdline))

**Optional** (recommended):
- **ffmpeg** - For video health validation

**Easy Configuration:**
```powershell
# Run the tool configurator
python configure_tools.py
# OR
configure_tools.bat
```

**Manual Configuration:**
Edit `config_files/config.json` and set the `tool_paths` section:
```json
{
  "tool_paths": {
    "7z": "C:\\Program Files\\7-Zip\\7z.exe",
    "par2": "par2",
    "ffmpeg": "ffmpeg"
  }
}
```

The script will automatically use these paths instead of requiring tools in your PATH.

### Step 3 (Optional): Install as Command

If you want to run `unpackr` from anywhere (instead of `python unpackr.py`):

**Simple Method (Requires Admin):**
```powershell
copy unpackr.bat C:\Windows\System32\
```

Now you can run from any directory:
```powershell
cd C:\
unpackr --source "C:\Downloads" --destination "D:\Videos"
```

**Alternative (No Admin Required):**
Add your Unpackr folder to your PATH environment variable:
1. Open Start > "Environment Variables"
2. Edit "Path" under User variables
3. Add your Unpackr folder path
4. Restart terminal

**Build Standalone .exe (Advanced):**
```powershell
pip install pyinstaller
python build.py
# Creates dist/unpackr.exe (~20-50 MB)
```

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
[##########----------] 33% | Folders: 10/30 | Videos: 15 | Archives: 8 | PAR2: 5
Speed: 2.3 folders/min | ETA: 0:08:45
> Extracting [34.2MB] Release.part001.rar
```

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