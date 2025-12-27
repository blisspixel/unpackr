# Ayahuasca Roadmap: The Truth About What Unpackr Needs

## The Ceremony Begins: What Are We Actually Building?

**Core truth:** A tool that cleans up messy download folders.

**Not:** A distributed system. Not a learning platform. Not an observability suite. Not a PhD thesis.

**User journey:**
1. User has folder full of RAR files, PAR2 files, NFO files, videos
2. User runs: `unpackr source dest`
3. Tool extracts archives, validates videos, moves good ones, deletes junk
4. User gets clean folder with working videos

**That's it.** Everything else is masturbation.

---

## What We Have That Actually Matters

### ✅ Core (Already Working)
- `core/archive_processor.py` - Extracts RARs, repairs PAR2
- `core/video_processor.py` - Validates videos aren't corrupt
- `core/file_handler.py` - Moves files, deletes junk
- `unpackr.py` - Main pipeline that ties it together
- **33 passing tests** covering real scenarios

**This is good code.** It works. It solves the problem.

### ✅ Phase 0 That's Worth Keeping
- **`core/safety_invariants.py`** (952 lines)
  - **Why keep:** Prevents catastrophic errors (deleting wrong files, writing outside destination)
  - **Integration effort:** Medium - need to add checks before destructive operations
  - **Value:** High - prevents data loss

- **`docs/FMEA.md`** (31 documented failure modes)
  - **Why keep:** Documents what can go wrong
  - **Integration effort:** Zero - it's documentation
  - **Value:** Medium - helps debugging, prevents repeating mistakes

- **Chaos tests** (`tests/chaos/`)
  - **Why keep:** Tests failure scenarios we don't normally hit
  - **Integration effort:** Zero - runs separately
  - **Value:** Medium - catches edge cases

### ⚠️ Phase 1 That's Questionable

- **`core/adaptive_policy.py`** (850 lines)
  - **What it does:** Learns from user corrections, adapts thresholds, profiles HDD vs SSD
  - **Reality check:** User runs this maybe once a week. Learning requires lots of feedback. Environment changes rarely.
  - **Verdict:** **CUT THE LEARNING, KEEP ENVIRONMENT PROFILING**
  - **Why:** HDD vs SSD detection for timeouts is legitimately useful. Learning from corrections is over-engineering.

- **`core/structured_events.py`** (700 lines)
  - **What it does:** Machine-readable JSON logs instead of string logs
  - **Reality check:** Current string logs work fine. JSON is nice for parsing but who's parsing them?
  - **Verdict:** **SIMPLIFY TO 100 LINES**
  - **Keep:** Simple event tracking (timestamp, type, path, outcome)
  - **Cut:** EventBuilder, EventAnalyzer, all the query infrastructure

- **`core/provenance.py`** (600 lines)
  - **What it does:** Tracks file history with cryptographic hashes
  - **Reality check:** This is for compliance/forensics. User just wants videos extracted.
  - **Verdict:** **CUT ENTIRELY**
  - **Why:** SHA256 hashing every file is expensive. User doesn't care about provenance.

### ❌ Phase 2 That's Completely Off Track

- **`core/telemetry_server.py`** (web dashboard)
  - **Verdict:** **DELETE**
  - **Why:** A cleanup script doesn't need a web UI. If user wants stats, print them to console.

- **`core/user_feedback.py`** (interactive prompts)
  - **Verdict:** **DELETE**
  - **Why:** Batch tool shouldn't ask questions. Breaks unattended operation.

- **`core/wal.py`** (write-ahead log with rollback)
  - **Verdict:** **DELETE**
  - **Why:** Complexity way beyond scope. If operation fails, user re-runs. Logging is enough.

---

## The Sober Truth: What Unpackr Actually Needs

### Immediate (Next 2 Weeks)

**1. Integration, Not Features**

Stop writing new code. Integrate what's useful:

```python
# In core/archive_processor.py
from core.safety_invariants import InvariantEnforcer

class ArchiveProcessor:
    def __init__(self, config):
        self.enforcer = InvariantEnforcer(destination_root, config)

    def _delete_archive_files(self, folder):
        for archive in archives:
            # Check invariants before deleting
            self.enforcer.enforce_delete(archive, extraction_verified=True)
            archive.unlink()
```

