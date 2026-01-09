# Requirements: Graceful Cancellation

## Problem

Ctrl+C during processing:
- Waits for current subprocess (can be minutes for large archives)
- May leave orphaned 7z/par2/ffmpeg processes
- May leave partially extracted files

## User Stories

**US-1**: When I press Ctrl+C, the app exits within 5 seconds.

**US-2**: When I cancel, running 7z/par2/ffmpeg processes are terminated.

**US-3**: When I cancel during extraction, partial files are cleaned up.

**US-4**: When I cancel, I see what was completed before stopping.

## Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-1 | Ctrl+C exits within 5 seconds |
| AC-2 | Child processes terminated on cancel |
| AC-3 | Partial extractions deleted |
| AC-4 | Summary shows "Cancelled after X folders" |
| AC-5 | Log records cancellation |

## Approach

1. Signal handler sets `cancellation_requested` flag
2. Check flag between folders (safe checkpoint)
3. Track spawned subprocesses, terminate on cancel
4. Delete files created since last checkpoint

## Out of Scope

- Pause/resume
- Save state for continuation
- Linux/Mac support
