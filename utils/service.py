"""
``unpackr service install|status|uninstall``: run Unpackr unattended with a systemd user timer.

Install writes a oneshot service and a timer (plus a ``.path`` unit with ``--on-change``)
under ``~/.config/systemd/user/``, shows them, and enables them only after confirmation.
A manifest under ``~/.config/unpackr/services/`` records every file written, so uninstall
removes exactly those files and reports them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 - fixed argument lists, no shell
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_TIMESPAN = re.compile(r"^\d+\s*(s|sec|m|min|h|hr|hour|hours|d|day|days)?$")
REPO_ROOT = Path(__file__).resolve().parent.parent

Runner = Callable[..., Any]


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def unit_dir() -> Path:
    return config_home() / "systemd" / "user"


def manifest_dir() -> Path:
    return config_home() / "unpackr" / "services"


def unit_name(source: Path) -> str:
    digest = hashlib.sha1(str(source).encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"unpackr-{digest}"


def valid_timespan(value: str) -> bool:
    return bool(_TIMESPAN.match(value.strip()))


def launcher() -> List[str]:
    """Absolute command that starts Unpackr outside this shell (no venv activation in systemd)."""
    beside_python = Path(sys.executable).parent / ("unpackr.exe" if sys.platform == "win32" else "unpackr")
    if beside_python.is_file():
        return [str(beside_python)]
    found = shutil.which("unpackr")
    if found:
        return [str(Path(found).resolve())]
    return [str(Path(sys.executable).resolve()), str(REPO_ROOT / "unpackr.py")]


def _quote(arg: str) -> str:
    """Quote one ExecStart argument for systemd (spaces, quotes, backslashes and % specifiers)."""
    arg = arg.replace("%", "%%")
    if re.search(r'[\s"\'\\]', arg):
        return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return arg


def _escape_path_setting(path: Path) -> str:
    # PathChanged= takes a single path; only % needs escaping, and spaces are allowed.
    return str(path).replace("%", "%%")


@dataclass
class ServicePlan:
    name: str
    source: Path
    destination: Path
    every: str
    on_change: bool
    command: List[str]
    units: Dict[str, str] = field(default_factory=dict)

    def unit_paths(self) -> Dict[str, Path]:
        return {filename: unit_dir() / filename for filename in self.units}

    def activations(self) -> List[str]:
        return [f for f in self.units if f.endswith((".timer", ".path"))]


def build_plan(
    source: Path,
    destination: Path,
    every: str = "15m",
    on_change: bool = False,
    config: Optional[Path] = None,
    notify: bool = True,
) -> ServicePlan:
    name = unit_name(source)
    command = launcher() + ["--unattended", "--source", str(source), "--destination", str(destination)]
    if config is not None:
        command += ["--config", str(config)]
    if notify:
        command.append("--notify")
    exec_start = " ".join(_quote(part) for part in command)

    units: Dict[str, str] = {}
    units[f"{name}.service"] = (
        "[Unit]\n"
        f"Description=Unpackr: clean up {source}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={exec_start}\n"
        "Nice=10\n"
        "IOSchedulingClass=idle\n"
        # Exit 3 means "finished, some items need attention"; it is reported, not a unit failure.
        "SuccessExitStatus=3\n"
    )
    units[f"{name}.timer"] = (
        "[Unit]\n"
        f"Description=Run Unpackr for {source} every {every}\n"
        "\n"
        "[Timer]\n"
        "OnActiveSec=1min\n"
        f"OnUnitInactiveSec={every}\n"
        f"Unit={name}.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    if on_change:
        units[f"{name}.path"] = (
            "[Unit]\n"
            f"Description=Run Unpackr when {source} changes\n"
            "\n"
            "[Path]\n"
            f"PathChanged={_escape_path_setting(source)}\n"
            f"Unit={name}.service\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
    return ServicePlan(name, source, destination, every, on_change, command, units)


def _systemctl(runner: Optional[Runner], *args: str) -> Any:
    run = runner or subprocess.run
    return run(["systemctl", "--user", *args], capture_output=True, text=True, check=False)  # nosec B603 B607


def systemd_available(runner: Optional[Runner] = None) -> Optional[str]:
    """None when a systemd user session is usable, otherwise the reason it is not."""
    if not sys.platform.startswith("linux"):
        return "service install supports Linux with a systemd user session; on other systems schedule `unpackr --unattended ...` with launchd or Task Scheduler"
    if not shutil.which("systemctl"):
        return "systemctl was not found; schedule `unpackr --unattended ...` with cron instead"
    try:
        result = _systemctl(runner, "is-system-running")
    except OSError as e:
        return f"systemctl --user failed: {e}"
    state = (result.stdout or "").strip()
    if state in ("", "offline") or "Failed to connect" in (result.stderr or ""):
        return "no systemd user session is reachable (try from a desktop login, or enable lingering with `loginctl enable-linger`)"
    return None


def _manifests() -> List[Dict[str, Any]]:
    found = []
    for path in sorted(manifest_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data["_manifest"] = str(path)
        found.append(data)
    return found


def install(
    plan: ServicePlan,
    assume_yes: bool = False,
    write: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
    interactive: Optional[bool] = None,
    runner: Optional[Runner] = None,
) -> int:
    reason = systemd_available(runner)
    if reason:
        write(f"Cannot install: {reason}.")
        return 2

    paths = plan.unit_paths()
    write(f"Unpackr service {plan.name}")
    write(f"  source:      {plan.source}")
    write(f"  destination: {plan.destination}")
    write(f"  runs:        every {plan.every}" + (" and when the source changes" if plan.on_change else ""))
    write("")
    for filename, text in plan.units.items():
        write(f"--- {paths[filename]}")
        write(text.rstrip())
        write("")

    existing = [p for p in paths.values() if p.exists()]
    if existing:
        write("These files already exist and will be replaced: " + ", ".join(str(p) for p in existing))

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not assume_yes:
        if not interactive:
            write("Not installed: confirmation needed. Re-run with --yes to install without a prompt.")
            return 1
        if ask("Install and enable these units? [y/N] ").strip().lower() not in ("y", "yes"):
            write("Not installed.")
            return 1

    unit_dir().mkdir(parents=True, exist_ok=True)
    for filename, text in plan.units.items():
        paths[filename].write_text(text, encoding="utf-8")
    manifest_dir().mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir() / f"{plan.name}.json"
    manifest.write_text(
        json.dumps(
            {
                "name": plan.name,
                "source": str(plan.source),
                "destination": str(plan.destination),
                "every": plan.every,
                "on_change": plan.on_change,
                "command": plan.command,
                "files": [str(p) for p in paths.values()],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    failures = []
    for args in (("daemon-reload",), ("enable", "--now", *plan.activations())):
        result = _systemctl(runner, *args)
        if result.returncode != 0:
            failures.append(f"systemctl --user {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    for path in [*paths.values(), manifest]:
        write(f"Wrote {path}")
    if failures:
        for failure in failures:
            write(f"Error: {failure}")
        write(
            f"The files are in place; fix the error and run `systemctl --user enable --now {' '.join(plan.activations())}`, or `unpackr service uninstall --source {plan.source}`."
        )
        return 1
    write(f"Enabled {', '.join(plan.activations())}. Logs: journalctl --user -u {plan.name}.service")
    return 0


def _select(
    source: Optional[Path], name: Optional[str], all_: bool, write: Callable[[str], None]
) -> Optional[List[Dict[str, Any]]]:
    manifests = _manifests()
    if all_:
        return manifests
    if name:
        chosen = [m for m in manifests if m.get("name") == name]
    elif source is not None:
        chosen = [m for m in manifests if m.get("source") == str(source)]
    elif len(manifests) == 1:
        chosen = manifests
    else:
        write("Several services are installed; pass --source, --name or --all.")
        for m in manifests:
            write(f"  {m.get('name')}  {m.get('source')}")
        return None
    return chosen


def status(
    source: Optional[Path] = None,
    name: Optional[str] = None,
    as_json: bool = False,
    write: Callable[[str], None] = print,
    runner: Optional[Runner] = None,
) -> int:
    chosen = _select(source, name, all_=source is None and name is None, write=write)
    if chosen is None:
        return 1
    rows = []
    for m in chosen:
        unit = m.get("name", "")
        row: Dict[str, Any] = {k: m.get(k) for k in ("name", "source", "destination", "every", "on_change", "files")}
        for activation in [f"{unit}.timer"] + ([f"{unit}.path"] if m.get("on_change") else []):
            enabled = _systemctl(runner, "is-enabled", activation).stdout.strip() or "unknown"
            active = _systemctl(runner, "is-active", activation).stdout.strip() or "unknown"
            row[activation] = {"enabled": enabled, "active": active}
        shown = _systemctl(
            runner, "show", f"{unit}.service", "-p", "Result", "-p", "ExecMainStatus", "-p", "ExecMainExitTimestamp"
        ).stdout
        props = dict(line.split("=", 1) for line in shown.splitlines() if "=" in line)
        row["last_run"] = {
            "finished": props.get("ExecMainExitTimestamp") or None,
            "exit_status": props.get("ExecMainStatus"),
            "result": props.get("Result"),
        }
        nxt = _systemctl(runner, "show", f"{unit}.timer", "-p", "NextElapseUSecRealtime").stdout
        row["next_run"] = (nxt.split("=", 1)[1].strip() if "=" in nxt else "") or None
        rows.append(row)

    if as_json:
        write(json.dumps({"services": rows}, indent=2))
        return 0
    if not rows:
        write(
            "No Unpackr services are installed. Add one with `unpackr service install --source DIR --destination DIR`."
        )
        return 0
    for row in rows:
        write(
            f"{row['name']}: {row['source']} -> {row['destination']} (every {row['every']}{', on change' if row['on_change'] else ''})"
        )
        for key, value in row.items():
            if key.endswith((".timer", ".path")):
                write(f"  {key}: {value['enabled']}, {value['active']}")
        last = row["last_run"]
        if last["finished"]:
            write(f"  last run: {last['finished']} (exit {last['exit_status']}, {last['result']})")
        else:
            write("  last run: not yet")
        if row["next_run"]:
            write(f"  next run: {row['next_run']}")
        write(f"  logs: journalctl --user -u {row['name']}.service")
    return 0


def uninstall(
    source: Optional[Path] = None,
    name: Optional[str] = None,
    all_: bool = False,
    write: Callable[[str], None] = print,
    runner: Optional[Runner] = None,
) -> int:
    chosen = _select(source, name, all_, write)
    if chosen is None:
        return 1
    if not chosen:
        write("No matching Unpackr service is installed.")
        return 1
    for m in chosen:
        unit = m.get("name", "")
        activations = [Path(f).name for f in m.get("files", []) if f.endswith((".timer", ".path"))]
        if activations and shutil.which("systemctl"):
            _systemctl(runner, "disable", "--now", *activations)
        if shutil.which("systemctl"):
            _systemctl(runner, "stop", f"{unit}.service")
        for file in [*m.get("files", []), m["_manifest"]]:
            path = Path(file)
            try:
                path.unlink()
                write(f"Removed {path}")
            except FileNotFoundError:
                write(f"Already gone: {path}")
            except OSError as e:
                write(f"Could not remove {path}: {e}")
    if shutil.which("systemctl"):
        _systemctl(runner, "daemon-reload")
    # Directories install created, only once empty (never the shared systemd/user folder).
    for folder in (manifest_dir(), manifest_dir().parent):
        try:
            folder.rmdir()
        except OSError:
            break
    return 0
