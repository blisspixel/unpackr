# Platform Support

Unpackr targets **Windows, Linux, and macOS** with the same safety contract.

Cross-platform policy helpers live in `utils/platform_support.py`.

## Install External Tools

### Windows

- Required: [7-Zip](https://www.7-zip.org/) (`7z` on PATH or absolute path in config)
- Recommended: [par2cmdline](https://github.com/Parchive/par2cmdline), [ffmpeg](https://ffmpeg.org/)

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install p7zip-full par2 ffmpeg
```

### Fedora / RHEL

```bash
sudo dnf install p7zip par2cmdline ffmpeg
```

### macOS (Homebrew)

```bash
brew install p7zip par2 ffmpeg
```

Then install Unpackr:

```bash
python -m pip install .
unpackr-doctor
```

## Launchers

After `python -m pip install .`, console scripts are available on every OS:

- `unpackr`
- `unpackr-doctor`
- `vhealth`

From a source checkout:

| OS | Launchers |
|----|-----------|
| Windows | `unpackr.bat`, `vhealth.bat` |
| Linux / macOS | `./unpackr.sh`, `./unpackr-doctor.sh`, `./vhealth.sh` |

Make shell launchers executable once:

```bash
chmod +x unpackr.sh unpackr-doctor.sh vhealth.sh
```

## Filesystem Notes

These behaviors are intentional and shared across platforms:

- Symlinks / junctions are refused for destructive cleanup (fail closed).
- Filename sanitization removes characters that break Windows or network shares so outputs stay portable.
- Tool paths must be absolute files or bare command names (no relative `./bin/tool` execution).
- Case-sensitive filesystems (typical Linux) can surface collisions that Windows hides; review logs if two sources differ only by case.

Planned deeper coverage (roadmap Phase C): APFS/ZFS/bind-mount/SMB-NFS quirk matrix and multi-user NAS permission guidance.

## CI Expectations

- Windows: full regression suite + coverage gate
- Linux: full regression suite + optional real-tool checks when `p7zip`/`ffmpeg` are installed
- macOS: expanded suite covering platform helpers, safety, config, doctor, packaging, and optional real-tool checks