**Add safety checks to:**
- File deletion (I2: never delete validated videos)
- File moves (I1: never write outside destination)
- Folder deletion (double-check it's actually empty/removable)

**Time estimate:** 1-2 days
**Lines changed:** ~50-100 lines across existing files
**Value:** Prevents catastrophic user errors

**2. Better Error Messages**

Current errors are cryptic:
```
Error: Failed to extract archive
```

Should be:
```
ERROR: Failed to extract MyVideo.part01.rar
  Reason: Disk full (need 2.5GB, have 500MB)
  Action: Free up space or skip this file
  Archive location: C:\Downloads\MyVideo\
```

**Time estimate:** 1 day
**Lines changed:** ~100 lines (improve logging in error handlers)
**Value:** User actually knows what went wrong

**3. End-to-End Integration Test**

Test the **entire pipeline** with real data:
```python
def test_full_pipeline():
    # Create test folder with:
    # - Multi-part RAR
    # - PAR2 files
    # - Video inside
    # - Junk files

    # Run unpackr
    run_unpackr(source, dest)

    # Verify:
    # - Video extracted
    # - Video validated
    # - Video moved to dest
    # - Junk deleted
    # - Source folder cleaned
```

**Time estimate:** 1 day
**Value:** Confidence the whole thing actually works

### Medium Term (Next Month)

**4. Simple Environment Detection (Keep from Phase 1)**

**Just the basics:**
```python
def detect_disk_type(path: Path) -> str:
    """Quick HDD vs SSD detection via seek patterns."""
    # Simple benchmark: random vs sequential read
    ratio = sequential_speed / random_speed

    if ratio > 5:
        return "HDD"  # Slow seeks
    else:
        return "SSD"  # Fast seeks
```

**Use it for:**
- Extraction timeouts (HDD gets 3x buffer, SSD gets 2x)
- PAR2 timeouts (adjust based on disk speed)

**Time estimate:** 2 days
**Lines added:** ~100 lines (simple profiler)
**Lines integrated:** ~20 lines (use in timeout calculation)
**Value:** Handles slow HDDs without timing out, doesn't waste time on SSDs

**5. Config Validation Helper**

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
```

**Time estimate:** 1 day
**Value:** User fixes config themselves instead of asking for help

### Long Term (When Actually Needed)

**6. Dry-Run Diff View**

Current dry-run just logs everything:
```
[DRY-RUN] Would delete: file1.nfo
[DRY-RUN] Would delete: file2.sfv
[DRY-RUN] Would move: video.mkv -> destination
... 500 more lines ...
```

Better:
```
DRY RUN SUMMARY
===============

ARCHIVES (3 files, 4.2 GB):
  ✓ Extract: MyVideo.part01.rar → MyVideo.mkv (1.8 GB)
  ✓ Extract: OtherShow.rar → episode.mkv (2.1 GB)
  ✗ Skip: Corrupted.rar (PAR2 repair failed)

VIDEOS (2 files, 3.9 GB):
  → Move: MyVideo.mkv (1.8 GB, 1080p, validated)
  → Move: episode.mkv (2.1 GB, 720p, validated)

CLEANUP:
  🗑️  Delete 15 junk files (.nfo, .sfv, .txt)
  🗑️  Delete 2 empty folders
  ✓  Keep: MusicLibrary/ (12 MP3 files)

DISK SPACE:
  Source freed: 4.5 GB
  Destination used: 3.9 GB
```

**Time estimate:** 1 day
**Value:** User sees what will happen in human-readable format

---

## What We Cut and Why

### Deleted Features

| Feature | Lines | Why Cut |
|---------|-------|---------|
| Telemetry dashboard | 600 | Web UI for cleanup script is absurd |
| User feedback system | 500 | Breaks batch operation |
| WAL transactions | 600 | Over-engineered rollback |
| Provenance tracking | 600 | Crypto hashing is expensive |
| Adaptive learning | 400 | Needs too much user feedback |
| Event query system | 300 | Nobody's querying logs programmatically |

**Total cut:** ~3,000 lines of unnecessary code

### Simplified Features

| Feature | Before | After | Why Simplify |
|---------|--------|-------|--------------|
| Structured events | 700 lines | 100 lines | Just need basic tracking |
| Adaptive policy | 850 lines | 150 lines | Keep env detection, cut learning |
| Safety invariants | 950 lines | 950 lines | **Keep as-is** - prevents data loss |

---

## Revised Architecture: Lean and Mean

```
unpackr/
├── unpackr.py              # Main entry (no changes)
├── core/
│   ├── archive_processor.py   # +safety checks (50 lines)
│   ├── video_processor.py     # +safety checks (30 lines)
│   ├── file_handler.py        # +safety checks (40 lines)
│   │
│   ├── safety_invariants.py   # Keep (950 lines) - prevents data loss
│   ├── environment.py          # NEW (150 lines) - simple HDD/SSD detection
│   └── simple_events.py        # NEW (100 lines) - basic event tracking
│
├── tests/
│   ├── test_*.py               # Keep existing (1500 lines)
│   ├── test_integration.py     # NEW (200 lines) - full pipeline test
│   └── chaos/                  # Keep (1300 lines) - edge case testing
│
└── docs/
    ├── README.md               # Update with simpler feature list
    ├── FMEA.md                 # Keep - documents failure modes
    └── INTEGRATION_GUIDE.md    # NEW - how to use safety invariants
```

**Total production code:** ~5,000 lines (down from 8,000)
**Total test code:** ~3,000 lines
**Documentation:** ~3,000 lines

---

## Implementation Plan: Do Less, Do It Better

### Week 1: Integration
- [ ] Add safety invariants to archive_processor
- [ ] Add safety invariants to file_handler
- [ ] Add safety invariants to video_processor
- [ ] Write integration test for full pipeline
- [ ] Fix any bugs found during integration

### Week 2: Polish
- [ ] Improve error messages (show context, suggest fixes)
- [ ] Add simple environment detection (HDD vs SSD)
- [ ] Use environment detection for timeout calculation
- [ ] Update README to reflect actual features

### Week 3: Testing
- [ ] Run chaos tests on integrated code
- [ ] Test on real download folders (your own data)
- [ ] Fix edge cases
- [ ] Update FMEA with newly discovered failure modes

### Week 4: Ship It
- [ ] Version bump to 2.0
- [ ] Tag release
- [ ] Update documentation
- [ ] Delete unused Phase 2 code
- [ ] Archive DEEP_ANALYSIS.md as "ideas we didn't need"

---

## The Ceremony Ends: What Did We Learn?

### Truth #1: Solve the Actual Problem
User has messy folder → wants clean videos.

Everything else is distraction.

### Truth #2: Complexity is a Liability
Every 100 lines of code is:
- More bugs
- More maintenance
- More cognitive load
- Less reliability

Delete ruthlessly.

### Truth #3: Safety > Features
Would you rather:
- A) Tool with 50 features that occasionally deletes wrong files
- B) Tool with 5 features that never loses data

Obviously B.

### Truth #4: Test What Matters
Don't test framework code. Test:
- Does it extract archives?
- Does it validate videos?
- Does it clean up correctly?
- Does it handle failures gracefully?

Integration tests > unit tests.

### Truth #5: Users Don't Care About Your Architecture
User doesn't care if you use:
- WAL transactions
- Event sourcing
- Provenance tracking
- Adaptive learning

User cares:
- Did my videos extract?
- Are they in the destination?
- Did it delete junk?
- Did it preserve my music folder?

---

## Final Roadmap: What Actually Ships

### Version 2.0 (2 weeks)
✅ Safety invariants integrated
✅ Better error messages
✅ End-to-end integration test
✅ Simple environment detection (HDD/SSD)
✅ Chaos tests passing

### Version 2.1 (1 month)
✅ Config validation helper
✅ Dry-run diff view
✅ Updated documentation

### Version 2.2 (When needed)
- Performance profiling (if slow)
- Additional safety checks (if users report issues)
- More file formats (if requested)

**No web dashboards. No learning. No transactions. No telemetry.**

Just a **really solid tool** that does one thing well: clean up download folders.

---

## Deleted Files Manifest

```bash
# Delete Phase 2 overengineering
rm core/telemetry_server.py          # 600 lines
rm core/user_feedback.py             # 500 lines
rm core/wal.py                       # 600 lines
rm core/provenance.py                # 600 lines

rm tests/test_user_feedback.py       # 300 lines
rm tests/test_wal.py                 # 400 lines
rm tests/test_provenance.py          # 450 lines

# Simplify Phase 1
# Manually extract useful 150 lines from adaptive_policy.py → environment.py
# Manually extract useful 100 lines from structured_events.py → simple_events.py
# Then delete originals

# Archive but don't delete (for reference)
mv docs/DEEP_ANALYSIS.md docs/archive/DEEP_ANALYSIS.md
mv docs/PHASE_0_IMPLEMENTATION.md docs/archive/
mv docs/PHASE_1_IMPLEMENTATION.md docs/archive/
```

**Total deleted:** ~3,800 lines of over-engineered code

---

## Success Metrics: What Actually Matters

### Before (Current State)
- ✅ 94 tests passing
- ⚠️ 8,000 lines production code
- ❌ No integration tests
- ⚠️ Safety checks not enforced
- ❌ Tons of unused features

### After (Version 2.0)
- ✅ 100+ tests passing (added integration)
- ✅ 5,000 lines production code (-37%)
- ✅ Full pipeline integration test
- ✅ Safety checks enforced everywhere
- ✅ Only features that solve real problems

### User Experience
**Before:**
- User: "It deleted my music folder"
- Us: "Did you configure min_music_files correctly?"
- User: "What's that?"

**After:**
- User: "It deleted my music folder"
- System: "SAFETY CHECK: Prevented deletion of /Music (12 files > threshold)"
- User: "Oh, it actually protected it. Cool."

---

## Conclusion: Do Less, Do It Right

We got carried away with the PhD-level analysis. We designed systems for:
- Machine learning (overkill)
- Telemetry (unnecessary)
- Transactions (over-engineered)
- Provenance (out of scope)

**What user actually needs:**
1. Extract archives ✅ (already works)
2. Validate videos ✅ (already works)
3. Clean up junk ✅ (already works)
4. Don't delete wrong stuff ⚠️ (needs safety checks)
5. Clear error messages ⚠️ (needs improvement)

**Ship Version 2.0 in 2 weeks:**
- Integrate safety invariants
- Improve error messages
- Delete unnecessary code
- Test the whole pipeline

Then **stop coding** and let users report real problems.

---

*The ceremony is complete. The truth is clear. Let's build the tool users need, not the system architects admire.*

**Next commit:** "feat: integrate safety invariants, delete over-engineered Phase 2"
