# Safety Contract

Unpackr removes files during cleanup. This document defines what can be removed, what is protected, and which safeguards are enforced.

## Removal Is Reversible By Default

With the default `delete_mode: "quarantine"`, nothing a live run removes is destroyed right away. Removed files and folders are moved to `<source>/.unpackr-quarantine/<run_id>/`, keeping their relative paths (a rename on the same filesystem, so it is instant). Every removal and every video moved to the destination is recorded in `<source>/.unpackr-runs/<run_id>.jsonl`.

- `unpackr runs --source <dir>` lists recent runs with their actions and quarantined size.
- `unpackr restore <run_id> --source <dir>` (or `restore latest`) puts quarantined files back and moves videos back from the destination when they are unchanged (size and modification time). `--path '<glob>'` restores part of a run; `--dry-run` previews.
- Quarantined runs older than `quarantine_retention_days` (default 14) are purged at the start of the next live run. The purge only touches direct children of `.unpackr-quarantine`, never follows symlinks, and never runs during `--dry-run`.
- `delete_mode: "trash"` sends removals to the desktop trash (freedesktop Trash on Linux, `~/.Trash` on macOS, the Recycle Bin on Windows); restore those from the trash.
- `delete_mode: "permanent"` keeps the previous behavior: removals are deleted immediately and cannot be restored by Unpackr.
- `.unpackr-quarantine` and `.unpackr-runs` are never scanned, processed or cleaned up as content.
- `unpackr-doctor --source <dir>` reports the quarantine size and warns above `quarantine_warn_mb`.

## Operating Guidance

Before live runs:
- Back up important data before running
- Test on non-critical folders first
- Use `--dry-run` to preview changes
- Review logs after processing

No automated deletion workflow can eliminate all risk.

## What Gets Deleted

| Item | Configurable? |
|------|---------------|
| Junk files (NFO, SFV, URL, DIZ, TXT, M3U) | Yes: `removable_extensions` |
| Sample videos (< 50MB) | Yes: `min_sample_size_mb` |
| Previews and samples shorter than 10 seconds | Yes: `min_video_duration_seconds` |
| Corrupt/truncated videos | No: always deleted |
| Archive sets after a successful extraction | No: always deleted |
| Archive sets PAR2 cannot repair, or that fail with CRC/data errors | No: always deleted |
| Empty folders | No: always deleted |
| Processed folders after extraction | No: always deleted |

## What Never Gets Deleted

| Item | Configurable? |
|------|---------------|
| Videos that pass validation | Moved to destination |
| Music folders (10+ files) | Yes: `min_music_files` |
| Image folders (10+ files, 10MB+) | Yes: `min_image_files` |
| Document folders (10+ files) | Yes: `min_documents` |
| Folders with unrecognized files | Always preserved |
| Incomplete, unreadable, password-protected or interrupted archive sets | Kept for retry; the run exits `3` |
| Anything in destination directory | Never touched |

Details and resume semantics: [PRESERVATION.md](PRESERVATION.md).

## Safety Mechanisms

### Path Containment
- All extractions happen in the source directory
- Writes are constrained to expected source/destination targets
- Archive contents validated before extraction (no path traversal)
- Windows-style `\` members, drive letters, UNC paths, and `..` segments are rejected on every OS
- Symlinks / junctions / reparse points are refused for destructive cleanup

### Fail-Closed Validation
- When uncertain, reject rather than proceed
- Archive volumes are grouped into sets; a set with a missing volume is not extracted, and its remaining volumes and folder are kept
- An archive 7-Zip cannot list is not extracted and is kept (reported as `archive_unlistable`, not as a security block)
- Only a set that extracted successfully has its volumes removed
- Video validation requires ffmpeg for full reliability

### Race Condition Prevention
- Folder state re-verified immediately before deletion
- Double-check pattern prevents unsafe deletions

### Resource Limits
- Dynamic timeouts based on file size
- Recursion depth limits (default `20` levels; `max_subfolder_depth`)
- Memory-bounded failure tracking
- Global runtime limit (default `48` hours; `max_runtime_hours`)

### Disk Space Protection
- Checks 3x archive size available before extraction
- Partial extractions cleaned up on failure

### Process Safety
- Subprocesses killed on timeout
- Thread-safe progress and stats
- Graceful shutdown on `Ctrl+C`

## Dry-Run Mode

Preview all operations without making changes:

```bash
unpackr --source "G:\Downloads" --destination "G:\Videos" --dry-run
```

All operations logged with `[DRY-RUN]` prefix. No files moved or deleted.

## Logging

Every run creates a timestamped log in `logs/`:

```
logs/unpackr-20251224-143022.log
```

Logs include:
- All operations (extract, move, delete)
- Errors and warnings
- Video health check results with reasons
- Safety interventions (timeouts, stuck detection)

## Security

### Path Traversal Protection
Archives validated before extraction. Rejects:
- Paths containing `..`
- Absolute paths
- Paths escaping target directory

### Command Injection Prevention
All subprocess calls use array form, not shell strings.

### Buffer Overflow Protection
Large operations use temp files instead of pipes.
