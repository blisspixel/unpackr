# Safety Contract

Unpackr exists to delete things: it turns a messy downloads folder into a clean one and keeps only what is worth keeping. This document defines what is removed, what is protected, and the safeguards that stop it from removing the good file. Run it on a downloads folder, not on folders you curate by hand.

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

- Point Unpackr at a downloads folder. A manual run means "clean now".
- `--dry-run` shows every decision without changing anything; `unpackr restore latest` undoes the last run.

## Junk, Bait And Unfinished Downloads

Usenet and torrent releases are mostly not the video you wanted. Each top-level release folder is screened before anything else happens:

- **Unfinished downloads.** Files ending in `.!qB`, `.!ut`, `.part`, `.crdownload`, `.partial`, `.download` or `.aria2` (`incomplete_download_markers`) are junk on a manual run: they are removed (`download_incomplete`) and the finished files in the same release are processed as usual. A video still being written fails validation and is removed as damaged. Unattended runs (`--unattended`, the service) cannot know you are done waiting, so they skip such releases (`download_in_progress`) and anything changed in the last `settle_minutes` (`folder_still_growing`) and pick them up later.
- **Disc structures.** A release with `VIDEO_TS` or `BDMV` is kept whole (`disc_structure_kept`).
- **Bait.** Executables, scripts, shortcuts and installers (`.exe`, `.lnk`, `.scr`, `.bat`, `.cmd`, `.js`, `.vbs`, `.hta`, `.ps1`, `.msi`, `.jar` and more, see `dangerous_extensions`), names that disguise their type (`Movie.mkv.exe`, Unicode direction controls) and subtitles that are oversized or binary are removed (to quarantine by default) and the **whole release fails**: no video from it is moved, the decoy stays for review, and the run exits `3` with `folder_failed_security`. Archives whose listing contains such files are never extracted (`archive_dangerous_member`). Two exceptions are removed and flagged without failing the release: `rename.bat`/`rename.sh` next to a real video, and RARBG's `RARBG_DO_NOT_MIRROR.exe` placeholder. Unpackr never runs or opens any of these files.
- **Junk by name.** Tracker spam (`RARBG.txt`, `WWW.*.COM*`), OS cruft (`Thumbs.db`, `.DS_Store`, `desktop.ini`, `._*`, `@eaDir`), torrent padding files (verified all zeros) and empty files are removable whatever their extension (`junk_name_patterns`).
- **Samples.** A video named sample, proof, trailer, preview or promo, or inside a `Sample`, `Proof` or `Screens` folder anywhere in the release, is removed when it is at most `max_sample_duration_seconds` (300) long, or, with no readable duration, smaller than `min_sample_size_mb`. Next to a main video of 20 minutes or more, another video under 10% of its length and under 5 minutes is also a sample. The longest video in a release is never removed as a sample, and a long video is never removed on its name alone.

## What Gets Deleted

| Item | Configurable? |
|------|---------------|
| Junk files (NFO, SFV, URL, DIZ, TXT, M3U) | Yes: `removable_extensions` |
| Sample videos (< 50MB) | Yes: `min_sample_size_mb` |
| Previews and samples shorter than 10 seconds | Yes: `min_video_duration_seconds` |
| Corrupt/truncated videos | No: always deleted, listed under DAMAGED, RE-DOWNLOAD |
| Unfinished downloads (manual runs) | Yes: `incomplete_download_markers` |
| Archive sets and their `.par2` files after a successful extraction | No: always deleted |
| Archive sets that fail with CRC/data errors | No: always deleted, listed for re-download |
| Releases PAR2 says are damaged beyond repair (no set could be extracted) | No: always deleted, listed for re-download |
| Empty folders | No: always deleted |
| Processed folders after extraction | No: always deleted |

## What Never Gets Deleted

| Item | Configurable? |
|------|---------------|
| Videos that pass validation | Moved to destination |
| Music folders (10+ files) | Yes: `min_music_files` |
| Image folders (10+ files, 10MB+) | Yes: `min_image_files` |
| Document folders (10+ files) | Yes: `min_documents` |
| Folders with files of an unrecognized extension | Always preserved |
| Incomplete, unreadable, password-protected or interrupted archive sets | Kept for retry; the run exits `3` |
| A PAR2 release par2 could not judge (not installed, tool error) next to unrecognized files, which may be renamed volumes | Kept; the run exits `3` |
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

## PAR2 And Archives

- PAR2 runs first, once per set, and is offered every file in the folder (`par2 r <set>.par2 *`), so volumes renamed by an obfuscated post are matched and renamed back. par2 expands the `*` itself on every OS.
- PAR2 never removes anything. Whatever it reports, extraction still runs and 7-Zip checks every file's CRC; that check decides whether a set is good. Without par2 installed, archives still extract.
- Archive volumes and `.par2` files are removed only after their set extracted cleanly (`extraction_verified`, enforced by invariant I3, which also recognises split volumes such as `.r00`, `.7z.001`, `.z01`). The archive step refuses to remove anything when no remover is configured, rather than falling back to a permanent delete.
- 7-Zip runs with `-p-`, so a password-protected archive fails at once (`archive_password`) instead of waiting at a prompt.
