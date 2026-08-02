# Build And Install Modes

## Supported Runtime

- Windows, Linux, macOS
- Python `3.11+`
- External tools: `7z`/`7zz` (required), `par2` and `ffmpeg` (recommended)

## Recommended Install

```bash
python -m pip install .
unpackr --help
unpackr-doctor
```

This provides console entry points:
- `unpackr`
- `unpackr-doctor`
- `vhealth`

The install also includes the top-level command modules and bundled default configuration files. The commands therefore work outside the repository directory after installation.

For editable contributor installs:

```bash
python -m pip install -e .[dev]
pre-commit install
pre-commit run --all-files
```

Use the same Python `3.11+` interpreter for installation and command execution. On Windows, `py -3.14 -m pip install .` is an explicit alternative when `python` resolves to an older interpreter.

## OS Notes

- **Windows:** `unpackr.bat` / `vhealth.bat` wrappers are optional conveniences. Default config still lists common `Program Files` tool locations as fallbacks after PATH names.
- **Linux / macOS:** install tools from the platform package manager and keep `7z`/`7zz`, `par2`, and `ffmpeg` on `PATH`. Platform helpers also probe common Homebrew prefixes on macOS.
- Cross-platform process detection and force-delete fallbacks live in `utils/platform_support.py`.

## Batch Wrapper Mode (Windows)

You can also run via the included wrappers:
- `unpackr.bat`
- `vhealth.bat`

If needed, place wrappers in a directory that is already on your `PATH`.

## Standalone EXE

A first-party EXE release pipeline is not currently maintained.
For historical packaging notes and scripts, see `docs/archive/`.

## Verification

```powershell
unpackr-doctor
unpackr --help
vhealth --help
```
