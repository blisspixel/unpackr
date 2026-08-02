#!/usr/bin/env bash
# unpackr-doctor launcher for Linux/macOS source checkouts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$ROOT/doctor.py" "$@"
