"""
Archive processing for Unpackr.
Handles RAR extraction and PAR2 repair operations.
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.config import ConfigSource
from core.junk_rules import dangerous_extensions
from core.remover import Remover
from core.safety_invariants import InvariantEnforcer
from utils.defensive import StateValidator
from utils.error_messages import log_error
from utils.filesystem_policy import containment_violation
from utils.safety import LoopSafety, ProcessTracker, SafetyLimits, SubprocessSafety
from utils.system_check import SystemCheck

_SPLIT_7Z = re.compile(r"^(?P<base>.+\.7z)\.(?P<num>\d{3})$", re.IGNORECASE)
_RAR_PART = re.compile(r"^(?P<base>.+)\.part(?P<num>\d+)\.rar$", re.IGNORECASE)
_RAR_OLD_VOLUME = re.compile(r"^(?P<base>.+)\.r(?P<num>\d{2})$", re.IGNORECASE)
_ZIP_VOLUME = re.compile(r"^(?P<base>.+)\.z(?P<num>\d{2})$", re.IGNORECASE)

# Outcomes that leave the archive volumes in place so the user can fix and retry.
HELD_STATUSES = ("held",)
# Held because the download itself is broken, not because of this machine (disk, timeout,
# missing 7-Zip). A manual run treats these sets as junk; an unattended run keeps them,
# since the rest of the download may still be on its way.
BROKEN_SET_REASONS = frozenset(
    {"archive_volume_missing", "archive_incomplete", "archive_unlistable", "archive_password"}
)


@dataclass
class ArchiveSet:
    """One logical archive: a single file or a numbered multi-volume set."""

    name: str
    kind: str
    volumes: list[Path] = field(default_factory=list[Path])
    first: Path | None = None
    missing: list[str] = field(default_factory=list[str])


@dataclass
class ArchiveOutcome:
    """What happened to one archive set during a run.

    status is "extracted", "held" (kept for the user to fix and retry),
    "blocked" (unsafe contents) or "failed" (damaged; treated as junk).
    """

    name: str
    status: str
    reason_code: str
    detail: str
    volumes: list[Path] = field(default_factory=list[Path])


def _volume_gaps(numbers: list[int], start: int) -> list[int]:
    if not numbers:
        return []
    present = set(numbers)
    return [n for n in range(start, max(numbers) + 1) if n not in present]


def find_archive_sets(folder: Path) -> list[ArchiveSet]:
    """Group the archive files in a folder into sets and report missing volumes.

    Recognizes plain ``.7z`` and ``.rar`` files, split 7z sets (``.7z.001``),
    RAR part sets (``.part01.rar``) and old-style RAR sets (``.rar`` + ``.r00``).
    Missing volumes are reported for gaps in the numbering and for a missing
    first volume; a missing final volume cannot be seen from names alone.
    """
    try:
        files = sorted(f for f in folder.iterdir() if f.is_file())
    except OSError:
        return []

    split_7z: dict[str, dict[int, Path]] = {}
    rar_parts: dict[str, dict[int, tuple[Path, int]]] = {}
    old_rar_volumes: dict[str, dict[int, Path]] = {}
    plain_rar: dict[str, Path] = {}
    zip_volumes: dict[str, dict[int, Path]] = {}
    zip_heads: dict[str, Path] = {}
    sets: list[ArchiveSet] = []

    for f in files:
        name = f.name
        lower = name.lower()
        m = _SPLIT_7Z.match(name)
        if m:
            split_7z.setdefault(m.group("base"), {})[int(m.group("num"))] = f
            continue
        m = _RAR_PART.match(name)
        if m:
            rar_parts.setdefault(m.group("base"), {})[int(m.group("num"))] = (f, len(m.group("num")))
            continue
        m = _RAR_OLD_VOLUME.match(name)
        if m:
            old_rar_volumes.setdefault(m.group("base"), {})[int(m.group("num"))] = f
            continue
        m = _ZIP_VOLUME.match(name)
        if m:
            zip_volumes.setdefault(m.group("base"), {})[int(m.group("num"))] = f
            continue
        if lower.endswith(".zip"):
            zip_heads[name[:-4]] = f
            continue
        if lower.endswith(".7z"):
            sets.append(ArchiveSet(name=name, kind="7z", volumes=[f], first=f))
        elif lower.endswith(".rar"):
            plain_rar[name[:-4]] = f

    for base, vols in split_7z.items():
        nums = sorted(vols)
        missing = [f"{base}.{n:03d}" for n in _volume_gaps(nums, 1)]
        sets.append(
            ArchiveSet(
                name=base,
                kind="7z-split",
                volumes=[vols[n] for n in nums],
                first=vols.get(1),
                missing=missing,
            )
        )

    for base, parts in rar_parts.items():
        nums = sorted(parts)
        width = parts[nums[0]][1]
        missing = [f"{base}.part{n:0{width}d}.rar" for n in _volume_gaps(nums, 1)]
        first = parts[1][0] if 1 in parts else None
        sets.append(
            ArchiveSet(
                name=f"{base}.rar",
                kind="rar-parts",
                volumes=[parts[n][0] for n in nums],
                first=first,
                missing=missing,
            )
        )

    for base, head in plain_rar.items():
        vols = old_rar_volumes.pop(base, {})
        nums = sorted(vols)
        missing = [f"{base}.r{n:02d}" for n in _volume_gaps(nums, 0)]
        sets.append(
            ArchiveSet(
                name=head.name,
                kind="rar" if not vols else "rar-volumes",
                volumes=[head] + [vols[n] for n in nums],
                first=head,
                missing=missing,
            )
        )

    # Spanned zip: data.z01, data.z02 ... with data.zip as the last volume (7-Zip opens the .zip).
    for base, head in zip_heads.items():
        vols = zip_volumes.pop(base, {})
        nums = sorted(vols)
        missing = [f"{base}.z{n:02d}" for n in _volume_gaps(nums, 1)]
        sets.append(
            ArchiveSet(
                name=head.name,
                kind="zip" if not vols else "zip-spanned",
                volumes=[vols[n] for n in nums] + [head],
                first=head,
                missing=missing,
            )
        )
    for base, vols in zip_volumes.items():
        nums = sorted(vols)
        missing = [f"{base}.z{n:02d}" for n in _volume_gaps(nums, 1)] + [f"{base}.zip"]
        sets.append(
            ArchiveSet(name=f"{base}.zip", kind="zip-spanned", volumes=[vols[n] for n in nums], missing=missing)
        )

    # .rNN volumes whose .rar head is missing
    for base, vols in old_rar_volumes.items():
        nums = sorted(vols)
        missing = [f"{base}.rar"] + [f"{base}.r{n:02d}" for n in _volume_gaps(nums, 0)]
        sets.append(
            ArchiveSet(name=f"{base}.rar", kind="rar-volumes", volumes=[vols[n] for n in nums], missing=missing)
        )

    return sorted(sets, key=lambda s: s.name.lower())


def classify_extract_failure(stdout: str, stderr: str, code: int, timeout: int) -> tuple[str, str, str]:
    """Map a failed 7z extraction to (status, reason_code, detail)."""
    text = f"{stdout}\n{stderr}".lower()
    if "timeout" in text:
        return "held", "archive_timeout", f"Operation timed out after {timeout}s"
    if "password" in text or "wrong password" in text:
        return "held", "archive_password", "Archive is password-protected"
    if any(k in text for k in ("missing volume", "unexpected end of archive", "unavailable data", "is not archive")):
        return "held", "archive_incomplete", "Archive is incomplete (a volume is missing or cut short)"
    if any(k in text for k in ("crc failed", "data error", "corrupt", "broken", "headers error")):
        return "failed", "archive_corrupt", "Archive data is damaged (CRC or data error)"
    if "cannot find" in text or "can not open" in text:
        return "held", "archive_unreadable", "Archive file not accessible"
    return "held", "archive_extract_failed", f"7z returned error code {code}"


_PAR2_VOLUME = re.compile(r"\.vol\d+[+-]\d+\.par2$", re.IGNORECASE)
# par2cmdline exit codes that say something about the data (1 repair possible,
# 2 repair not possible, 4 insufficient critical data, 5 repair failed); the
# others (3 bad arguments, 6 file I/O, 7 logic, 8 memory, ...) are tool errors.
_PAR2_DAMAGE_CODES = {1, 2, 4, 5}
_PAR2_FAILURE_TEXT = (
    "repair failed",
    "repair is not possible",
    "repair is impossible",
    "cannot repair",
    "could not repair",
    "damaged beyond repair",
    "insufficient",
)


@dataclass
class Par2Outcome:
    """What PAR2 said about a folder: verified, repaired, damaged, error, unavailable or none."""

    status: str
    reason_code: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status in ("verified", "repaired", "none")


def par2_set_name(filename: str) -> str:
    """The set a ``.par2`` file belongs to: ``Movie.vol03+04.par2`` -> ``movie``."""
    name = _PAR2_VOLUME.sub("", filename)
    if name.lower().endswith(".par2"):
        name = name[:-5]
    return name.lower()


def par2_set_heads(par2_files: list[Path]) -> list[Path]:
    """One file per PAR2 set to hand to par2: the index file, else the smallest recovery volume."""
    sets: dict[str, list[Path]] = {}
    for f in par2_files:
        sets.setdefault(par2_set_name(f.name), []).append(f)
    heads: list[Path] = []
    for files in sets.values():
        index = [f for f in files if not _PAR2_VOLUME.search(f.name)]
        if index:
            heads.append(sorted(index)[0])
        else:
            heads.append(min(files, key=lambda f: (f.stat().st_size if f.exists() else 0, f.name)))
    return sorted(heads)


def classify_par2_result(stdout: str, stderr: str, code: int, success: bool) -> tuple[str, str, str]:
    """Map one ``par2 r`` run to (status, reason_code, detail)."""
    text = f"{stdout}\n{stderr}".lower()
    if "timeout" in text and not success:
        return "error", "par2_tool_error", "par2 timed out"
    if code in _PAR2_DAMAGE_CODES or any(k in text for k in _PAR2_FAILURE_TEXT):
        return "damaged", "par2_damaged", f"damaged and PAR2 cannot repair it (par2 exit {code})"
    if not success or code != 0:
        return "error", "par2_tool_error", f"par2 failed (exit {code}); the data was not judged"
    if "repair complete" in text or "repaired successfully" in text:
        return "repaired", "par2_repaired", "repaired"
    return "verified", "par2_verified", "all files correct"


def is_archive_related(path: Path) -> bool:
    """True for archive volumes and PAR2 files, the only things the archive step may remove."""
    name = path.name
    lower = name.lower()
    return lower.endswith((".rar", ".7z", ".zip", ".par2")) or bool(
        _SPLIT_7Z.match(name) or _RAR_OLD_VOLUME.match(name) or _ZIP_VOLUME.match(name)
    )


class ArchiveProcessor:
    """Handles archive extraction and repair operations."""

    def __init__(
        self,
        config: ConfigSource | None = None,
        destination_root: Path | None = None,
        process_tracker: ProcessTracker | None = None,
    ) -> None:
        """Initialize the archive processor.

        Args:
            config: Configuration object
            destination_root: Root destination for safety invariants
            process_tracker: Object with 'active_process' attribute for cancellation support
        """
        self.config: ConfigSource = config or {}
        self.system_check = SystemCheck(config)
        self.process_tracker = process_tracker
        self.enforcer = None
        if destination_root:
            self.enforcer = InvariantEnforcer(destination_root, config)
        self.last_outcomes: list[ArchiveOutcome] = []
        self.last_par2 = Par2Outcome("none", "", "")
        self._last_path_check: str = "archive_unsafe_paths"
        # Remover (quarantine, trash or permanent delete); nothing is removed without one.
        self.remover: Remover | None = None

    def _reset_path_check(self) -> None:
        # A method (not an inline assignment) so the type checker does not pin
        # the attribute to this literal across the _validate_archive_paths call.
        self._last_path_check = "archive_unsafe_paths"

    @staticmethod
    def describe_missing(missing: list[str], limit: int = 3) -> str:
        shown = ", ".join(missing[:limit])
        more = len(missing) - limit
        return f"{shown} and {more} more" if more > 0 else shown

    def process_rar_files(
        self,
        folder: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> bool:
        """
        Extract RAR files in the given folder.

        Args:
            folder: Path to folder containing RAR files
            progress_callback: Optional callback(current, total, message)

        Returns:
            True if processing completed successfully, False otherwise
        """
        self.last_outcomes = []
        try:
            archive_sets = find_archive_sets(folder)
            if not archive_sets:
                return True  # No archive files to process

            # Safety: limit number of archive sets
            loop_limit = getattr(self.config, "archive_extraction_loop_limit", 100)
            loop_guard = LoopSafety(loop_limit, "Archive extraction loop")
            success_count = 0
            total_count = len(archive_sets)

            for idx, archive_set in enumerate(archive_sets, 1):
                if progress_callback:
                    progress_callback(idx, total_count, f"Extracting: {archive_set.name[:50]}")

                if not loop_guard.tick():
                    logging.error(f"Archive extraction loop safety triggered in {folder}")
                    break

                outcome = self._process_archive_set(archive_set, folder)
                self.last_outcomes.append(outcome)
                if outcome.status == "extracted":
                    success_count += 1
                    # Only a set that extracted cleanly is removed; anything else stays for review.
                    self._delete_volumes(outcome.volumes)

            if success_count == 0:
                logging.warning(f"All {total_count} archive extractions failed in {folder}")
                return False
            if success_count < total_count:
                logging.warning(f"Partial extraction: {success_count}/{total_count} archives succeeded in {folder}")
                return True
            logging.info(f"All {total_count} archives extracted successfully in {folder}")
            return True

        except Exception as e:
            log_error(
                what_failed="Archive processing failed",
                reason=str(e),
                action="Check folder permissions and disk space",
                location=folder,
            )
            return False

    def preflight_set(self, archive_set: ArchiveSet, folder: Path) -> ArchiveOutcome | None:
        """Read-only checks that decide whether a set can be extracted.

        Returns the outcome for a set that must not be extracted (missing volume,
        no 7-Zip, password, unreadable, unsafe or dangerous contents), or None
        when extraction can go ahead. Dry runs call this too, so the plan holds
        and blocks the same sets the live run will.
        """

        def outcome(status: str, code: str, detail: str) -> ArchiveOutcome:
            return ArchiveOutcome(archive_set.name, status, code, detail, list(archive_set.volumes))

        if archive_set.missing or archive_set.first is None:
            missing = self.describe_missing(archive_set.missing)
            if archive_set.kind == "7z-split":
                logging.warning(f"Incomplete 7z archive detected in {folder}: {archive_set.name} (missing {missing})")
            log_error(
                what_failed=f"Incomplete archive set: {archive_set.name}",
                reason=f"Missing volume(s): {missing}",
                action="Download the missing volume(s) and run again; the other volumes were kept",
                location=folder,
            )
            return outcome("held", "archive_volume_missing", f"missing {missing}")

        archive_file = archive_set.first
        sevenzip_cmd = self.system_check.get_tool_command("7z")
        if not sevenzip_cmd:
            logging.error("7-Zip executable unavailable or configured with an unsafe relative path")
            return outcome("held", "tool_missing", "7-Zip unavailable")

        # SECURITY: Check archive contents for path traversal before extraction
        self._reset_path_check()
        if self._validate_archive_paths(archive_file, folder, sevenzip_cmd):
            return None
        if self._last_path_check == "archive_password":
            log_error(
                what_failed=f"Could not open {archive_file.name}",
                reason="Archive is password-protected (encrypted headers)",
                action="Extract it yourself with the password; the volumes were kept",
                location=archive_file.parent,
            )
            return outcome("held", "archive_password", "Archive is password-protected")
        if self._last_path_check == "archive_unlistable":
            log_error(
                what_failed=f"Could not read {archive_file.name}",
                reason="7-Zip could not list the archive (a volume is missing, it is damaged, or it is password-protected)",
                action="Check the download is complete; the volumes were kept",
                location=archive_file.parent,
            )
            return outcome("held", "archive_unlistable", "7-Zip could not list the archive")
        if self._last_path_check == "archive_dangerous_member":
            log_error(
                what_failed=f"SECURITY: Blocked {archive_file.name}",
                reason="Archive contains an executable, script or shortcut",
                action="Treat the release as fake; do not extract or run anything from it",
                location=archive_file.parent,
            )
            return outcome("blocked", "archive_dangerous_member", "contains an executable, script or shortcut")
        log_error(
            what_failed=f"SECURITY: Blocked {archive_file.name}",
            reason="Archive contains unsafe paths (path traversal attempt)",
            action="Do not extract this archive - it may be malicious",
            location=archive_file.parent,
        )
        return outcome("blocked", "archive_unsafe_paths", "entries would extract outside the folder")

    def _process_archive_set(self, archive_set: ArchiveSet, folder: Path) -> ArchiveOutcome:
        """Extract one archive set and report what happened to it."""

        def outcome(status: str, code: str, detail: str) -> ArchiveOutcome:
            return ArchiveOutcome(archive_set.name, status, code, detail, list(archive_set.volumes))

        archive_file = archive_set.first or folder / archive_set.name
        try:
            held = self.preflight_set(archive_set, folder)
            if held is not None:
                return held
            sevenzip_cmd = self.system_check.get_tool_command("7z") or []

            start_time = time.time()
            try:
                file_size_bytes = sum(v.stat().st_size for v in archive_set.volumes)
            except OSError:
                file_size_bytes = 0
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Check disk space before extraction (archives typically expand 1.5-3x)
            required_space_mb = int(file_size_mb * 3)
            if not StateValidator.check_disk_space(folder, required_mb=required_space_mb):
                import shutil

                available = shutil.disk_usage(folder).free / (1024 * 1024)
                log_error(
                    what_failed=f"Cannot extract {archive_file.name}",
                    reason=f"Disk full (need {required_space_mb}MB, have {int(available)}MB)",
                    action="Free up space or skip this file",
                    location=folder,
                )
                return outcome("held", "disk_space_low", f"need {required_space_mb}MB")

            extraction_timeout = SafetyLimits.calculate_rar_timeout(file_size_bytes)
            if extraction_timeout > SafetyLimits.RAR_EXTRACTION_TIMEOUT:
                logging.info(f"Using extended timeout {extraction_timeout}s for large archive ({file_size_mb:.1f}MB)")

            success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
                sevenzip_cmd + ["x", str(archive_file), f"-o{folder}", "-aoa", "-p-", "-y"],
                timeout=extraction_timeout,
                cwd=folder,
                operation=f"Archive extraction: {archive_file.name}",
                use_temp_files=True,
                process_tracker=self.process_tracker,
            )
            elapsed = time.time() - start_time

            if success:
                speed_mbps = file_size_mb / elapsed if elapsed > 0 else 0
                logging.info(
                    f"Extracted {archive_file.name} ({file_size_mb:.1f}MB in {elapsed:.1f}s, {speed_mbps:.1f}MB/s)"
                )
                return outcome("extracted", "archive_extracted", f"{file_size_mb:.1f}MB in {elapsed:.1f}s")

            status, reason_code, reason = classify_extract_failure(stdout or "", stderr or "", code, extraction_timeout)
            log_error(
                what_failed=f"Failed to extract {archive_file.name}",
                reason=reason,
                action="Check if archive is complete, not password-protected, and not corrupted",
                location=archive_file.parent,
                details=stderr[:300] if stderr else None,
            )
            return outcome(status, reason_code, reason)

        except Exception as e:
            log_error(
                what_failed=f"Unexpected error extracting {archive_file.name}",
                reason=str(e),
                action="Check archive file is accessible and not locked by another process",
                location=archive_file.parent,
            )
            return outcome("held", "archive_extract_error", str(e)[:200])

    def _delete_volumes(self, volumes: list[Path]) -> None:
        """Remove the volumes of one set that extracted cleanly."""
        for volume in volumes:
            self._delete_path(volume, extraction_verified=True)

    def process_par2_files(self, folder: Path) -> bool:
        """Verify, and repair if needed, every PAR2 set in ``folder``.

        PAR2 never removes anything: a set it cannot verify (damaged, obfuscated
        beyond matching, tool error, par2 not installed) still goes on to
        extraction, where 7-Zip checks every file's CRC. The ``.par2`` files are
        removed later by :meth:`remove_par2_files`, once the content is out.

        Every file in the folder is offered to par2 (``*``, expanded by par2
        itself on every OS), so volumes renamed by an obfuscated post are matched
        and renamed back before extraction.

        Returns True when every set verified or was repaired (or there are none);
        :attr:`last_par2` says what happened.
        """
        self.last_par2 = Par2Outcome("none", "", "")
        try:
            par2_files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".par2")
        except OSError as e:
            self.last_par2 = Par2Outcome("error", "par2_tool_error", f"could not list folder: {e}")
            return False
        if not par2_files:
            return True

        par2_cmd = self.system_check.get_tool_command("par2")
        if not par2_cmd:
            logging.warning("par2 is not installed; 7-Zip's CRC check will be the only integrity check")
            self.last_par2 = Par2Outcome("unavailable", "par2_unavailable", "par2 not installed; not verified")
            return False

        results = [self._run_par2_set(main, par2_cmd, folder) for main in par2_set_heads(par2_files)]
        repaired = any(r.status == "repaired" for r in results)
        bad = [r for r in results if r.status not in ("verified", "repaired")]
        if bad:
            # Damage outranks a tool error: it is the one the user can act on (re-download).
            worst = next((r for r in bad if r.status == "damaged"), bad[0])
            self.last_par2 = worst
            return False
        self.last_par2 = Par2Outcome(
            "repaired" if repaired else "verified",
            "par2_repaired" if repaired else "par2_verified",
            f"{len(results)} PAR2 set(s)",
        )
        return True

    def _run_par2_set(self, main: Path, par2_cmd: list[str], folder: Path) -> Par2Outcome:
        """Run ``par2 r <main> *`` for one set and classify the result."""
        try:
            set_files = [f for f in folder.glob("*.par2") if par2_set_name(f.name) == par2_set_name(main.name)]
            set_bytes = sum(f.stat().st_size for f in set_files)
        except OSError:
            set_files, set_bytes = [main], 0
        par2_timeout = SafetyLimits.calculate_par2_timeout(set_bytes)
        logging.info(f"PAR2 verify/repair: {main.name} ({len(set_files)} files, {set_bytes / 1048576:.1f}MB)")

        start_time = time.time()
        success, stdout, stderr, code = SubprocessSafety.run_with_timeout(
            par2_cmd + ["r", main.name, "*"],
            timeout=par2_timeout,
            cwd=folder,
            operation=f"PAR2 repair: {main.name}",
            use_temp_files=True,  # PAR2 can output large amounts of data
            process_tracker=self.process_tracker,
        )
        elapsed = time.time() - start_time
        status, reason_code, detail = classify_par2_result(stdout or "", stderr or "", code, success)
        if status in ("verified", "repaired"):
            logging.info(f"PAR2 {status} {main.name} in {elapsed:.1f}s")
        else:
            log_error(
                what_failed=f"PAR2 could not verify {main.name}",
                reason=detail,
                action="Nothing was removed; extraction will still run and 7-Zip checks every file's CRC",
                location=folder,
                details=f"Exit code: {code}\nStdout: {(stdout or '')[-300:]}\nStderr: {(stderr or '')[:300]}",
            )
        return Par2Outcome(status, reason_code, f"{main.name}: {detail}")

    def remove_par2_files(self, folder: Path) -> None:
        """Remove a folder's ``.par2`` files once its content has been verified and extracted."""
        for file in sorted(folder.glob("*.par2")) + sorted(folder.glob("*.PAR2")):
            if file.is_file():
                self._delete_path(file, extraction_verified=True)

    def _delete_path(self, file: Path, extraction_verified: bool) -> None:
        """Remove one archive-related file through the run's Remover, with lock retries.

        ``extraction_verified`` must be True only when the set's content has been
        extracted (or, for ``.par2`` files, the content was verified and is out).
        Without a Remover nothing is removed: a library caller that forgot to set
        one must not fall back to a silent permanent unlink.
        """
        if not extraction_verified or not is_archive_related(file):
            logging.error(f"Refusing to remove {file}: its content has not been extracted and verified")
            return
        if self.enforcer:
            try:
                if not self.enforcer.enforce_delete(file, extraction_verified=extraction_verified):
                    return
            except Exception as e:
                logging.error(f"Safety check prevented deletion of {file}: {e}")
                return
        if self.remover is None:
            logging.error(f"Refusing to remove {file}: no remover configured for this run")
            return

        for attempt in range(3):
            try:
                self.remover.remove(file, "archive_cleanup")
                logging.info(f"Removed file: {file}")
                return
            except PermissionError:
                if attempt < 2:
                    logging.warning(f"File locked (attempt {attempt + 1}/3): {file}")
                    time.sleep(1)
                else:
                    logging.error(f"Could not {self.remover.mode} locked file {file} after 3 attempts")
            except Exception as e:
                logging.error(f"Failed to remove file {file}: {e}")
                return

    def _validate_archive_paths(self, archive_file: Path, target_folder: Path, sevenzip_cmd: list[str]) -> bool:
        """
        Validate all paths in archive to prevent path traversal attacks.

        SECURITY: Checks that all files in the archive would extract to within target_folder.
        Rejects archives containing:
        - Absolute paths (C:\\, /, etc.)
        - Parent directory references (../)
        - Symbolic links pointing outside target

        Args:
            archive_file: Archive file to validate
            target_folder: Intended extraction directory
            sevenzip_cmd: 7z command to use for listing

        Returns:
            True if archive is safe to extract, False if malicious paths detected
        """
        try:
            # SECURITY: Stream the full 7z listing line-by-line so we cannot miss
            # entries hidden in the middle of a multi-megabyte listing. The previous
            # implementation relied on a 64 KiB head/tail sample, which an attacker
            # could exploit by inflating the listing to hide an unsafe entry in the
            # truncated middle (see _read_bounded_text in utils/safety.py).
            target_folder_resolved = target_folder.resolve()
            unsafe: dict[str, str] = {}
            unsafe_password: dict[str, str] = {}
            dangerous = set(dangerous_extensions(self.config))

            def check_line(line: str) -> bool:
                # Skip blank/header/footer lines.
                stripped = line.strip()
                if "wrong password" in stripped.lower() or "encrypted archive" in stripped.lower():
                    unsafe_password["seen"] = "1"
                    return True
                if not stripped or "---" in line or "Date" in line or "Path" in line:
                    return True

                # 7z list format: Date Time Attr Size CompSize Path
                parts = line.split()
                if len(parts) < 6:
                    return True

                file_path = " ".join(parts[5:])
                if not file_path:
                    return True

                reason = containment_violation(file_path, target_folder_resolved)
                if reason:
                    unsafe["reason"] = reason
                    return False
                if Path(file_path.replace("\\", "/")).suffix.lower() in dangerous:
                    unsafe["reason"] = f"dangerous member {file_path}"
                    unsafe["dangerous"] = "1"
                    return False
                return True

            success, stderr_sample, code = SubprocessSafety.run_with_line_handler(
                sevenzip_cmd + ["l", "-p-", str(archive_file)],
                timeout=30,  # Listing should be fast
                line_handler=check_line,
                operation=f"Archive path validation: {archive_file.name}",
            )

            if unsafe:
                logging.error(f"SECURITY: Archive contains {unsafe['reason']}")
                if unsafe.get("dangerous"):
                    self._last_path_check = "archive_dangerous_member"
                return False

            if any(k in (stderr_sample or "").lower() for k in ("wrong password", "encrypted archive")):
                unsafe_password["seen"] = "1"
            if unsafe_password:
                logging.warning(f"{archive_file.name} is password-protected (encrypted headers) - not extracting")
                self._last_path_check = "archive_password"
                return False

            if not success or code != 0:
                logging.warning(f"Could not list archive contents for {archive_file.name} - not extracting")
                self._last_path_check = "archive_unlistable"
                return False

            # Every line in the full (untruncated) listing passed validation.
            return True

        except Exception as e:
            logging.error(f"Error validating archive paths for {archive_file.name}: {e}")
            self._last_path_check = "archive_unlistable"
            return False  # Fail closed on errors
