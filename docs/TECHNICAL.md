# Technical Details

Internal architecture and implementation details for developers.

## Architecture

```
unpackr/
├── unpackr.py              # Main entry point, UI, orchestration
├── core/
│   ├── config.py           # Configuration loading and validation
│   ├── archive_processor.py # PAR2 repair, RAR/7z extraction
│   ├── file_handler.py     # File operations (move, delete, sanitize)
│   └── video_processor.py  # Video health validation
├── utils/
│   ├── safety.py           # Timeouts, loop guards, resource limits
│   ├── defensive.py        # Input validation, error recovery
│   └── system_check.py     # Tool detection
└── tests/                  # 240+ tests
```

## Processing Pipeline

### Phase 1: Pre-Scan

Classifies all folders in source directory:
- **Junk folders** - Empty or only junk files, deleted immediately
- **Content folders** - 10+ music/image/document files, preserved
- **Video folders** - Everything else, queued for processing

Folders sorted by modification time (oldest first) so ongoing downloads aren't touched.

### Phase 2: Process Each Folder

For each video folder:

1. **PAR2 Repair** (if PAR2 files present)
   - Verify archive integrity
   - Repair if needed
   - Delete corrupted archives if repair fails

2. **Archive Extraction**
   - Validate archive paths (security check)
   - Check disk space (3x archive size)
   - Extract only `.part001` files (7-Zip handles the rest)
   - Dynamic timeout based on file size

3. **Video Validation**
   - Size check (reject < 1MB)
   - Metadata extraction (duration, bitrate)
   - Truncation detection (reject if < 70% expected size)
   - Full decode test (verify all frames readable)
   - Corruption keyword detection

4. **Cleanup**
   - Delete junk files
   - Move valid videos to destination
   - Delete corrupt videos
   - Remove empty folders

### Phase 3: Multi-Pass Cleanup

Re-attempt locked folders:
- 3 passes with exponential backoff
- PowerShell fallback for stubborn deletions
- Report still-locked folders at end

## Video Validation

The health check catches partially extracted videos with valid headers but corrupt data:

```python
1. Size check        - Reject files < 1MB
2. Metadata          - Extract duration/bitrate via ffprobe
3. Duration check    - Reject < 10 seconds or no duration
4. Truncation        - Reject if actual size < 70% of expected
5. Decode test       - Decode entire video, check for errors
6. Keywords          - Detect "corrupt", "truncated", "moov atom not found"
```

## PAR2 Processing

Checks failure keywords BEFORE success keywords:
- "repair failed"
- "repair impossible"
- "cannot repair"
- "insufficient"

This prevents false positives where corrupted archives were incorrectly marked OK.

## Timeouts

Dynamic based on file size:

| Operation | Calculation | Min | Max |
|-----------|-------------|-----|-----|
| RAR extraction | size / 10MB/s + 50% buffer | 5 min | 2 hours |
| PAR2 repair | size / 5MB/s + 100% buffer | 10 min | 3 hours |
| Video validation | fixed | 60 sec | 60 sec |
| Global runtime | fixed | - | 4 hours |

## Thread Safety

- Progress updates use locks
- Statistics tracking is atomic
- Spinner runs in background thread
- All shared state protected

## Cancellation

Ctrl+C triggers graceful shutdown:

1. Signal handler sets `cancellation_requested` flag
2. Active subprocess (7z/par2/ffmpeg) is terminated
3. Main loop exits at next checkpoint (between folders)
4. Summary shows "cancelled" status with partial stats
5. Second Ctrl+C forces immediate exit

Checkpoints exist before each folder, loose video, and junk folder deletion.

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Quick run
python -m pytest tests/ -q
```

245 tests covering:
- Video validation edge cases
- PAR2 error detection
- Safety limits and timeouts
- Input validation and sanitization
- Path handling
- Configuration loading
- File operations
