# Changelog

Release dates are included where recorded.

## Unreleased

- Raised and enforced the quality gate through local `pre-commit` and CI.
- Current full-suite baseline is `482` passing tests and `86.24%` total coverage.
- Expanded stricter Pyright coverage to `core/config.py`, `core/file_handler.py`, and `core/safety_invariants.py`.
- Extracted CLI prompt/presentation helpers into `utils/cli_prompts.py` to reduce `unpackr.py` surface area.
- Pushed targeted module coverage higher:
  - `core/config.py` to `98%`
  - `core/file_handler.py` to `92%`
  - `core/video_processor.py` to `91%`
  - `unpackr.py` to `82%`
- Updated docs to use the current Windows quality workflow (`py -3.13 -m ...` where appropriate).
- Enforced external tool version policy:
  - `7z >= 22.0` (blocking)
  - `par2 >= 0.8.1` (warning)
  - `ffmpeg >= 4.4` (warning)
- Refreshed core docs (`README`, `ROADMAP`, `TECHNICAL`, `BUILD`, `TROUBLESHOOTING`) for current behavior and support matrix.
- Archived superseded UX doc to `docs/archive/UX_DESIGN.md` and added `docs/archive/README.md`.

## v1.3.0 (2026-01-07)

- Graceful cancellation: `Ctrl+C` exits within 5 seconds.
- Terminates running `7z`/`par2`/`ffmpeg` processes on cancel.
- Shows `cancelled` status in summary with partial stats.
- Second `Ctrl+C` forces immediate exit.
- `vhealth`: fixed double-deletion bug.
- `vhealth`: cleaner progress display (single line).
- `vhealth`: suppressed noisy log messages during progress.
- `vhealth`: keeps files with `fav` prefix when duplicates are found.

## v1.2.2 (2026-01-07)

- Progress display shows `calculating...` instead of `0.0` during warmup.
- Fixed structured events module to handle non-existent files gracefully.
- Fixed success rate calculation to use terminal states only.
- Removed broken chaos tests.
- Simplified roadmap to match project philosophy.

## v1.2.1

- Modern progress display with live stats.
- Rarity-based comment system.
- Improved filename sanitization (Cyrillic/Unicode transliteration).
- Non-recursive video scanning for faster UI updates.
- UTF-8 console support on Windows.

## v1.2.0

- Fast folder scanning with `os.scandir` (2 to 3x faster).
- Dynamic timeouts based on file size (handles 50GB+ archives).

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

- Initial release.
- PAR2 repair and verification.
- RAR/7z extraction.
- Video health validation.
- Junk file cleanup.
- Content folder preservation.
- Comprehensive logging.
- 33 tests.
