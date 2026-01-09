# Roadmap

## Non-Goals

- GUI, cloud, plugins, parallel processing, audio, metadata enrichment

## Design Notes

**Why sequential processing?** HDD random read is 20-100x slower than sequential. Parallel causes thrashing.

**Why no async?** External tools (7z, par2, ffmpeg) block anyway.

---

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for version history.
