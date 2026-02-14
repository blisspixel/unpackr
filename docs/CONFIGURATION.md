# Configuration Reference

Edit `config_files/config.json` to control runtime behavior.

## Full Example

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe", "7z"],
    "par2": ["bin\\par2.exe", "par2"],
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

### tool_paths

Paths to external tools. Each value is an array; entries are tried in order until one succeeds.

- `7z` is required.
- `par2` and `ffmpeg` are recommended for best reliability/validation coverage.

```json
"tool_paths": {
  "7z": ["C:\\Program Files\\7-Zip\\7z.exe"],
  "par2": ["C:\\custom\\path\\par2.exe"],
  "ffmpeg": ["C:\\ffmpeg\\bin\\ffmpeg.exe"]
}
```

### min_sample_size_mb

Videos smaller than this threshold (MB) are treated as samples and deleted. Default: `50`.

To keep most small files, set a higher threshold such as `5000`.

### min_music_files, min_image_files, min_documents

Folders meeting these file-count thresholds are preserved. Default: `10`.

Image folders also require at least `10MB` total size to avoid preserving cover-art/thumbnail folders.

### removable_extensions

File extensions deleted during cleanup. Only files in this list are removed.

To keep .txt files, remove ".txt" from the list.

### video_extensions

File extensions recognized as videos. Add formats supported by your ffmpeg build.

### max_log_files

Number of log files to retain. Oldest logs are removed first. Default: `3`.

## Common Customizations

**Keep sample files:**
```json
{ "min_sample_size_mb": 5000 }
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
