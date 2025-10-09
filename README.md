# Unpackr# Unpackr



Automated video file processor that extracts, validates, and organizes your downloads.Your Digital Declutterer - Automate, Organize, and Streamline Your Downloads



## What It Does## What It Does



This utility automates the tedious process of:Video processing utility that:

1. **Extracting** RAR archives (using 7-Zip)- Extracts RAR archives (7-Zip)

2. **Repairing** damaged files (using PAR2)- Repairs files with PAR2

3. **Validating** video health (using FFmpeg)- Validates video health (FFmpeg)

4. **Moving** good videos to your destination- Organizes downloaded content

5. **Deleting** corrupt files and samples- Cleans up aggressively

6. **Cleaning up** junk files and empty folders- Includes timeout protection to handle edge cases



**Smart Detection:**## Quick Start

- Preserves folders with music, documents, or images

- Removes sample files and junk (NFO, SFV, URL files)```powershell

- Skips folders that only contain non-video content# Install dependencies

pip install -r requirements.txt

**Safety Features:**

- Timeout protection on all operations (won't hang forever)# Run interactive mode

- Loop guards and recursion limitspython unpackr.py

- Input validation and disk space checks

- Comprehensive error logging# Run with arguments

python unpackr.py --source "G:\Downloads" --destination "G:\Videos"

## Installation```



### Step 1: Install Python Dependencies## The Problem



```powershellDownload folders cluttered with:

pip install -r requirements.txt- Nested subfolders

```- PAR2/RAR archives

- NFO/SFV junk files

This installs: tqdm, psutil, colorama- Sample videos

- Corrupt files

### Step 2: Ensure External Tools Available

Manually extracting, validating, and organizing wastes time.

Required:

