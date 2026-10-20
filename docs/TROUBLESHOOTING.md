# Troubleshooting

Most failures are environment or dependency related. Start with `unpackr-doctor`, then validate `tool_paths` in the active config described in [Configuration](CONFIGURATION.md).

## Common Issues

### 7-Zip Not Found

Install a package-manager build or vendor binary so `7z`/`7zz` is on PATH. See [PLATFORMS.md](PLATFORMS.md).

Windows absolute-path example:

```json
{
  "tool_paths": {
    "7z": ["C:\\Program Files\\7-Zip\\7z.exe"]
  }
}
```

Linux/macOS usually only need PATH names:

```json
{
  "tool_paths": {
    "7z": ["7z", "7zz"]
  }
}
```

### `par2cmdline` Not Found

Optional but recommended. Install via your OS package manager (`par2` / `par2cmdline`) or set an absolute path in config.

Without par2, damaged archives cannot be repaired and obfuscated (renamed) volumes cannot be matched; archives still extract, and 7-Zip checks every file's CRC. A release that is only `.par2` files and unrecognized names is kept for you to look at (exit `3`).

### `ffmpeg` Not Found

Optional. Install [ffmpeg](https://ffmpeg.org/) for video validation (`brew`/`apt`/`dnf` recipes in [PLATFORMS.md](PLATFORMS.md)).

Without ffmpeg, health-check reliability is reduced.

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

From a checkout, reinstall into an isolated environment (this works on externally managed Pythons):

```powershell
uv tool install --reinstall .
unpackr --help
```

If an old launcher is still being selected, remove and reinstall it:

```powershell
uv tool uninstall unpackr
uv tool install .
```

As a checkout-only fallback, run `unpackr.sh` or `unpackr.bat`. Those wrappers put `src` on `PYTHONPATH`. A bare `python -m unpackr` from the checkout cannot see the package until unpackr is installed.

From other directories, ensure the Scripts directory for the installation interpreter is in `PATH`. Locate it with `python -c "import sysconfig; print(sysconfig.get_path('scripts'))"`.

If `python` resolves to an older interpreter on Windows, run tools explicitly with `py -3.15 -m ...` or another installed `3.11+` launcher target.

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
