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
| `3` | Live run completed, but some items need attention: an archive set was kept because a volume is missing, it could not be listed, it is password-protected or extraction was interrupted; an archive was blocked for unsafe paths; a release contained bait; or par2 could not judge a release with unrecognized files (possibly renamed volumes). Details are in `errors`. Damaged downloads that were removed are listed in `damaged` and do not change the exit code. |

### Structured run summary (`--json`)

```bash
unpackr --source "~/Downloads" --destination "~/Videos" --dry-run --json
```

When `--json` is set, stdout carries only a single JSON object, printed after the run, so `unpackr --json ... | jq` works; the banner, progress and summary screen go to stderr. The object includes:

- `timestamp_utc`, `tool`, `version`
- `exit_code`, `status` (`completed` \| `completed_with_errors` \| `cancelled` \| `failed` \| `planned` \| `skipped`). `skipped` (exit `0`) means an `--unattended` run found another run already working on the source; without `--unattended` the same situation is `failed` (exit `1`) with `run_locked`.
- `dry_run`, `cancelled`
- `paths.source`, `paths.destination`
- `counts.*` processing counters (`counts.folders_settling`: releases an unattended run left because they were still being written)
- `damaged`: downloads found damaged this run and removed as junk (corrupt or truncated videos, archives with CRC errors, releases PAR2 could not repair); worth downloading again
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
| `archive_corrupt` | warning | CRC or data error; treated as junk and listed in `damaged` |
| `par2_damaged` | warning | PAR2 says the data is damaged beyond repair; with archives, 7-Zip's CRC check still decides; without, the release is junk and listed in `damaged` |
| `par2_tool_error`, `par2_unavailable` | warning or error | par2 could not judge the data (tool error, not installed). A warning when extraction went ahead; an error when unrecognized files (possibly renamed volumes) were kept |
| `archive_dangerous_member` | error | The archive contains an executable, script or shortcut; not extracted |
| `security_executable`, `security_dangerous_ext`, `security_double_extension`, `security_bidi_name`, `security_suspicious_subtitle` | error | Bait file removed; its release fails |
| `folder_failed_security` | error | Release contained bait; nothing was moved from it |
| `security_rename_script`, `security_known_marker` | warning | Removed, but the release continues |
| `download_incomplete` | warning | Manual run: unfinished download files (`.part`, `.!qB` ...) removed as junk |
| `download_in_progress` | warning | Unattended run: release still downloading; skipped this run |
| `disc_structure_kept` | warning | `VIDEO_TS`/`BDMV` release kept whole |
| `folder_still_growing` | warning | Unattended run: the download changed within `settle_minutes`; skipped this run |
| `run_locked` | warning or error | Another run holds `<source>/.unpackr-lock` |
| `layout_unparsed` | warning | Name did not fit `output_layout`; moved with the flat layout |
| `renamed_deobfuscated` | item | Obfuscated video name replaced with the release name |
| `subtitle_moved` | item | Subtitle moved next to its video |
| `video_move_failed` | warning | A valid video could not be moved |
| `no_videos_kept` | warning | Videos were found but every one was removed as a preview, sample or damaged file |

A dry run reports problems it can predict (for example `archive_volume_missing`) as warnings and exits `0`.

### Removal block

Live runs add `removal`: `mode`, `run_id`, `journal`, `quarantine_path`, `quarantined_files`, `quarantined_bytes`, `trashed_files`, `retention_days` and `restore_command`. When anything was quarantined, `recommended_actions` starts with the restore command.

### Run subcommands

| Command | Exit |
|---------|------|
| `unpackr runs --source DIR [--json]` | `0` |
| `unpackr restore RUN_ID\|latest --source DIR [--path GLOB] [--dry-run] [--json]` | `0` when the journal exists (skipped items are listed), `1` when no journal or no runs exist |

### Per-file items

Runs with `--json` also include `items` (one entry per file decision) and `item_counts` (totals per action). `--report FILE` writes the same items as JSON Lines, one `{"type": "item", ...}` object per line followed by a `{"type": "summary", ...}` line with the run summary.

```json
{"path": "Movie.One/Movie.One.mkv", "folder": "Movie.One", "action": "moved",
 "reason_code": "video_ok", "detail": "14.0s", "bytes": 5321113,
 "destination": "/videos/Movie.One.mkv", "planned": false, "inferred": false}
```

| Field | Meaning |
|-------|---------|
| `path` | Path relative to the source directory |
| `folder` | Top-level folder under the source (empty for loose files) |
| `action` | `moved`, `deleted`, `extracted`, `kept`, `skipped` or `blocked` |
| `reason_code` | Why, for example `video_ok`, `video_too_short`, `video_truncated`, `sample_with_full_version`, `archive_extracted`, `archive_volume_missing`, `archive_password`, `junk_extension`, `par2_cleanup`, `download_incomplete`, `not_processed` |
| `detail` | Human-readable specifics (duration, missing volume names) |
| `bytes` | Size before the run |
| `destination` | Final path for moved videos |
| `planned` | `true` in `--dry-run` output |
| `disposal` | For live `deleted` items: `quarantine`, `trash` or `permanent` |
| `inferred` | `true` when the action was reconciled at the end of the run rather than recorded at the decision point (for example a junk file removed together with its folder) |

Every file present in the source when the run starts has exactly one item. Files created during the run (extracted videos) appear too, under their extracted path. A dry run on an unchanged tree reports the same actions as the following live run for every file present before the run: it runs the same read-only archive checks (missing volume, listing, password, unsafe contents) and plans folder cleanup the same way. The exceptions are live-only results: videos that fail validation, archives that fail their CRC check, and PAR2 repairs; extracted files only exist during the live run. `--show-plan --json` includes `plan`, a folder-level list (`process`, `keep`, `delete`, `validate_video`); per-file items come from `--dry-run --json`.

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

## `unpackr service`

| Command | `0` | `1` | `2` |
|---|---|---|---|
| `service install` | Units written and enabled | Not confirmed, or `systemctl` failed (files are reported) | No systemd user session or not Linux |
| `service status` | Shown (also with nothing installed) | Several services and no `--source`/`--name` | |
| `service uninstall` | Removed (each file is listed) | Nothing matched, or ambiguous | |

The service unit treats exit `3` (completed with items needing attention) as success, so `systemctl --user status` does not show a failed unit for a run that reported problems; they are in the notification, the journal and the log.