- **7-Zip** - For RAR extraction ([download](https://www.7-zip.org/))## The Solution



Optional but recommended:Unpackr automates everything:

- **par2cmdline** - For file repair1. Extracts RAR archives

- **ffmpeg** - For video validation2. Repairs damaged files (PAR2)

3. Validates video health (FFmpeg)

The script checks for these on startup and warns if missing.4. Moves good videos to destination

5. Deletes corrupt files

### Step 3 (Optional): Install as Command6. Cleans up junk and empty folders



If you want to run `unpackr` from anywhere (instead of `python unpackr.py`):Smart Detection:

- Preserves music/document folders

**Simple Method (Requires Admin):**- Removes sample files

```powershell- Skips content-only folders

copy unpackr.bat C:\Windows\System32\

```## Project Structure



Now you can run from any directory:```

```powershellunpackr.py              # Run this

cd C:\README.md               # This file

unpackr --source "C:\Downloads" --destination "D:\Videos"requirements.txt        # Dependencies

```bin/                    # Executables

config_files/           # Configuration

**Alternative (No Admin Required):**scripts/                # Utilities

Add `G:\Unpackr` to your PATH environment variable:core/                   # Business logic

1. Open Start > "Environment Variables"utils/                  # Helpers

2. Edit "Path" under User variablestests/                  # Test suites

3. Add `G:\Unpackr`docs/                   # Documentation

4. Restart terminallogs/                   # Runtime logs

archive/                # Historical versions

**Build Standalone .exe (Advanced):**```

```powershell

pip install pyinstallerSee docs/PROJECT_STRUCTURE.md for details.

python build.py

# Creates dist/unpackr.exe (~20-50 MB)## Safety Features

```

Timeout Protection:

## Usage- RAR extraction: 5 minutes

- PAR2 repair: 10 minutes

### Interactive Mode- Video validation: 60 seconds

- Global runtime: 4 hours

Just run without arguments and it will prompt you:

Loop Guards:

```powershell- Max iterations with auto-breaks

python unpackr.py- Recursion limits (10 levels)

```- Stuck detection (5min)



### Command-Line ModeInput Validation:

- Path validation (null bytes, traversal)

Specify source and destination:- State checks (disk space, permissions)

- Error recovery with retries

```powershell

python unpackr.py --source "C:\Downloads" --destination "D:\Videos"Designed to handle errors gracefully and avoid common hanging scenarios.

```

## Quick Reference

Or if installed as command:

```powershell

```powershell# Interactive mode

unpackr --source "C:\Downloads" --destination "D:\Videos"python unpackr.py

```

# Command-line mode

### Custom Configurationpython unpackr.py --source "G:\Downloads" --destination "G:\Videos"



Use a different config file:# Custom config

python unpackr.py --config "custom_config.json"

```powershell```

python unpackr.py --config "my_config.json"

```## Configuration



### Path HandlingEdit config_files/config.json to customize:

- File extensions (video/music/image/docs)

Paths work with or without quotes:- Folder classification thresholds

- Sample size detection

```powershell- Log retention

# With quotes (if spaces in path)

python unpackr.py --source "C:\My Downloads" --destination "D:\My Videos"## Requirements



# Without quotes (if no spaces)Python Dependencies:

python unpackr.py --source C:\Downloads --destination D:\Videos- tqdm>=4.62.0

```- psutil>=5.8.0

- colorama>=0.4.4

## What Happens During Processing

External Tools:

### 1. Pre-Scan Analysis- 7-Zip (required)

```- par2cmdline (optional)

[PRE-SCAN] Analyzing directories...- ffmpeg (optional)

Videos: 12 | Archives: 5 | Junk: 127 | Content Folders: 2

```## Testing

Quickly scans to show what will be processed.

```powershell

### 2. Stage 1: Process Archivespython tests/test_comprehensive.py

- Finds all RAR filespython tests/test_safety.py

- Extracts them (5 min timeout per archive)python tests/test_defensive.py

- Repairs with PAR2 if available (10 min timeout)```



### 3. Stage 2: Find VideosTotal: 80+ tests

- Scans for video files

- Detects sample files (< 50 MB by default)## Install as Command (Optional)

- Identifies content folders (music/docs/images)

To run `unpackr` from anywhere (instead of `python unpackr.py`):

### 4. Stage 3: Validate Videos

- Checks video health with FFmpeg (60 sec timeout)```powershell

- Flags corrupt files for deletion# Copy batch file to PATH (requires admin)

copy unpackr.bat C:\Windows\System32\

### 5. Stage 4: Move Videos

- Moves good videos to destination# Now run from anywhere:

- Preserves folder structure if neededcd C:\

- Skips duplicatesunpackr --source "C:\Downloads" --destination "D:\Videos"

```

### 6. Stage 5: Cleanup

- Deletes junk files (NFO, SFV, URL, etc.)See `INSTALL.md` for other installation options (no admin, PATH setup, PowerShell alias).

- Removes empty folders

- Deletes corrupt videosFor building standalone .exe, see `docs/BUILD.md`.

- Preserves content folders (music/docs)

## Documentation

### Final Summary

```- README.md - This file

Moved: 10 | Deleted: 127 files | Videos: 10 | Folders: 5- INSTALL.md - Install as command guide

```- docs/QUICK_REFERENCE.md - Quick start

- docs/PROJECT_STRUCTURE.md - Organization

## Configuration- docs/BUILD.md - Build standalone .exe



Edit `config_files/config.json` to customize:## Disclaimer



```jsonUse at your own risk. Always back up important data.

{

  "video_extensions": [".mp4", ".avi", ".mkv", ".mov", ...],## License

  "music_extensions": [".mp3", ".flac", ".wav", ...],

  "removable_extensions": [".nfo", ".sfv", ".url", ...],Use freely. No warranties.

  "min_sample_size_mb": 50,

  "max_log_files": 5,---

  "log_folder": "logs"

}A personal utility project for automating video downloads cleanup.

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

## Safety & Timeouts

**Why Timeouts Matter:**
Some archives or videos can hang extraction/validation. Timeouts prevent infinite hangs.

**Configured Timeouts:**
- RAR extraction: 5 minutes per archive
- PAR2 repair: 10 minutes per operation
- Video validation: 60 seconds per file
- Global runtime: 4 hours total

**Additional Safeguards:**
- Loop iteration limits (won't loop forever)
- Recursion depth limits (max 10 subfolder levels)
- Stuck detection (stops if no progress for 5 minutes)

**If Issues Occur:**
- Check logs in `logs/unpackr-YYYYMMDD-HHMMSS.log`
- Safety stops are logged with reason
- You can adjust timeouts in the code if needed

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

## Testing

Run the test suites to verify everything works:

```powershell
python tests/test_comprehensive.py   # 58 tests - core functionality
python tests/test_safety.py          # Safety mechanism tests
python tests/test_defensive.py       # Input validation tests
```

Total: 80+ tests covering all features.

## Project Structure

```
Unpackr/
├── unpackr.py              # Main script (run this)
├── unpackr.bat             # Windows launcher (for command usage)
├── build.py                # Build standalone .exe
├── requirements.txt        # Python dependencies
├── .gitignore              # Git ignore rules
│
├── bin/                    # External executables
│   └── par2.exe
│
├── config_files/           # Configuration
│   └── config.json
│
├── scripts/                # Utility scripts
│   └── movierenamer.py
│
├── core/                   # Business logic modules
│   ├── config.py           # Configuration management
│   ├── logger.py           # Logging system
│   ├── file_handler.py     # File operations
│   ├── archive_processor.py # RAR/PAR2 handling
│   └── video_processor.py  # Video validation
│
├── utils/                  # Helper utilities
│   ├── system_check.py     # Tool validation
│   ├── progress.py         # Progress tracking
│   ├── safety.py           # Timeout protection
│   └── defensive.py        # Input validation
│
├── tests/                  # Test suites
│   ├── test_comprehensive.py
│   ├── test_safety.py
│   └── test_defensive.py
│
├── docs/                   # Additional documentation
│   ├── QUICK_REFERENCE.md
│   ├── PROJECT_STRUCTURE.md
│   └── BUILD.md
│
├── logs/                   # Runtime logs (auto-created)
│   └── unpackr-*.log
│
└── archive/                # Old versions (compressed)
    └── archive_unpackr.7z
```

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
