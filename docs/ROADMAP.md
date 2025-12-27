# Unpackr Development Roadmap

## Current State (v2.0)

**Core functionality works:**
- Extracts multi-part RAR and 7z archives
- Repairs files with PAR2
- Validates video health (detects corruption, truncation)
- Moves validated videos to destination
- Cleans up junk files and empty folders
- Protects content folders (music, images, documents)

**Test Coverage:**
- 243+ passing tests
- End-to-end integration tests
- Chaos testing for edge cases
- FMEA documentation of 31 failure modes

**Safety Features:**
- Safety invariants prevent data loss
- Never write outside destination
- Never delete validated videos
- Never delete content folders beyond thresholds
- Fail-closed validation (reject when uncertain)

## What's Next

### Immediate Focus (v2.1)

**1. Better Error Messages**

Current errors are cryptic:
```
Error: Failed to extract archive
```

Should be:
```
ERROR: Failed to extract MyVideo.part01.rar
  Reason: Disk full (need 2.5GB, have 500MB)
  Action: Free up space or skip this file
  Location: C:\Downloads\MyVideo\
```

**Why:** User actually knows what went wrong and how to fix it.

**2. Improved Dry-Run Output**

Current dry-run logs everything line-by-line. Better format:
```
DRY RUN SUMMARY
===============

ARCHIVES (3 files, 4.2 GB):
  Extract: MyVideo.part01.rar -> MyVideo.mkv (1.8 GB)
  Extract: OtherShow.rar -> episode.mkv (2.1 GB)
  Skip: Corrupted.rar (PAR2 repair failed)

VIDEOS (2 files, 3.9 GB):
  Move: MyVideo.mkv (1.8 GB, 1080p, validated)
  Move: episode.mkv (2.1 GB, 720p, validated)

CLEANUP:
  Delete 15 junk files (.nfo, .sfv, .txt)
  Delete 2 empty folders
  Keep: MusicLibrary/ (12 MP3 files)

DISK SPACE:
  Source freed: 4.5 GB
  Destination used: 3.9 GB
```

**Why:** User sees what will happen in human-readable format.

**3. Config Validation**

User edits config.json wrong, gets cryptic error:
```
Error: 'min_sample_size_mb'
```

Should be:
```
ERROR: Invalid config value
  Field: min_sample_size_mb
  Value: "fifty" (string)
  Expected: number (integer)
  Example: 50
  Config file: C:\Users\you\.unpackr\config.json
```

**Why:** User fixes config themselves instead of asking for help.

### Medium Term (v2.2)

**4. Simple Environment Detection**

Detect HDD vs SSD for better timeout calculations:
```python
def detect_disk_type(path: Path) -> str:
    """Quick HDD vs SSD detection via seek patterns."""
    ratio = sequential_speed / random_speed
    if ratio > 5:
        return "HDD"  # Slow seeks, needs longer timeouts
    else:
        return "SSD"  # Fast seeks, standard timeouts
```

**Use it for:**
- Extraction timeouts (HDD gets 3x buffer, SSD gets 2x)
- PAR2 timeouts (adjust based on disk speed)

**Why:** Handles slow HDDs without timing out, doesn't waste time on SSDs.

**5. Progress Bar Improvements**

Current progress shows file-by-file. Better:
```
Processing: Downloads/MyVideo/
  [====================] Extracting archives (3/3)
  [===>                ] Validating videos (1/2)
  [                    ] Moving to destination (0/2)

  Current: Validating episode.mkv (2.1 GB, 45s elapsed)
```

**Why:** User knows what's happening and how long it might take.

### Long Term (When Needed)

**6. Parallel Processing**

Currently processes folders sequentially. Could process multiple folders in parallel (with safety guards).

**Why:** Faster on large directories with many folders.
**Risk:** More complex, needs careful testing to avoid race conditions.
**Decision:** Only add if users report speed issues with large collections.

**7. Incremental Processing**

Remember what's already been processed, skip on re-run.

**Why:** Useful for ongoing download folders (run daily, only process new stuff).
**Risk:** State tracking adds complexity, potential for stale data.
**Decision:** Only add if users request it. Current approach (process everything) is simpler.

**8. Custom Hooks**

Let users run custom scripts at key points (before/after extraction, etc.).

**Why:** Power users can add custom logic without modifying Unpackr.
**Risk:** Support burden if hooks break things.
**Decision:** Wait for multiple user requests. Most users won't need it.

## What We Won't Add

These features were considered and rejected:

### Web Dashboard
**Reason:** A cleanup script doesn't need a web UI. If you want stats, look at the logs or add a simple summary at the end.

### Interactive Prompts
**Reason:** Breaks batch operation. User should configure thresholds once, then trust the automation.

### Machine Learning / Adaptive Thresholds
**Reason:** Not enough signal. User runs this weekly at most. No meaningful adaptation possible. HDD/SSD detection is useful, but learning from "corrections" is over-engineering.

### Telemetry Server
**Reason:** Local tool should keep data local. Logs are enough.

### Write-Ahead Logging (WAL)
**Reason:** Complexity way beyond scope. If operation fails, user re-runs. Logging is enough for debugging.

### Provenance Tracking
**Reason:** SHA256 hashing every file is expensive. User doesn't care about cryptographic file history for a cleanup script.

### Cloud Integration
**Reason:** Out of scope. Unpackr is for local post-processing. Use other tools for cloud storage.

### Media Library Integration (Plex, Jellyfin, etc.)
**Reason:** Out of scope. Unpackr delivers clean videos. Other tools handle library management.

## Decision Framework

When considering new features, ask:

1. **Does it help clean up download folders?**
   - If no: Reject
   - If yes: Continue

2. **Is it simpler than the problem it solves?**
   - If no: Reject
   - If yes: Continue

3. **Can the user accomplish this with existing tools?**
   - If yes: Document the pattern, don't add feature
   - If no: Consider adding

4. **Does it add significant maintenance burden?**
   - If yes: Reject unless critical
   - If no: Consider adding

5. **Have multiple users requested it?**
   - If no: Wait for more requests
   - If yes: Prioritize

## Success Metrics

**Good indicators:**
- Time from download complete to validated video: < 5 minutes
- False positive rate (good video rejected): < 1%
- False negative rate (bad video accepted): < 5%
- User intervention needed: Never (except config)

**Bad indicators:**
- Cryptic errors requiring debug mode
- Frequent timeouts on normal operations
- Need to read documentation to understand what happened
- Having to manually clean up after Unpackr runs

## Version History

### v2.0 (Current)
- Integrated safety invariants into core processors
- Added comprehensive test suite (243+ tests)
- Removed over-engineered features (WAL, telemetry, provenance)
- Simplified architecture to focus on core mission

### v1.x (Previous)
- Initial release with core functionality
- Archive extraction, PAR2 repair, video validation
- Basic cleanup and folder management

## Contributing

See feature requests? Want to add something?

**First:** Check the "What We Won't Add" section. If it's there, it's been considered and rejected.

**Then:** Open an issue describing:
- What problem you're solving
- Why existing features don't work
- How you'd use it in real scenarios

**Remember:** Unpackr's strength is doing one thing well. Every feature is a liability. Code is expensive. Simplicity is valuable.
