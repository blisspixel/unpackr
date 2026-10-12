# Preservation Heuristics

Unpackr keeps the good content in a messy downloads folder (videos it moves to your library, plus music, photos and documents it leaves in place) and deletes the rest.

Defaults below come from `config_files/config.json` / `Config.DEFAULT_CONFIG` and are overridable.

## What Is Preserved

| Content type | Default threshold | Notes |
|--------------|-------------------|-------|
| Music | `min_music_files` (**1**) | A folder without videos holding any music is kept |
| Images | `min_image_files` (**1**) | A folder without videos holding any photos is kept |
| Documents | `min_documents` (**1**) | A folder without videos holding any documents is kept (`.txt`, `.nfo` and other junk extensions do not count) |
| Images left in a video release | 10+ images **and** > 10 MB | Fewer is cover art or screenshots, removed with the release |
| Unrecognized residual files | Always | If a folder still has non-junk unknowns after processing, deletion is refused |

Destination directories are never scanned for cleanup of source leftovers.

## Classification During Pre-Scan

For each source subfolder:

1. If it contains videos or archive files (`.rar` / `.7z`), it is a **video folder** (candidate for processing).
2. Else if it holds music, images or documents (at least the thresholds above, default 1), it is a **content folder** (preserved).
3. Else it is treated as **junk/empty-ish** and may be removed by cleanup passes.

Loose music, images and documents in the source folder itself are always left in place.

## Deletion Guards

Even after a successful video move, a folder is deleted only when `is_folder_empty_or_removable` agrees:

- No symlink/junction at the folder root or (for force-delete) in the tree
- No real image collection remaining (10+ images over 10 MB; fewer is cover art)
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
