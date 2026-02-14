# Changelog

## Unreleased

- Raised CI coverage gate to `80%` and aligned docs/quality commands.
- Expanded regression suite substantially (370+ tests total, 80%+ coverage baseline).
- Enforced external tool version policy:
  - `7z >= 22.0` (blocking)
  - `par2 >= 0.8.1` (warning)
  - `ffmpeg >= 4.4` (warning)
- Refreshed core docs (`README`, `ROADMAP`, `TECHNICAL`, `BUILD`, `TROUBLESHOOTING`) for current behavior and support matrix.
- Archived superseded UX doc to `docs/archive/UX_DESIGN.md` and added `docs/archive/README.md`.

## v1.3.0 (2026-01-07)

- Graceful cancellation: Ctrl+C exits within 5 seconds
- Terminates running 7z/par2/ffmpeg processes on cancel
- Shows "cancelled" status in summary with partial stats
- Second Ctrl+C forces immediate exit
- vhealth: Fixed double-deletion bug
- vhealth: Cleaner progress display (single line)
- vhealth: Suppressed noisy log messages during progress
- vhealth: Keeps files with "fav" prefix when duplicates found

## v1.2.2 (2026-01-07)

- Progress display shows "calculating..." instead of "0.0" during warmup
- Fixed structured events module to handle non-existent files gracefully
- Fixed success rate calculation to use terminal states only
- Removed broken chaos tests
- Simplified roadmap to match project philosophy

## v1.2.1

- Modern progress display with live stats
- Rarity-based comment system
- Improved filename sanitization (Cyrillic/Unicode transliteration)
- Non-recursive video scanning for faster UI updates
- UTF-8 console support on Windows

## v1.2.0

- Fast folder scanning with os.scandir (2-3x faster)
- Dynamic timeouts based on file size (handles 50GB+ archives)

## v1.1.0

### Security
- Path traversal protection (validates archive contents before extraction)
- Command injection prevention (safe subprocess handling)
- Buffer overflow protection (temp files for large operations)

### Stability
- Exception handler cleanup (proper spinner thread cleanup)
- Memory leak fix (bounded deque for failure tracking)
- Race condition fix (double-check before deletion)
- Comprehensive config validation

## v1.0.0

- Initial release
- PAR2 repair and verification
- RAR/7z extraction
- Video health validation
- Junk file cleanup
- Content folder preservation
- Comprehensive logging
- 33 tests
