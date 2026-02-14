# Unpackr

Automated cleanup for Usenet downloads. Repairs archives, extracts videos, validates playback, removes junk.

**Windows only.** Requires Python 3.11+, [7-Zip](https://www.7-zip.org/). Optional: [par2cmdline](https://github.com/Parchive/par2cmdline), [ffmpeg](https://ffmpeg.org/).

## What It Does

```
Downloads/                         
├── MyVideo/                       
│   ├── MyVideo.part01.rar        
│   ├── MyVideo.part02.rar         →  Destination/MyVideo.mkv (validated)
│   ├── MyVideo.par2              
│   └── sample.mkv                
├── OtherShow/                     
│   └── episode.mkv                →  Destination/episode.mkv (validated)
└── MusicLibrary/                  
    └── (10+ songs)                →  (preserved in place)
```

- Repairs corrupted archives with PAR2
- Extracts multi-part RAR/7z
- Validates videos (rejects truncated/corrupt)
- Moves working videos to destination
- Deletes junk (NFO, SFV, samples, empty folders)
- Preserves folders with 10+ music/image/document files

## Usage

```bash
pip install -e .
unpackr-doctor                    # verify setup
unpackr "G:\Downloads" "G:\Videos" --dry-run   # preview
unpackr "G:\Downloads" "G:\Videos"             # run
```

## Safety

**This tool deletes files.** Back up first. Test with `--dry-run`. Check logs after.

Designed to fail safely: rejects uncertain files rather than risking bad moves. Corrupt videos are deleted, not repaired - re-download from source is the proper fix. But no deletion tool is risk-free.

## Configuration

Edit `config_files/config.json` for thresholds and tool paths. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "7-Zip not found" | Install 7-Zip or add path to config.json |
| "ffmpeg not found" | Optional. Without it, videos assumed good |
| Videos not moving | Check `logs/`. Corrupt videos are deleted |
| Slow/hanging | Large archives take time. Check logs |
| Need to stop | Ctrl+C exits cleanly within seconds |

More: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Other Tools

- `vhealth "G:\Videos"` - Deep validation, duplicate detection (keeps files prefixed with "fav")
- `unpackr-doctor` - Diagnose setup issues

## Docs

[Configuration](docs/CONFIGURATION.md) ·
[Safety](docs/SAFETY.md) ·
[Technical](docs/TECHNICAL.md) ·
[Changelog](docs/CHANGELOG.md)
