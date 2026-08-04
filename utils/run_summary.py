"""
Machine-readable run summaries for Unpackr CLI automation.

Emits a stable JSON contract for CI scripts and operators without changing
destructive-path policy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with timezone."""
    return datetime.now(timezone.utc).isoformat()


def build_unpackr_run_summary(
    *,
    status: str,
    exit_code: int,
    source: Optional[str] = None,
    destination: Optional[str] = None,
    dry_run: bool = False,
    cancelled: bool = False,
    stats: Optional[Mapping[str, int]] = None,
    errors: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    recommended_actions: Optional[list[str]] = None,
    version: str = "",
) -> Dict[str, Any]:
    """
    Build a structured unpackr run summary.

    Status values:
    - completed: finished without cancellation
    - cancelled: user interrupted after start
    - failed: blocked or aborted with non-zero exit
    - planned: --show-plan only
    """
    snapshot = dict(stats or {})
    issues = list(errors or [])
    warns = list(warnings or [])
    actions = list(recommended_actions or [])

    if cancelled and status == "completed":
        status = "cancelled"

    if exit_code != 0 and status == "completed":
        status = "failed"

    if not actions:
        if exit_code != 0:
            actions.append("Re-run with --dry-run and review the log file before a live run.")
        if cancelled:
            actions.append("Re-run the same source/destination to process remaining work.")
        if dry_run and exit_code == 0:
            actions.append("Run without --dry-run to execute the planned actions.")
        actions.append("Run `unpackr-doctor --json` and confirm status is ready before unattended live runs.")

    return {
        "timestamp_utc": utc_now_iso(),
        "tool": "unpackr",
        "version": version,
        "exit_code": exit_code,
        "status": status,
        "dry_run": dry_run,
        "cancelled": cancelled,
        "paths": {
            "source": source,
            "destination": destination,
        },
        "counts": {
            "folders_processed": int(snapshot.get("folders_processed", 0)),
            "folders_deleted": int(snapshot.get("folders_deleted", 0)),
            "videos_found": int(snapshot.get("videos_found", 0)),
            "videos_moved": int(snapshot.get("videos_moved", 0)),
            "videos_healthy": int(snapshot.get("videos_healthy", 0)),
            "videos_corrupt": int(snapshot.get("videos_corrupt", 0)),
            "videos_sample": int(snapshot.get("videos_sample", 0)),
            "rars_extracted": int(snapshot.get("rars_extracted", 0)),
            "par2s_repaired": int(snapshot.get("par2s_repaired", 0)),
            "junk_files_deleted": int(snapshot.get("junk_files_deleted", 0)),
            "safety_stops": int(snapshot.get("safety_stops", 0)),
        },
        "errors": issues,
        "warnings": warns,
        "recommended_actions": actions,
    }


def dumps_run_summary(summary: Mapping[str, Any]) -> str:
    """Serialize a run summary as compact, stable JSON text."""
    return json.dumps(summary, indent=2, sort_keys=True)
