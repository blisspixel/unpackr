# Troubleshooting

## Common Issues

### "7-Zip not found"

Install 7-Zip from https://www.7-zip.org/ or add the path to config.json:

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe"]
  }
}
```

### "par2cmdline not found"

Optional but recommended. Install from https://github.com/Parchive/par2cmdline or add path to config.json.

Without par2, corrupted archives cannot be repaired.

### "ffmpeg not found"

Optional. Install from https://ffmpeg.org/ for video validation.

Without ffmpeg, videos are assumed good and moved without health checks.

### Videos not moving to destination

1. Check destination path exists and is writable
2. Check logs for errors: `logs/unpackr-YYYYMMDD-HHMMSS.log`
3. Run with `--dry-run` to see what would happen
4. Search logs for "Video health check FAILED" - corrupt videos are deleted, not moved

### Slow or hanging

- Large archives take time (50GB archive = up to 2 hours)
- Network drives are slower than local
- Check logs for timeout messages
- Timeouts are dynamic based on file size

### Permission errors

- Run as Administrator if needed
- Check folder permissions
- Files locked by other processes will be retried (3 passes with delays)

### Command not found

From project directory: ensure `unpackr.bat` exists

From other directories: ensure Python Scripts directory is in PATH:
```
C:\Users\<you>\AppData\Roaming\Python\Python310\Scripts\
```

## Diagnostics

Run the diagnostic tool:

```bash
unpackr-doctor
```

This checks:
- Python version
- Required packages
- External tools (7z, par2, ffmpeg)
- Config file validity
- Write permissions
- Disk space

## Log Files

Logs are in the `logs/` folder:

```
logs/unpackr-20251224-143022.log
```

Search for:
- `ERROR` - failures
- `WARNING` - potential issues
- `Video health check FAILED` - rejected videos
- `timeout` - operations that took too long

## Getting Help

1. Run `unpackr-doctor` and note any issues
2. Check logs for specific errors
3. Try `--dry-run` to see what would happen
4. Test on a single folder first
