#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/scripts/macos_env.sh"
cd "$CYNE_ROOT"
[[ -x .venv/bin/python ]] || { echo "Run ./setup_macos.sh first." >&2; exit 1; }
exec .venv/bin/python main.py "$@"
