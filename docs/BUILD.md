# Build And Install Modes

## Supported Runtime

- Windows, Linux, macOS
- Python `3.12+`
- External tools: `7z`/`7zz` (required), `par2` and `ffmpeg` (recommended)

## Recommended Install

On externally managed Pythons (Arch, Debian, Ubuntu, and PEP 668), install into an isolated environment:

```bash
uv tool install git+https://github.com/blisspixel/unpackr
# or, from a checkout: uv tool install .
# pipx install git+https://github.com/blisspixel/unpackr
unpackr --help
unpackr-doctor
```

This provides console entry points:
- `unpackr`
- `unpackr-doctor`
- `vhealth`

The wheel contains one `unpackr` package and the bundled default configuration. The commands work outside the repository directory after installation. Inside a virtualenv, `python -m pip install .` installs the same scripts.

For editable contributor installs, create a virtualenv first:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

Use the same Python `3.12+` interpreter for installation and command execution. On Windows, `py -3.15 -m pip install .` inside a virtualenv is an explicit alternative when `python` resolves to an older interpreter.

## OS Notes

- **Windows:** `unpackr.bat` / `vhealth.bat` wrappers are optional conveniences. Default config still lists common `Program Files` tool locations as fallbacks after PATH names.
- **Linux / macOS:** install tools from the platform package manager and keep `7z`/`7zz`, `par2`, and `ffmpeg` on `PATH`. Platform helpers also probe common Homebrew prefixes on macOS.
- Cross-platform process detection and force-delete fallbacks live in `src/unpackr/utils/platform_support.py`.

## Source Launchers

Windows wrappers:
- `unpackr.bat`
- `vhealth.bat`

POSIX wrappers (Linux/macOS source checkouts):
- `./unpackr.sh`
- `./unpackr-doctor.sh`
- `./vhealth.sh`

```bash
chmod +x unpackr.sh unpackr-doctor.sh vhealth.sh
./unpackr.sh --help
```

If needed, place wrappers in a directory that is already on your `PATH`.

Platform package recipes and filesystem notes: [PLATFORMS.md](PLATFORMS.md).

## Standalone EXE

A first-party EXE release pipeline is not currently maintained.
For historical packaging notes and scripts, see `docs/archive/`.

## Verification

```powershell
unpackr-doctor
unpackr --help
vhealth --help
```
