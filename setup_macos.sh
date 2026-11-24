#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/scripts/macos_env.sh"
cd "$CYNE_ROOT"
if [[ "$(uname -s)" != Darwin ]]; then
  echo "This setup script is for macOS." >&2; exit 1
fi
if [[ "$(uname -m)" != arm64 ]]; then
  echo "This dependency lock targets native Apple Silicon. Run from an arm64 terminal." >&2; exit 1
fi
command -v brew >/dev/null || { echo "Install Homebrew, then rerun setup." >&2; exit 1; }
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install python@3.11 ffmpeg cmake
CYNE_PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
"$CYNE_PYTHON" -m venv .venv
export CMAKE_BUILD_PARALLEL_LEVEL=2
export CMAKE_POLICY_VERSION_MINIMUM=3.5
if [[ -f requirements-macos.lock ]]; then
  .venv/bin/python -m pip install --no-cache-dir -r requirements-macos.lock
else
  .venv/bin/python -m pip install --no-cache-dir 'setuptools<81' wheel
  .venv/bin/python -m pip install --no-cache-dir -r requirements.txt -c constraints-macos.txt
fi
.venv/bin/python -m pip check
echo "Environment ready. Launch with ./run.command. Models download when requested."
