# Unpackr - Quick Reference

## What It Does

Automated video file processor that:
- Extracts RAR archives
- Repairs files with PAR2
- Validates video health
- Organizes content
- Cleans up aggressively
- Never hangs (timeout protection)

## Quick Start

```powershell
# Install dependencies
pip install -r requirements.txt

# Run interactive mode
python unpackr.py

# Run with arguments
python unpackr.py --source "G:\Downloads" --destination "G:\Videos"
```

## Configuration

Edit `config_files/config.json` to customize:
- File extensions (video, music, image, docs)
- Minimum counts for folder classification
- Sample size threshold (default: 50MB)
- Log retention (default: 5 files)

## Project Structure

```
unpackr.py              # Run this
README.md               # Full documentation
requirements.txt        # Dependencies
├── bin/                # Executables (par2.exe)
├── config_files/       # Configuration
├── scripts/            # Utilities
├── core/               # Business logic (6 modules)
├── utils/              # Helpers (4 modules)
├── tests/              # Test suites
├── docs/               # Documentation
├── logs/               # Runtime logs
└── archive/            # Historical versions
```

## Safety Features

**Timeout Protection:**
- RAR extraction: 5 minutes
- PAR2 repair: 10 minutes
- Video validation: 60 seconds
- Global runtime: 4 hours

**Loop Guards:**
- Max iterations with automatic breaks
- Recursion depth limits (10 levels)
- Stuck detection (5min no progress)

**Input Validation:**
- Path validation (null bytes, traversal)
- State checks (disk space, permissions)
- Error recovery with retries

## Testing

```powershell
# Run test suites
python tests/test_comprehensive.py
python tests/test_safety.py
python tests/test_defensive.py
```

## External Tools Required

- **7-Zip** - RAR extraction
- **par2cmdline** - File repair
- **ffmpeg** - Video validation

System check runs automatically on startup.

## Common Use Cases

### Process Downloads Folder
```powershell
python unpackr.py --source "G:\Downloads" --destination "G:\Videos"
```

### Test on Sample Folder
```powershell
python unpackr.py --source "G:\test" --destination "G:\test_output"
```

### Custom Config
```powershell
python unpackr.py --config "custom_config.json"
```

## Logs

All operations logged to: `logs/unpackr-YYYYMMDD-HHMMSS.log`

Logs include:
- Files processed
- Errors encountered
- Safety interventions
- Performance metrics

---

**For detailed documentation, see README.md in root directory.**
