# Configuration Reference

Edit `config_files/config.json` to customize Unpackr's behavior.

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

Paths to external tools. Each is an array - tries in order until one works.

```json
"tool_paths": {
  "7z": ["C:\\Program Files\\7-Zip\\7z.exe"],
  "par2": ["C:\\custom\\path\\par2.exe"],
  "ffmpeg": ["C:\\ffmpeg\\bin\\ffmpeg.exe"]
}
```

### min_sample_size_mb

Videos smaller than this (in MB) are considered samples and deleted. Default: 50

To keep all videos regardless of size, set to a high value like 5000.

### min_music_files, min_image_files, min_documents

Folders with at least this many files of each type are preserved. Default: 10

Image folders also require 10MB+ total size to distinguish from cover art.

### removable_extensions

File types that get deleted during cleanup. Only files in this list are removed.

To keep .txt files, remove ".txt" from the list.

### video_extensions

File types recognized as videos. Add any format ffmpeg can validate.

### max_log_files

Number of log files to keep. Oldest are deleted. Default: 3

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
