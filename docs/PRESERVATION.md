# Preservation Heuristics

Unpackr deletes aggressively only when a folder is classified as processed video work. Content collections are preserved.

Defaults below come from `config_files/config.json` / `Config.DEFAULT_CONFIG` and are overridable.

## What Is Preserved

| Content type | Default threshold | Notes |
|--------------|-------------------|-------|
| Music | `min_music_files` (**10**) | Folder with at least this many music-extension files |
| Images | `min_image_files` (**10**) **and** total image size **> 10 MB** | Avoids keeping tiny cover-art/thumbnail folders |
| Documents | `min_documents` (**10**) | Folder with at least this many document-extension files |
| Unrecognized residual files | Always | If a folder still has non-junk unknowns after processing, deletion is refused |

Destination directories are never scanned for cleanup of source leftovers.

## Classification During Pre-Scan

For each source subfolder:

1. If it contains videos or archive files (`.rar` / `.7z`), it is a **video folder** (candidate for processing).
2. Else if music/images/documents meet the thresholds above, it is a **content folder** (preserved).
3. Else it is treated as **junk/empty-ish** and may be removed by cleanup passes.

Image rule uses **both** count and total size so a handful of screenshots does not preserve an entire empty download tree.

## Deletion Guards

Even after a successful video move, a folder is deleted only when `is_folder_empty_or_removable` agrees:

- No symlink/junction at the folder root or (for force-delete) in the tree
- No significant image collection remaining
- Remaining files are junk/removable extensions or known incomplete archive debris
- PAR2/archive error flags can keep partial sets from being wiped incorrectly

## Resume Behavior

When interrupted, Unpackr can resume with `--resume`:

- State file: `<source>/.unpackr-state.json`
- Records folders that finished `process_folder` successfully
- Resume skips those folders (no duplicate moves for completed work)
- Successful non-cancelled completion clears the state file
- Corrupt/missing state is ignored (fail open to full reprocess, never partial silent skip of unknown paths)

`--resume` does **not** reconstruct half-finished extractions inside a folder; it only skips folders already marked complete.

## Operator Tips

- Prefer `--dry-run` / `--show-plan` before live deletes on a new source tree
- Lower `min_*` thresholds only when you intentionally want smaller collections kept
- Keep `removable_extensions` conservative; removing `.txt` from the list keeps nfo/txt companions
