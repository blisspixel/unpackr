"""
Subcommands: ``unpackr runs`` and ``unpackr restore`` (previous runs) and
``unpackr service`` (unattended runs with a systemd user timer).

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

SUBCOMMANDS = ("runs", "restore", "service")


def _source(value: str) -> Path:
    path = Path(os.path.expanduser(value))
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"source directory not found: {value}")
    return path


def _existing_file(value: str) -> Path:
    path = Path(os.path.expanduser(value)).resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"config file not found: {value}")
    return path


def _destination(value: str) -> Path:
    path = Path(os.path.expanduser(value)).resolve()
    if not path.is_dir() and not path.parent.is_dir():
        raise argparse.ArgumentTypeError(f"destination does not exist and neither does its parent: {value}")
    return path


def _timespan(value: str) -> str:
    from utils.service import valid_timespan

    if not valid_timespan(value):
        raise argparse.ArgumentTypeError(f"not a time span: {value!r} (examples: 15m, 1h, 30min)")
    return value.strip()


def build_subcommand_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unpackr", description="Inspect or undo previous Unpackr runs, or manage the service."
    )
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

    service = sub.add_parser(
        "service",
        help="Run Unpackr unattended with a systemd user timer (Linux)",
        description="Install, inspect or remove a systemd user timer that runs `unpackr --unattended`.",
    )
    service_sub = service.add_subparsers(dest="action", required=True)
    install = service_sub.add_parser("install", help="Write and enable the units (asks first)")
    install.add_argument(
        "--source", "-s", required=True, type=lambda v: _source(v).resolve(), help="Downloads folder to clean"
    )
    install.add_argument("--destination", "-d", required=True, type=_destination, help="Where videos go")
    install.add_argument("--every", default="15m", type=_timespan, help="Time between runs (default: 15m)")
    install.add_argument("--on-change", action="store_true", help="Also run when the source folder changes")
    install.add_argument("--config", "-c", type=_existing_file, help="config.json to use for the runs")
    install.add_argument("--no-notify", action="store_true", help="Do not send desktop notifications")
    install.add_argument("--yes", "-y", action="store_true", help="Install without asking")
    for action in ("status", "uninstall"):
        cmd = service_sub.add_parser(
            action, help="Show installed services" if action == "status" else "Disable and delete"
        )
        cmd.add_argument(
            "--source", "-s", type=lambda v: Path(os.path.expanduser(v)).resolve(), help="Service for this source"
        )
        cmd.add_argument("--name", help="Service name, such as unpackr-1a2b3c4d")
        if action == "status":
            cmd.add_argument("--json", action="store_true", help="Print JSON")
        else:
            cmd.add_argument("--all", action="store_true", help="Remove every Unpackr service")
    return parser


def _human_mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


def run_subcommand(argv: List[str]) -> int:
    args = build_subcommand_parser().parse_args(argv)
    write = print

    if args.command == "service":
        from utils import service as svc

        if args.action == "install":
            plan = svc.build_plan(
                args.source,
                args.destination,
                every=args.every,
                on_change=args.on_change,
                config=args.config,
                notify=not args.no_notify,
            )
            return svc.install(plan, assume_yes=args.yes, write=write)
        if args.action == "status":
            return svc.status(args.source, args.name, as_json=args.json, write=write)
        return svc.uninstall(args.source, args.name, all_=args.all, write=write)

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
