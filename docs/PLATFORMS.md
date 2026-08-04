# Platform Support

Unpackr targets **Windows, Linux, and macOS** with the same safety contract.

Cross-platform policy helpers:

- `utils/platform_support.py` — tools, processes, force-delete
- `utils/filesystem_policy.py` — path containment, case collisions, symlink farms, Unicode

## Install External Tools

### Windows

- Required: [7-Zip](https://www.7-zip.org/) (`7z` on PATH or absolute path in config)
- Recommended: [par2cmdline](https://github.com/Parchive/par2cmdline), [ffmpeg](https://ffmpeg.org/)

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install p7zip-full par2 ffmpeg
```

### Fedora / RHEL

```bash
sudo dnf install p7zip par2cmdline ffmpeg
```

### macOS (Homebrew)

```bash
brew install p7zip par2 ffmpeg
```

Then install Unpackr:

```bash
python -m pip install .
unpackr-doctor
```

## Launchers

After `python -m pip install .`, console scripts are available on every OS:

- `unpackr`
- `unpackr-doctor`
- `vhealth`

From a source checkout:

| OS | Launchers |
|----|-----------|
| Windows | `unpackr.bat`, `vhealth.bat` |
| Linux / macOS | `./unpackr.sh`, `./unpackr-doctor.sh`, `./vhealth.sh` |

```bash
chmod +x unpackr.sh unpackr-doctor.sh vhealth.sh
```

## Filesystem Quirk Matrix

| Quirk | Policy | Notes |
|-------|--------|-------|
| Case-insensitive volume (NTFS default, many SMB shares, APFS default) | Warn via doctor probe; preserve exact names; log collisions when names differ only by case | Linux ext4 is usually case-sensitive and will keep both `A.mkv` and `a.mkv` |
| Case-sensitive volume (typical Linux, APFS case-sensitive) | Exact-name operations; still sanitize Windows-hostile characters for portability | Prefer unique basenames if files may later land on Windows/NAS |
| Symlink / junction / reparse point | **Fail closed** on destructive cleanup and force-delete | Never follow linklike trees when deleting |
| Symlink farm inside a folder | Tree treated as unsafe for force-delete | Protects against delete-outside-root accidents |
| Non-ASCII names (Unicode, CJK, Cyrillic) | Supported for discovery; sanitization transliterates for portable outputs | macOS often stores NFD; Linux often NFC — NFC normalization is used in policy helpers |
| Control characters / null bytes in paths | Rejected | Config `log_folder` and archive members included |
| Absolute / `..` / drive-letter archive members | Rejected before extract | Windows-style `\` members are normalized on POSIX too |
| Long paths | Filenames sanitized with length headroom | Prefer short destination roots on Windows |
| Network mounts (SMB/NFS) | Supported with reduced performance and stricter permission surprises | Run `--dry-run` first; avoid deleting across mount points via symlinks |
| Bind mounts / ZFS datasets | Treated as ordinary paths unless linklike | Confirm free space on the actual dataset |

`unpackr-doctor` now prints a filesystem probe (`case_sensitive`, `symlinks`, `non_ascii`) for the working directory.

## Multi-User NAS And Permissions

Recommended layout:

```text
/data/incoming   # source downloads (group-writable)
/data/library    # destination library (group-writable)
/var/log/unpackr # optional logs when log_folder is absolute
```

Guidance:

1. Run Unpackr as a dedicated service account with rights only to source + destination + log folder.
2. Prefer group-writable directories (`2775` on POSIX with setgid bit) so multiple operators share outputs without world-writable trees.
3. Do not run as root unless required by mount policy; root can bypass permission failures that mask misconfiguration.
4. On Windows shares, grant Modify on the share and NTFS ACLs for the service account only.
5. Keep source and destination on the same volume when possible so moves stay atomic; cross-volume moves fall back to copy+delete.
6. If antivirus or indexer locks files, allowlist the service account and destination path rather than weakening safety retries.

## SELinux / AppArmor Notes

These only apply when confinement frameworks are enforcing.

### SELinux (RHEL/Fedora/CentOS)

Symptoms:

- `Permission denied` despite correct DAC permissions
- Doctor write probe fails under a service unit but succeeds interactively

Checks:

```bash
getenforce
ls -Z /data/incoming /data/library
ausearch -m avc -ts recent | tail
```

Remediation patterns:

- Label content directories appropriately for the service domain, or run the unit in an unconfined domain only if policy owners accept the risk.
- Prefer proper `semanage fcontext` + `restorecon` over broad `chmod 777`.
- Capture AVCs before requesting a local policy module; do not disable SELinux for production media hosts.

### AppArmor (Ubuntu/Debian)

Symptoms:

- Denied open/create under `/data/...` for a confined profile
- Subprocess helper (`7z`, `ffmpeg`) blocked from reading source archives

Checks:

```bash
sudo aa-status
sudo journalctl -k | grep -i apparmor | tail
```

Remediation patterns:

- Extend the profile to allow read on source, write on destination, execute for `7z`/`par2`/`ffmpeg`.
- Prefer profile updates over putting the binary in complain mode permanently.

## Performance Evidence

Before any concurrency or throughput change, capture a micro-benchmark report:

```bash
python scripts/benchmark_harness.py -o benchmarks/baseline-$(python -c "import platform;print(platform.system().lower())").json
```

The report includes hardware profile, filesystem probe, sequential/random read rates, and CPU score. Attach before/after JSON in PRs that claim performance gains.

See [BENCHMARKS.md](BENCHMARKS.md).

## CI Expectations

- Windows: full regression suite + coverage gate
- Linux: full regression suite + coverage gate on 3.11 + real-tool checks (`p7zip`/`par2`/`ffmpeg`)
- macOS: expanded platform/safety/doctor/archive suite + optional real-tool checks
