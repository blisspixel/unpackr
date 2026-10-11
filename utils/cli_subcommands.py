"""
Subcommands that operate on previous runs: ``unpackr runs`` and ``unpackr restore``.

They are dispatched before the main argument parser so the main command keeps
its positional ``source destination`` form.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

from core.remover import list_runs, restore_run

SUBCOMMANDS = ("runs", "restore")


def _source(value: str) -> Path:
    path = Path(os.path.expanduser(value))
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"source directory not found: {value}")
    return path


def build_subcommand_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unpackr", description="Inspect or undo previous Unpackr runs.")
    sub = parser.add_subparsers(dest="command", required=True)

    runs = sub.add_parser("runs", help="List recent runs with their actions and quarantined size")
    runs.add_argument("--source", "-s", required=True, type=_source, help="Source directory the runs processed")
    runs.add_argument("--json", action="store_true", help="Print JSON")

    restore = sub.add_parser(
        "restore",
        help="Put quarantined files back and move videos back from the destination",
        description=(
            "Restore one run. Quarantined files return to their original paths and moved videos return "
            "from the destination when they are unchanged. Files sent to the system trash or deleted "
            "permanently are listed but cannot be restored here."
        ),
    )
    restore.add_argument("run_id", help="Run id from `unpackr runs`, or 'latest'")
    restore.add_argument("--source", "-s", required=True, type=_source, help="Source directory the run processed")
    restore.add_argument("--path", help="Only restore paths matching this glob (for example '*Movie*')")
    restore.add_argument("--dry-run", action="store_true", help="Show what would be restored without moving files")
    restore.add_argument("--json", action="store_true", help="Print JSON")
    return parser


def _human_mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


def run_subcommand(argv: List[str]) -> int:
    args = build_subcommand_parser().parse_args(argv)
    write = print

    if args.command == "runs":
        infos = list_runs(args.source)
        if args.json:
            write(
                json.dumps(
                    [
                        {
                            "run_id": i.run_id,
                            "journal": str(i.journal),
                            "counts": i.counts,
                            "quarantine_files": i.quarantine_files,
                            "quarantine_bytes": i.quarantine_bytes,
                        }
                        for i in infos
                    ],
                    indent=2,
                )
            )
            return 0
        if not infos:
            write(f"No runs recorded in {args.source}")
            return 0
        for i in infos:
            counts = ", ".join(f"{k} {v}" for k, v in sorted(i.counts.items())) or "no actions"
            held = (
                f"{i.quarantine_files} files, {_human_mb(i.quarantine_bytes)} in quarantine"
                if i.quarantine_files
                else ""
            )
            write(f"{i.run_id}  {counts}" + (f"  ({held})" if held else ""))
        return 0

    run_id = args.run_id
    if run_id == "latest":
        infos = list_runs(args.source)
        if not infos:
            write(f"No runs recorded in {args.source}")
            return 1
        run_id = infos[0].run_id
    try:
        result = restore_run(args.source, run_id, path_glob=args.path, dry_run=args.dry_run)
    except FileNotFoundError as e:
        write(str(e))
        return 1

    if args.json:
        write(
            json.dumps(
                {"run_id": run_id, "dry_run": args.dry_run, "restored": result.restored, "skipped": result.skipped},
                indent=2,
            )
        )
    else:
        verb = "Would restore" if args.dry_run else "Restored"
        write(f"{verb} {len(result.restored)} item(s) from run {run_id}")
        for line in result.restored:
            write(f"  + {line}")
        if result.skipped:
            write(f"Skipped {len(result.skipped)}:")
            for line in result.skipped:
                write(f"  - {line}")
    return 0
