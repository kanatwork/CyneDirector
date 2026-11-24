#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/scripts/macos_env.sh"
cd "$CYNE_ROOT"
exec .venv/bin/python -m cyne_cli "$@"
