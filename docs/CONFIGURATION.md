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

### `min_music_files`, `min_image_files`, `min_documents`

Folders meeting these file-count thresholds are preserved. Default: `10`.

Image folders also require at least `10MB` total size to avoid preserving cover-art/thumbnail folders.

### `removable_extensions`

Metadata and junk extensions deleted during ordinary cleanup. Archive fragments, extensionless junk, and other explicitly classified processing artifacts are handled by separate safety rules described in [Safety](SAFETY.md).

To keep .txt files, remove ".txt" from the list.

### `video_extensions`

File extensions recognized as videos. Add formats supported by your ffmpeg build.

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
