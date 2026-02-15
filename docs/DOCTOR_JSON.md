# Doctor JSON Output

`unpackr-doctor --json` emits machine-readable diagnostics for CI and automation.

## Usage

```bash
unpackr-doctor --json
```

The command exits with:

- `0` when there are no blocking issues (`status: "ready"`)
- `1` when blocking issues are present (`status: "blocked"`)

## JSON Schema

```json
{
  "timestamp_utc": "string (ISO-8601 UTC timestamp)",
  "exit_code": "number (0 or 1)",
  "status": "string (ready|blocked)",
  "counts": {
    "passed": "number",
    "warnings": "number",
    "issues": "number"
  },
  "passed": ["string"],
  "warnings": ["string"],
  "issues": ["string"],
  "recommended_actions": ["string"]
}
```

## Example: Ready

```json
{
  "timestamp_utc": "2026-02-14T18:30:00.000000+00:00",
  "exit_code": 0,
  "status": "ready",
  "counts": {
    "passed": 10,
    "warnings": 1,
    "issues": 0
  },
  "passed": ["Python version", "Configuration file"],
  "warnings": ["ffmpeg not found - video validation will be skipped"],
  "issues": [],
  "recommended_actions": [
    "Install ffmpeg if you want full video health validation.",
    "Re-run `unpackr-doctor` and confirm zero issues before live run."
  ]
}
```

## Example: Blocked

```json
{
  "timestamp_utc": "2026-02-14T18:30:00.000000+00:00",
  "exit_code": 1,
  "status": "blocked",
  "counts": {
    "passed": 7,
    "warnings": 0,
    "issues": 2
  },
  "passed": ["Write permissions"],
  "warnings": [],
  "issues": [
    "Python version too old",
    "7-Zip not found - required for archive extraction"
  ],
  "recommended_actions": [
    "Install Python 3.11+ and run doctor again.",
    "Install 7-Zip and ensure `7z` is on PATH (or set tool path in config).",
    "Re-run `unpackr-doctor` and confirm zero issues before live run."
  ]
}
```

## CI Patterns

### GitHub Actions

```yaml
- name: Doctor check
  run: unpackr-doctor --json > doctor.json
```

The step fails automatically on exit code `1`.

### PowerShell Gate (Custom Rule)

```powershell
unpackr-doctor --json | Out-File -Encoding utf8 doctor.json
$doc = Get-Content doctor.json | ConvertFrom-Json
if ($doc.counts.issues -gt 0) { throw "Doctor blocking issues: $($doc.counts.issues)" }
```
