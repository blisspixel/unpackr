#!/usr/bin/env bash
# unpackr-doctor launcher for Linux/macOS source checkouts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m unpackr.doctor "$@"
