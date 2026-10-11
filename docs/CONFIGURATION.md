# Configuration Reference

The bundled `config_files/config.json` supplies the default runtime behavior.

For custom settings, copy that file to a writable location and pass it explicitly to each command that should use it:

```powershell
unpackr --config "C:\path\to\config.json" --source "G:\Downloads" --destination "G:\Videos"
unpackr-doctor --config "C:\path\to\config.json"
vhealth "G:\Videos" --config "C:\path\to\config.json"
```

An explicit config path must name an existing file. Unpackr resolves the bundled default relative to the installed module, not the current working directory.

Invalid or unreadable configuration is blocking. The commands exit instead of continuing with fallback deletion and safety settings.

## Common Settings Example

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe", "7z"],
    "par2": ["par2"],
    "ffmpeg": ["ffmpeg"]
  },
  "video_extensions": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"],
  "music_extensions": [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma"],
  "image_extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
  "document_extensions": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx"],
  "removable_extensions": [".nfo", ".sfv", ".url", ".diz", ".txt", ".m3u"],
  "min_sample_size_mb": 50,
  "min_video_duration_seconds": 10,
  "delete_mode": "quarantine",
  "quarantine_retention_days": 14,
  "quarantine_warn_mb": 20480,
  "min_music_files": 10,
  "min_image_files": 10,
  "min_documents": 10,
  "max_log_files": 3,
  "log_folder": "logs"
}
```

## Settings

### `tool_paths`

Paths to external tools. Each value is an array; entries are tried in order until one succeeds.

- `7z` / `7zz` is required.
- `par2` and `ffmpeg` are recommended for best reliability/validation coverage.
- Prefer PATH command names first. Absolute paths are optional fallbacks.
- On every platform, Unpackr also merges built-in platform candidates from `utils/platform_support.py`.

```json
"tool_paths": {
  "7z": ["7z", "7zz", "C:\\Program Files\\7-Zip\\7z.exe"],
  "par2": ["par2"],
  "ffmpeg": ["ffmpeg"]
}
```

### `min_sample_size_mb`

Videos smaller than this threshold (MB) are treated as samples and deleted. Default: `50`.

To keep nearly all small videos, lower the threshold to `1`. Raising the value classifies more videos as samples and deletes more files.

### `min_video_duration_seconds`

Videos shorter than this many seconds are previews, samples or trailers rather than the content you downloaded, and are removed. Default: `10`. They are counted as samples (`videos_sample`), not as corrupt. Set `0` to disable the duration rule.

### `min_music_files`, `min_image_files`, `min_documents`

Folders meeting these file-count thresholds are preserved. Default: `10`.

Image folders also require at least `10MB` total size to avoid preserving cover-art/thumbnail folders.

### `removable_extensions`

Metadata and junk extensions deleted during ordinary cleanup. Archive fragments, extensionless junk, and other explicitly classified processing artifacts are handled by separate safety rules described in [Safety](SAFETY.md).

To keep .txt files, remove ".txt" from the list.

### `video_extensions`

File extensions recognized as videos. Add formats supported by your ffmpeg build.

### `max_sample_duration_seconds`

A video with sample evidence (name or folder) is removed only when it is at most this long. Default: `300`. Protects real episodes titled "Preview" or "Promo".

### `output_layout`

Where and under what name videos land in the destination. Default: `"{name}{ext}"` (flat, as before). Presets:

| Preset | Template | Example |
|---|---|---|
| `flat` | `{name}{ext}` | `Some.Show.S01E02.1080p.mkv` |
| `release` | `{release}{ext}` | `Some.Show.S01E02.1080p.mkv` |
| `movies` | `Movies/{title} ({year})/{title} ({year}){ext}` | `Movies/Movie Title (2026)/Movie Title (2026).mkv` |
| `tv` | `TV/{show}/Season {season:02}/{show} - S{season:02}E{episode:02}{episode_suffix}{ext}` | `TV/Some Show/Season 01/Some Show - S01E02.mkv` |
| `auto` | `tv` for episodes, `movies` for movies, `flat` otherwise | |

Fields for custom templates: `name` (video name, deobfuscated), `ext`, `release` (top-level release folder), `title`, `year`, `show`, `season`, `episode`, `episode_suffix` (`-E03` for multi-episode files). Names are parsed locally from the release folder or file name; there are no network lookups. When a video's name does not provide the fields a template needs, it is moved with the flat layout and a `layout_unparsed` warning. Rendered paths never leave the destination.

### `deobfuscate_names`

When `true` (default), a video with an obfuscated or meaningless name (`a1b2c3d4e5f6...mkv`, 32-character hashes, `abc.xyz...`, `movie.mkv`) takes the name of its release folder, following SABnzbd's heuristics. Reported as `renamed_deobfuscated`.

### `keep_subtitles`

When `true` (default), subtitles that belong to a moved video (`<video>.en.srt`, or RARBG-style `Subs/2_English.srt` in a single-video release) are moved next to it with a matching name, such as `Some Show - S01E02.English.srt`. Reported as `subtitle_moved`. A shared `Subs` folder in a multi-video release is left alone.

### `dedupe_same_title`

Opt-in. When `true`, two videos of the same title in one release (differing only in quality, codec or group tags) keep only the largest; the others are removed as `duplicate_encode`. Default: `false`.

### `dangerous_extensions`

Extensions that mark a release as bait. Default: executables, scripts, shortcuts and installers (Sonarr/Radarr and TRaSH Guides lists). A release containing one is failed and nothing in it is moved.

### `incomplete_download_markers`

File endings that mean a download is still running. Default: `[".!qB", ".!ut", ".part", ".crdownload", ".partial", ".download", ".aria2"]`. Such releases are skipped until a later run.

### `sample_folder_names`

Folder names whose videos are treated as samples. Default: `["sample", "samples", "proof", "proofs", "screens", "screenshots"]`.

### `junk_name_patterns`

Case-insensitive name patterns that are always junk. Default includes `RARBG*.txt`, `WWW.*.COM*`, `Thumbs.db`, `.DS_Store`, `desktop.ini`, `._*` and `*.url`.

### `delete_mode`

How a live run disposes of what it removes. Default: `"quarantine"`.

- `"quarantine"`: move into `<source>/.unpackr-quarantine/<run_id>/` and journal it; undo with `unpackr restore <run_id> --source <dir>`.
- `"trash"`: send to the desktop trash or Recycle Bin.
- `"permanent"`: delete immediately (the behavior before quarantine existed).

### `quarantine_retention_days`

Days to keep a quarantined run before the next live run purges it. Default: `14`. `0` keeps quarantined runs until you remove them.

### `quarantine_warn_mb`

`unpackr-doctor --source <dir>` warns when the quarantine holds more than this many MB. Default: `20480` (20 GB).

### `log_folder`

Where log files go. Default: `"logs"`. A relative value is placed under the per-user state folder (`~/.local/state/unpackr/` on Linux, `~/Library/Logs/unpackr/` on macOS, `%LOCALAPPDATA%\unpackr\` on Windows), so runs never leave a `logs` folder in whatever directory they started from. An absolute or `~` path is used as given.

### `max_log_files`

Number of log files to retain. Oldest logs are removed first. Default: `3`.

### Runtime Safety Limits

- `max_runtime_hours`: maximum run duration. Default: `48`.
- `max_videos_per_folder`: processing-loop safety bound. Default: `500`.
- `max_subfolder_depth`: recursion safety bound. Default: `20`.
- `stuck_timeout_hours`: time without progress before stuck detection. Default: `3`.
- `archive_extraction_loop_limit`: archive extraction loop bound. Default: `100`.

### Retry Settings

- `file_delete_max_attempts`: file deletion attempts. Default: `5`.
- `file_delete_retry_delay`: initial file deletion retry delay in seconds. Default: `1`.
- `folder_delete_max_attempts`: folder deletion attempts. Default: `2`.
- `folder_delete_retry_delay`: folder deletion retry delay in seconds. Default: `5`.
- `file_lock_wait_attempts`: checks while waiting for a lock to clear. Default: `10`.
- `file_lock_wait_delay`: delay between lock checks in seconds. Default: `1`.

All safety and retry values must be positive integers. Invalid values block CLI execution.

## Common Customizations

**Keep nearly all small videos:**
```json
{ "min_sample_size_mb": 1 }
```

**Preserve folders with fewer files:**
```json
{
  "min_music_files": 3,
  "min_image_files": 3,
  "min_documents": 1
}
```

**Keep .txt files:**
```json
{ "removable_extensions": [".nfo", ".sfv", ".url", ".diz", ".m3u"] }
```

**Add .ts video format:**
```json
{ "video_extensions": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg", ".ts"] }
```

## Custom Comments

Place `comments.json` beside an explicit config file to customize optional console comments. If it is absent, Unpackr reads the bundled `comments.sample.json` directly and does not write into the installed package directory.
