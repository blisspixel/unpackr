# Safety Contract

Unpackr deletes files during cleanup. This document defines what can be deleted, what is protected, and which safeguards are enforced.

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
| Corrupt/truncated videos | No: always deleted |
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
| Anything in destination directory | Never touched |

## Safety Mechanisms

### Path Containment
- All extractions happen in the source directory
- Writes are constrained to expected source/destination targets
- Archive contents validated before extraction (no path traversal)

### Fail-Closed Validation
- When uncertain, reject rather than proceed
- Corrupt archive listing = skip extraction
- Video validation requires ffmpeg for full reliability

### Race Condition Prevention
- Folder state re-verified immediately before deletion
- Double-check pattern prevents unsafe deletions

### Resource Limits
- Dynamic timeouts based on file size
- Recursion depth limits (10 levels)
- Memory-bounded failure tracking
- Global runtime limit (4 hours)

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
