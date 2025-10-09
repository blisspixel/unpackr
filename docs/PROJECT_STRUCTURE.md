# Unpackr - Project Structure

## Root Directory (Minimal)
```
unpackr.py              # Main entry point
unpackr.bat             # Windows launcher (for PATH)
build.py                # Build script for .exe
README.md               # Documentation
requirements.txt        # Dependencies
.gitignore              # Git ignore rules
```

## Organized Subdirectories

### `/bin/`
External executables
```
par2.exe               # PAR2 repair tool
```

### `/config_files/`
Configuration
```
config.json            # App settings
```

### `/scripts/`
Utility scripts
```
movierenamer.py        # Movie renaming utility
```

### `/core/`
Business logic modules (6 files)
```
config.py              # Configuration management
logger.py              # Logging system
file_handler.py        # File operations
archive_processor.py   # RAR/PAR2 handling
video_processor.py     # Video validation
cleanup.py             # Cleanup operations
```

### `/utils/`
Helper utilities (4 files)
```
system_check.py        # Tool validation
progress.py            # Progress tracking
safety.py              # Timeout protection
defensive.py           # Input validation
```

### `/tests/`
Test suites
```
test_comprehensive.py  # Main tests (58 tests)
test_safety.py         # Safety tests
test_defensive.py      # Validation tests
```

### `/docs/`
Documentation
```
QUICK_REFERENCE.md     # Quick start guide
PROJECT_STRUCTURE.md   # This file
BUILD.md               # Installation as command
```

### `/logs/`
Runtime logs
```
unpackr-YYYYMMDD-HHMMSS.log
```

### `/archive/`
Historical versions and backups

## Design Philosophy

**Ultra-Clean Root:** Only 3 files in root - entry point, docs, dependencies.

**Logical Organization:** Everything has a clear home:
- Executables → `bin/`
- Configuration → `config_files/`
- Utilities → `scripts/`
- Source code → `core/` and `utils/`
- Quality assurance → `tests/`
- Documentation → `docs/`
- Runtime data → `logs/`
- History → `archive/`

**Professional Structure:** Follows industry standards (Linux FHS, Python packaging).

**Scalable:** Adding new items is obvious - each has a designated folder.

---

**Total:** 1,500+ lines of code across 11 modules, 80+ tests, 2 docs.
