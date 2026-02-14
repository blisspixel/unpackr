# CLI Presentation

This document covers terminal rendering behavior for `unpackr`.

## Scope

- Processing workflow support remains Windows-only.
- CLI presentation paths are designed to degrade safely across Windows, Linux, and macOS terminals.

## Modes

`unpackr` supports animation modes:

- `auto`: default; enables Rich live rendering on interactive terminals.
- `off`: disables animated rendering.
- `light`: Rich live rendering without enhanced effects.
- `full`: richer visual effects for status/action lines.

Use via CLI:

```bash
unpackr --animations auto
unpackr --animations off
unpackr --animations light
unpackr --animations full
```

## Color Control

- `--no-color`: disable ANSI color/styled output.
- `UNPACKR_NO_COLOR=1` or `NO_COLOR`: environment-based color disable.

## Environment Variables

- `UNPACKR_ANIMATIONS`: `auto|off|light|full`
- `UNPACKR_NO_COLOR`: `1` to disable color
- `NO_COLOR`: standard no-color signal
- `CI`: when set, advanced rendering paths are disabled automatically

## Precedence

Presentation settings precedence:

1. CLI flags (`--animations`, `--no-color`)
2. Environment variables (`UNPACKR_ANIMATIONS`, `UNPACKR_NO_COLOR`, `NO_COLOR`)
3. Config values (`animations`, `no_color`)
4. Defaults (`animations=auto`, color enabled)

## Degradation Policy

- Non-interactive terminals and CI should not rely on animated rendering.
- Rendering failures must not affect processing flow.
- Optional enhanced effects must always have safe fallback paths.
