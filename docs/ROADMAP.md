# Unpackr Development Roadmap

## Current State

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

Tasks are listed in logical dependency order. Each builds on the previous.

### Foundation Layer ✅ COMPLETE

**Better Error Messages** ✅

~~Current errors are cryptic~~

Now shows:
```
ERROR: Failed to extract MyVideo.part01.rar
  Reason: Disk full (need 2500MB, have 500MB)
  Action: Free up space or skip this file
  Location: C:\Downloads\MyVideo\
```

**Status:** COMPLETE
- ✅ Created utils/error_messages.py with format helpers
- ✅ Updated archive_processor.py error messages
- ✅ Updated video_processor.py error messages
- ✅ Updated file_handler.py error messages
- ✅ All core tests passing (250/261)

---

**Config Validation** ✅

~~User edits config.json wrong, gets cryptic error~~

Now shows:
```
ERROR: Invalid config value
  Field: min_sample_size_mb
  Value: "fifty" (str)
  Expected: number (integer)
  Example: 50
  Valid range: 1 to 10000
  Config file: C:\Users\you\.unpackr\config.json
```

**Status:** COMPLETE
- ✅ Enhanced core/config.py with structured errors
- ✅ Shows Field/Value/Expected/Example/Range
- ✅ JSON parse errors show line/column numbers
- ✅ Created tests/test_config_validation.py (7/7 passing)

---

### User Experience Layer 🚧 IN PROGRESS

**Improved Dry-Run Output** ✅

~~Current dry-run logs everything line-by-line~~

Now shows structured summary:
```
DRY RUN SUMMARY
===============

PAR2 VERIFICATION/REPAIR (2 folders, 15 files):
  Process: MyVideo (10 PAR2 files)
  Process: OtherShow (5 PAR2 files)

ARCHIVES (3 to extract, 4.2 GB):
  Extract: MyVideo.part01.rar (1.8 GB)
  Extract: OtherShow.rar (2.1 GB)

VIDEOS (2 to move, 3.9 GB):
  Move: MyVideo.mkv (1.8 GB, unknown, validated)
  Move: episode.mkv (2.1 GB, unknown, validated)

  DELETE SAMPLES (1):
    Delete: sample.mkv - sample/preview file

CLEANUP:
  Delete 15 junk files (3 .nfo, 5 .sfv, 7 .txt)
  Delete 2 empty/junk folders

DISK SPACE:
  Source freed: 4.2 GB (after cleanup)
  Destination used: 3.9 GB

SUMMARY:
  Archives: 3 extract, 0 skip
  Videos: 2 move, 1 delete, 0 skip
  Cleanup: 15 junk files, 2 folders
  Protected: 0 content folders kept
```

**Status:** COMPLETE
- ✅ Created utils/dry_run_summary.py with DryRunPlan class
- ✅ Integrated into unpackr.py main loop
- ✅ Tracks PAR2, archives, videos, cleanup operations
- ✅ Groups by operation type with counts and sizes
- ✅ Shows disk space impact (freed/used)
- ✅ Human-readable size formatting (B, KB, MB, GB)

---

**Progress Bar Improvements**

Current progress shows file-by-file. Better:
```
Processing: Downloads/MyVideo/
  [====================] Extracting archives (3/3)
  [===>                ] Validating videos (1/2)
  [                    ] Moving to destination (0/2)

  Current: Validating episode.mkv (2.1 GB)
```

**Why:** Depends on operation structure being clear. User tracks progress through multi-step process.

**Changes needed:**
- Show stage-level progress (not just file-level)
- Display current file being processed
- Show counts (done/total) per stage
- Keep previous stages visible (context)

---

### Performance Layer

**Simple Environment Detection**

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

**Why:** Core operations must work correctly first. Then optimize timeouts based on hardware.

**Changes needed:**
- Add disk type detection utility
- Run detection once per session
- Cache result per path
- Apply multipliers to base timeouts

---

### Optimization Layer

Only add these if users report specific problems. Core functionality must be rock-solid first.

**Parallel Processing**

Process multiple folders simultaneously (with safety guards).

**Prerequisites:**
- All serial processing must work perfectly
- Error handling must be bulletproof
- Safety invariants must never be violated

**Why we might add it:** Faster on large directories with many folders.

**Why we might not:** More complex, potential race conditions, harder to debug.

**Decision point:** Only if users report speed issues with large collections (hundreds of folders).

---

**Incremental Processing**

Remember what's already been processed, skip on re-run.

**Prerequisites:**
- Full processing must work reliably
- State tracking design must be simple
- Corruption recovery must be clear

**Why we might add it:** Useful for ongoing download folders (run daily, only process new content).

**Why we might not:** State tracking adds complexity, potential for stale data, debugging becomes harder.

**Decision point:** Only if multiple users request it. Current approach (process everything) is simpler.

---

**Custom Hooks**

Let users run custom scripts at key points (before/after extraction, etc.).

**Prerequisites:**
- Core pipeline must be stable
- Hook points must be well-defined
- Error handling for hook failures must exist

**Why we might add it:** Power users can add custom logic without modifying Unpackr.

**Why we might not:** Support burden if hooks break things, most users won't need it.

**Decision point:** Wait for multiple user requests with specific use cases.

---

## What We Won't Add

These features were considered and rejected. They don't help the core mission.

### Web Dashboard
**Reason:** A cleanup script doesn't need a web UI. If you want stats, look at the logs or add a simple summary at the end.

### Interactive Prompts
**Reason:** Breaks batch operation. User should configure thresholds once, then trust the automation.

### Machine Learning / Adaptive Thresholds
**Reason:** Not enough signal. User runs this infrequently. No meaningful adaptation possible. HDD/SSD detection is useful, but learning from "corrections" is over-engineering.

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

---

## Decision Framework

When considering new features, ask in order:

1. **Does it help clean up download folders?**
   - If no: Stop. Reject.
   - If yes: Continue to 2.

2. **Is it simpler than the problem it solves?**
   - If no: Stop. Reject.
   - If yes: Continue to 3.

3. **Can the user accomplish this with existing tools?**
   - If yes: Stop. Document the pattern, don't add feature.
   - If no: Continue to 4.

4. **Does it add significant maintenance burden?**
   - If yes: Stop. Reject unless critical.
   - If no: Continue to 5.

5. **Have multiple users requested it?**
   - If no: Wait. Don't add until proven need.
   - If yes: Add to roadmap in appropriate layer.

---

## Success Metrics

**Good indicators:**
- False positive rate (good video rejected): < 1%
- False negative rate (bad video accepted): < 5%
- User intervention needed: Never (except config)
- Errors are self-explanatory without debug mode

**Bad indicators:**
- Cryptic errors requiring debug mode
- Frequent timeouts on normal operations
- Need to read documentation to understand what happened
- Having to manually clean up after Unpackr runs

---

## Contributing

See feature requests? Want to add something?

**First:** Check the "What We Won't Add" section. If it's there, it's been considered and rejected.

**Then:** Open an issue describing:
- What problem you're solving
- Why existing features don't work
- How you'd use it in real scenarios
- Which layer it belongs in (foundation, UX, performance, optimization)

**Remember:** Unpackr's strength is doing one thing well. Every feature is a liability. Code is expensive. Simplicity is valuable.
