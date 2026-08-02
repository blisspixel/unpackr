# Troubleshooting

Most failures are environment or dependency related. Start with `unpackr-doctor`, then validate `tool_paths` in the active config described in [Configuration](CONFIGURATION.md).

## Common Issues

### 7-Zip Not Found

Install [7-Zip](https://www.7-zip.org/) or add the path in your active config:

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe"]
  }
}
```

### `par2cmdline` Not Found

Optional but recommended. Install [par2cmdline](https://github.com/Parchive/par2cmdline) or add the path in your active config.

Without par2, corrupted archives cannot be repaired.

### `ffmpeg` Not Found

Optional. Install [ffmpeg](https://ffmpeg.org/) for video validation.

Without ffmpeg, health-check reliability is reduced. Install ffmpeg for expected video validation behavior.

### Videos Not Moving To Destination

1. Check destination path exists and is writable
2. Check logs for errors: `logs/unpackr-YYYYMMDD-HHMMSS.log`
3. Run with `--dry-run` to see what would happen
4. Search logs for `Video health check FAILED` (corrupt videos are deleted, not moved)

### Slow Or Hanging

- Large archives take time (for example, a `50GB` archive can take up to ~2 hours)
- Network drives are slower than local
- Check logs for timeout messages
- Timeouts are dynamic based on file size

### Permission Errors

- Use an elevated shell only when required by folder policy
- Check folder permissions
- Files locked by other processes will be retried (3 passes with delays)

### Command Not Found Or `ModuleNotFoundError`

From the project directory, reinstall with the same Python interpreter that will run the command:

```powershell
python -m pip install .
unpackr --help
```

If an old launcher is still being selected, remove and reinstall it:

```powershell
python -m pip uninstall unpackr
python -m pip install .
```

As a checkout-only fallback, use `python -m unpackr --help` or run `unpackr.bat` explicitly.

From other directories, ensure the Scripts directory for the installation interpreter is in `PATH`. Locate it with `python -c "import sysconfig; print(sysconfig.get_path('scripts'))"`.

If `python` resolves to an older interpreter on Windows, run tools explicitly with `py -3.14 -m ...` or another installed `3.11+` launcher target.

## Diagnostics

Run the diagnostic tool:

```bash
unpackr-doctor
```

This checks:
- Python version
- Required runtime dependencies
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
5. If contributing, run `pre-commit run --all-files` before opening a change
