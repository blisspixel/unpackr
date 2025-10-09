# Unpackr

Your Digital Declutterer - Automate, Organize, and Streamline Your Downloads

## What It Does

Video processing utility that automates the tedious process of:

1. **Extracting** RAR archives (using 7-Zip)
2. **Repairing** damaged files (using PAR2)
3. **Validating** video health (using FFmpeg)
4. **Moving** good videos to your destination
5. **Deleting** corrupt files and samples
6. **Cleaning up** junk files and empty folders

**Smart Detection:**
- Preserves folders with music, documents, or images
- Removes sample files and junk (NFO, SFV, URL files)
- Skips folders that only contain non-video content

**Safety Features:**
- Timeout protection on all operations (won't hang forever)
- Loop guards and recursion limits
- Input validation and disk space checks
- Comprehensive error logging

## Quick Start

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

### Step 2: Ensure External Tools Available

Required:
- **7-Zip** - For RAR extraction ([download](https://www.7-zip.org/))

Optional but recommended:
- **par2cmdline** - For file repair
- **ffmpeg** - For video validation

The script checks for these on startup and warns if missing.

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
python unpackr.py --source "C:\Downloads" --destination "D:\Videos"
```

Or if installed as command:
```powershell
unpackr --source "C:\Downloads" --destination "D:\Videos"
```

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
[PRE-SCAN] Analyzing directories...
Videos: 12 | Archives: 5 | Junk: 127 | Content Folders: 2
```
Quickly scans to show what will be processed.

### 2. Stage 1: Process Archives
- Finds all RAR files
- Extracts them (5 min timeout per archive)
- Repairs with PAR2 if available (10 min timeout)

### 3. Stage 2: Find Videos
- Scans for video files
- Detects sample files (< 50 MB by default)
- Identifies content folders (music/docs/images)

### 4. Stage 3: Validate Videos
- Checks video health with FFmpeg (60 sec timeout)
- Flags corrupt files for deletion

### 5. Stage 4: Move Videos
- Moves good videos to destination
- Preserves folder structure if needed
- Skips duplicates

### 6. Stage 5: Cleanup
- Deletes junk files (NFO, SFV, URL, etc.)
- Removes empty folders
- Deletes corrupt videos
- Preserves content folders (music/docs)

### Final Summary
```
Moved: 10 | Deleted: 127 files | Videos: 10 | Folders: 5
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