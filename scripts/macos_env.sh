#!/bin/bash
# Source this from the launch/setup scripts; never change the user's global shell.
CYNE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
CYNE_CACHE_DIR="${CYNE_CACHE_DIR:-$CYNE_ROOT/.cache}"
export HF_HOME="$CYNE_CACHE_DIR/huggingface"
export TORCH_HOME="$CYNE_CACHE_DIR/torch"
export XDG_CACHE_HOME="$CYNE_CACHE_DIR"
export YOLO_CONFIG_DIR="$CYNE_CACHE_DIR/ultralytics"
export MPLCONFIGDIR="$CYNE_CACHE_DIR/matplotlib"
export ANONYMIZED_TELEMETRY=False
export HF_HUB_DISABLE_XET=1
export PYTORCH_ENABLE_MPS_FALLBACK=1
mkdir -p "$HF_HOME" "$TORCH_HOME" "$YOLO_CONFIG_DIR" "$MPLCONFIGDIR"
