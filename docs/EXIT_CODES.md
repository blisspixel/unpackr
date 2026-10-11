# Exit Codes And Machine Output

Stable contracts for CI and automation. Prefer machine JSON when available.

## Summary

| Command | `0` | `1` | `2` |
|---------|-----|-----|-----|
| `unpackr` | Completed or clean user abort before work | Setup/runtime failure | argparse usage error (`3`: completed with items needing attention) |
| `unpackr-doctor` | Ready (`status=ready`) | Blocked (`status=blocked`) | argparse usage error |
| `vhealth` | Completed scan | Invalid input / runtime failure | argparse usage error |

## unpackr

| Code | When |
|------|------|
| `0` | Successful processing; dry-run finished; user cancelled countdown; process-conflict abort before work |
| `1` | Invalid/missing config; path validation failure; logging setup failure; missing required tools; scan/preflight failure; initialization failure; force-cancel after first Ctrl+C |
| `2` | Invalid CLI arguments (argparse) |
| `3` | Live run completed, but some items need attention: an archive set was kept because a volume is missing, it could not be listed, it is password-protected or extraction was interrupted, or an archive was blocked for unsafe paths. Details are in `errors`. |

### Structured run summary (`--json`)

```bash
unpackr --source "~/Downloads" --destination "~/Videos" --dry-run --json
```

When `--json` is set, Unpackr prints a single JSON object to stdout after the run (human progress remains on the terminal). The object includes:

- `timestamp_utc`, `tool`, `version`
- `exit_code`, `status` (`completed` \| `completed_with_errors` \| `cancelled` \| `failed` \| `planned`)
- `dry_run`, `cancelled`
- `paths.source`, `paths.destination`
- `counts.*` processing counters
- `errors`, `warnings`, `recommended_actions`

Entries in `errors` and `warnings` start with a reason code in brackets, then `folder/item: detail`:

| Reason code | Level | Meaning |
|-------------|-------|---------|
| `archive_volume_missing` | error | A numbered volume is missing; the set was kept for retry |
| `archive_unlistable` | error | 7-Zip could not list the archive (missing volume, damage or password); kept |
| `archive_incomplete` | error | Extraction stopped at a missing or cut-short volume; kept |
| `archive_password` | error | Password-protected; kept |
| `archive_timeout`, `disk_space_low`, `archive_extract_failed` | error | Extraction did not finish; kept |
| `archive_unsafe_paths` | error | Entries would extract outside the folder; blocked |
| `archive_corrupt` | warning | CRC or data error; treated as junk |
| `video_move_failed` | warning | A valid video could not be moved |
| `no_videos_kept` | warning | Videos were found but every one was removed as a preview, sample or damaged file |

A dry run reports problems it can predict (for example `archive_volume_missing`) as warnings and exits `0`.

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
