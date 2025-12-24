# UX Design Guidelines - Unpackr

This document explains the expected user experience and critical implementation details to prevent regressions.

## Overview

Unpackr uses a clean, modern CLI interface with:
- Single-line progress updates during pre-scan
- Visual countdown before processing
- Full-screen dashboard during processing with live spinner

## Critical UX Requirements

### 1. Pre-Scan Progress (MUST use single-line updates)

**Expected behavior:**
```
[PRE-SCAN] Analyzing 1/354 folders...
[PRE-SCAN] Analyzing 2/354 folders...
[PRE-SCAN] Analyzing 3/354 folders...
```

All updates appear on **THE SAME LINE** using carriage return (`\r`).

**Implementation:**
```python
for i, folder in enumerate(folders, 1):
    sys.stdout.write(f"\r[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
    sys.stdout.flush()
```

**NEVER do this (terminal spam):**
```python
# BAD - Creates hundreds of lines
for i, folder in enumerate(folders, 1):
    print(f"[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
```

**Why `\r` works:**
- `\r` (carriage return) moves cursor to start of line
- Next write overwrites the previous text
- Creates smooth single-line updates
- Works on Windows with UTF-8 encoding configured

**File location:** [unpackr.py:277-280](../unpackr.py#L277-L280)

### 2. Countdown (MUST show decreasing numbers)

**Expected behavior:**
```
Starting in 10 seconds... (Press Ctrl+C to cancel)
Starting in 9 seconds... (Press Ctrl+C to cancel)
Starting in 8 seconds... (Press Ctrl+C to cancel)
...
```

All updates appear on **THE SAME LINE** using carriage return.

**Implementation:**
```python
for i in range(seconds, 0, -1):
    sys.stdout.write(f"\r{Fore.GREEN}Starting in {i} seconds... "
                   f"(Press Ctrl+C to cancel) {Style.RESET_ALL}")
    sys.stdout.flush()
    time.sleep(1)
sys.stdout.write("\r" + " " * 60 + "\r")  # Clear the line
```

**NEVER do this (appears hung):**
```python
# BAD - Shows static message, user thinks it's frozen
print(f"Starting in {seconds} seconds... (Press Ctrl+C to cancel)")
time.sleep(seconds)
```

**File location:** [unpackr.py:1290-1297](../unpackr.py#L1290-L1297)

### 3. Dashboard (MUST clear screen on first update)

**Expected behavior:**
After countdown completes, screen clears and dashboard appears immediately:

```
  _   _ _ __  _ __   __ _  ___| | ___ __
 | | | | '_ \| '_ \ / _` |/ __| |/ / '__|
 | |_| | | | | |_) | (_| | (__|   <| |
  \__,_|_| |_| .__/ \__,_|\___|_|\_\_|
             |_|

  [████████████████░░░░░░░░░░░░░░░░░░░░] 45% │ 160/354
  found: 1200  extracted: 45  repaired: 12  processed: 158
  speed:  12.5 folders/min  time left: 0:15:32  saved: 5.3 hrs

  > [FolderName] Validate 3/15: video_file.mp4
  ⠹ working
```

**Implementation details:**

1. **First update MUST clear screen:**
```python
if self.first_progress_update:
    self.first_progress_update = False
    sys.stdout.write('\033[2J\033[H')  # Clear and home
```

2. **First update MUST happen immediately in run loop:**
```python
for i, folder in enumerate(video_folders, 1):
    # Initialize dashboard on first folder
    if i == 1:
        self._update_progress(0, total, f"Initializing... {total} folders queued")
```

**Why this matters:**
- Without immediate first update, user sees countdown finish → blank → confusion
- Dashboard must appear within 1 second of countdown completion
- Screen clear removes all previous output (pre-scan, countdown, etc.)

**File locations:**
- Dashboard display: [unpackr.py:766-820](../unpackr.py#L766-L820)
- First update trigger: [unpackr.py:965-967](../unpackr.py#L965-L967)

### 4. UTF-8 Encoding (MUST configure at startup)

**Expected behavior:**
Unicode characters render without crashes:
- Progress bars: `████████████████████░░░░`
- Spinners: `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`
- Separators: `│`

**Implementation:**
```python
def main():
    # Configure UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass  # Fallback for older Python versions

    init()  # Initialize colorama
```

**Why this matters:**
- Windows console defaults to cp1252 encoding
- Unicode characters crash with `UnicodeEncodeError: 'charmap' codec can't encode`
- MUST configure encoding BEFORE any Unicode output

**File location:** [unpackr.py:1305-1311](../unpackr.py#L1305-L1311)

## Testing UX Changes

When modifying UX code, test the ACTUAL user experience:

### Manual Testing Checklist

1. **Pre-scan display:**
   ```bash
   python unpackr.py --source "folder_with_50+_subfolders" --destination "test_dest"
   ```
   - Watch for single-line updates (no spam)
   - Count how many `[PRE-SCAN]` lines appear (should be 1, not 50+)

2. **Countdown display:**
   - Watch for numbers counting down: 10...9...8...7...
   - Verify it's the SAME LINE updating (not 10 separate lines)
   - Verify line clears after countdown completes

3. **Dashboard appearance:**
   - After countdown, screen should clear immediately
   - Dashboard with ASCII art header should appear
   - Spinner should start on bottom line
   - No "black screen" or delay

4. **Unicode rendering:**
   - Progress bar blocks render: `████░░░`
   - Spinner animates: `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`
   - No `UnicodeEncodeError` crashes

### Automated Test Coverage

Integration tests validate UX behavior:

```python
def test_prescan_no_terminal_spam(runner):
    """Verify pre-scan doesn't spam hundreds of lines."""
    # Run unpackr with 50 folders
    # Count [PRE-SCAN] lines in output
    # Assert: prescan_lines <= 5 (not 50+)
```

**File location:** [tests/test_integration_real_usage.py:59-112](../tests/test_integration_real_usage.py#L59-L112)

## Common UX Bugs (and How to Avoid Them)

### Bug #1: Pre-Scan Terminal Spam

**Symptom:** 486 lines of `[PRE-SCAN]` output instead of 1 updating line

**Root cause:** Using `print()` instead of `sys.stdout.write("\r...")`

**Fix:** Use carriage return for single-line updates (see Section 1 above)

**Test that would have caught it:** `test_prescan_no_terminal_spam`

### Bug #2: Countdown Appears Hung

**Symptom:** Static message "Starting in 10 seconds..." with no visible countdown

**Root cause:** Printing once then sleeping, instead of updating countdown numbers

**Fix:** Loop with decreasing numbers using `\r` updates (see Section 2 above)

**Test that would have caught it:** `test_countdown_shows_visual_feedback`

### Bug #3: Dashboard Doesn't Appear

**Symptom:** Countdown finishes → nothing happens → user thinks it's frozen

**Root cause:** No guaranteed first call to `_update_progress()` to trigger screen clear

**Fix:** Call `_update_progress(0, total, "Initializing...")` at start of run loop

**Test that would have caught it:** End-to-end workflow test (TODO)

### Bug #4: Unicode Encoding Crashes

**Symptom:** `UnicodeEncodeError: 'charmap' codec can't encode character`

**Root cause:** Windows console defaults to cp1252, not UTF-8

**Fix:** Configure UTF-8 at start of `main()` (see Section 4 above)

**Test that would have caught it:** `test_windows_console_encoding`

## Design Philosophy

### Clean Modern CLI

- Minimal output (only essential information)
- Single-line updates where possible (pre-scan, countdown)
- Full dashboard when lots of info needed (processing)
- No decorative separators (`===`, `---`)
- Color with purpose (Green=success, Red=error, Yellow=warning)

### User Perception

- **Responsive:** Visual feedback within 1 second of any change
- **Informative:** Show what's happening, not just "please wait"
- **Honest:** Show real progress, not fake spinners on stuck operations
- **Predictable:** Same UX pattern across all operations

### Implementation Principles

1. **Test visual output, not just return values**
   - Integration tests must check terminal rendering
   - Count lines of output, not just success/failure

2. **`\r` for single-line updates**
   - Pre-scan, countdown, status messages
   - NEVER use `print()` in loops

3. **Screen clear for dashboard transitions**
   - Use `\033[2J\033[H` to clear and home
   - Happens on first progress update

4. **UTF-8 encoding FIRST**
   - Configure in `main()` before any output
   - Required for Unicode characters on Windows

## Troubleshooting Guide

### "Pre-scan is spamming my terminal"

**Check:** [unpackr.py:277-280](../unpackr.py#L277-L280)

Should use:
```python
sys.stdout.write(f"\r[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
sys.stdout.flush()
```

NOT:
```python
print(f"[PRE-SCAN] Analyzing {i}/{len(folders)} folders...")
```

### "Countdown looks frozen"

**Check:** [unpackr.py:1290-1297](../unpackr.py#L1290-L1297)

Should have loop with decreasing numbers:
```python
for i in range(seconds, 0, -1):
    sys.stdout.write(f"\rStarting in {i} seconds...")
    sys.stdout.flush()
    time.sleep(1)
```

### "Dashboard never appears after countdown"

**Check:** [unpackr.py:965-967](../unpackr.py#L965-L967)

Should call `_update_progress()` at start of run loop:
```python
if i == 1:
    self._update_progress(0, total, f"Initializing... {total} folders queued")
```

### "UnicodeEncodeError on Windows"

**Check:** [unpackr.py:1305-1311](../unpackr.py#L1305-L1311)

Should configure UTF-8 at start of `main()`:
```python
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
```

## Version History

### v1.2.x - UX Restoration (2024-12-24)

**Fixed:**
- Pre-scan single-line updates restored (was spamming terminal)
- Countdown visual feedback restored (was appearing frozen)
- Dashboard immediate display restored (was delayed/missing)
- UTF-8 encoding configuration added (was crashing on Unicode)

**Commits:**
- Restore clean UX from commit 07fc08b
- Add UTF-8 encoding configuration
- Add guaranteed first progress update

**Tests added:**
- `test_prescan_no_terminal_spam` - Prevents terminal spam regression
- `test_countdown_shows_visual_feedback` - Prevents frozen countdown regression
- `test_windows_console_encoding` - Prevents Unicode crash regression

---

**Last updated:** 2024-12-24

**Maintainer note:** If you modify UX code, test it VISUALLY in actual terminal, not just with automated tests. The tests validate output format, but you need to see the actual user experience to catch display issues.
