# Exit Codes And Machine Output

Stable contracts for CI and automation. Prefer machine JSON when available.

## Summary

| Command | `0` | `1` | `2` |
|---------|-----|-----|-----|
| `unpackr` | Completed or clean user abort before work | Setup/runtime failure | argparse usage error |
| `unpackr-doctor` | Ready (`status=ready`) | Blocked (`status=blocked`) | argparse usage error |
| `vhealth` | Completed scan | Invalid input / runtime failure | argparse usage error |

## unpackr

| Code | When |
|------|------|
| `0` | Successful processing; dry-run finished; user cancelled countdown; process-conflict abort before work |
| `1` | Invalid/missing config; path validation failure; logging setup failure; missing required tools; scan/preflight failure; initialization failure; force-cancel after first Ctrl+C |
| `2` | Invalid CLI arguments (argparse) |

### Structured run summary (`--json`)

```bash
unpackr --source "~/Downloads" --destination "~/Videos" --dry-run --json
```

When `--json` is set, Unpackr prints a single JSON object to stdout after the run (human progress remains on the terminal). The object includes:

- `timestamp_utc`, `tool`, `version`
- `exit_code`, `status` (`completed` \| `cancelled` \| `failed` \| `planned`)
- `dry_run`, `cancelled`
- `paths.source`, `paths.destination`
- `counts.*` processing counters
- `errors`, `warnings`, `recommended_actions`

## unpackr-doctor

| Code | When |
|------|------|
| `0` | No blocking issues (`status: "ready"`) |
| `1` | One or more blocking issues (`status: "blocked"`) |
| `2` | Invalid CLI arguments |

JSON contract: [DOCTOR_JSON.md](DOCTOR_JSON.md).

CI example:

```bash
unpackr-doctor --json > doctor.json
python -c "import json,sys; d=json.load(open('doctor.json')); sys.exit(0 if d['exit_code']==0 and d['counts']['issues']==0 else 1)"
```

## vhealth

| Code | When |
|------|------|
| `0` | Scan finished (including read-only and delete-enabled modes) |
| `1` | Missing/invalid path; invalid config; uncaught runtime error; Ctrl+C |
| `2` | Invalid CLI arguments |

```bash
vhealth --version
vhealth "~/Videos" --min-resolution 720p
```

## Versioning

Package version is defined in `version.py` and shown by `vhealth --version` and in unpackr JSON `version`.
