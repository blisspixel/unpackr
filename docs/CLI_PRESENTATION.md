# CLI Presentation

This document covers terminal rendering for `unpackr`.

## Scope

- Processing runs on Windows, Linux, and macOS.
- The same dashboard is used on each. When the terminal cannot show it, Unpackr prints one line per folder.

## Modes

`auto`, `light`, and `full` are the same six-line dashboard on an interactive terminal. `off` prints one line per folder.

The dashboard is skipped when any of these is true:

- `--animations off` or `UNPACKR_ANIMATIONS=off`
- stdout is not a TTY
- `CI` is a truthy value (`1`, `true`, `yes`, `on`)
- `--no-color`, `UNPACKR_NO_COLOR`, `NO_COLOR`, or `TERM=dumb`
- `UNPACKR_NO_ANIM` is set

There is no Rich dependency. The dashboard does not clear the screen and does not estimate time saved.

```bash
unpackr --animations auto
unpackr --animations off
```

`light` and `full` are accepted and show the same dashboard.

## What the dashboard shows

Six lines, redrawn in place at most ten times a second. The first paint is immediate. A stopped dashboard flushes one last paint and then moves to the next line.

1. Spinner (`-`, `\`, `|`, `/`), the verb, `current/total`, and the percent. The spinner is cyan.
2. A bar of `#` and `-`.
3. Counts. Labels are dim. `moved` and `repaired` are green. `bad` is red. `extracted` is blue. `found`, `cleaned`, `empty`, and `junk` use the default foreground.
4. `speed: … folders/min | eta: …`
5. A dim comment, when one is loaded.
6. The dim target.

Lines are truncated to the terminal width minus one. Truncation ignores ANSI colour sequences, so a coloured count is not cut short of its digits.

The wordmark is printed once, after configuration, when the terminal is wide enough. `--version` exits during argument parsing, before that banner.

The end of a run is a three-line receipt: folders and bytes freed, videos moved, and the restore command including `--source`. It does not clear the screen and it does not print the wordmark again. The receipt is skipped when there is no source directory to report.

## Colour

Roles are cyan (accent), green (success), yellow (warning), red (error), blue (info), and dim (labels). Neutral numbers keep the terminal's foreground. There is no magenta and no forced white.

- `--no-color` disables ANSI colour.
- `UNPACKR_NO_COLOR=1` and `NO_COLOR` do the same.
- `TERM=dumb` disables colour.

On Python 3.14 and newer, argparse's own error colour is turned off. Unpackr paints its own output.

## Environment

- `UNPACKR_ANIMATIONS`: `auto`, `off`, `light`, or `full`
- `UNPACKR_NO_COLOR`: `1` disables colour
- `NO_COLOR`: standard no-colour signal
- `CI`: when truthy, the dashboard is off
- `UNPACKR_NO_ANIM`: dashboard off
- `TERM=dumb`: dashboard and colour off

## Precedence

1. CLI flags (`--animations`, `--no-color`)
2. Environment (`UNPACKR_ANIMATIONS`, `UNPACKR_NO_COLOR`, `NO_COLOR`)
3. Config (`animations`, `no_color`)
4. Defaults (`animations=auto`, colour enabled)

## Degradation

- Non-interactive terminals and CI print one line: `[current/total] target`.
- A rendering failure must not change what the run does.
