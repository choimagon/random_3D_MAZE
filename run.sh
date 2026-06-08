#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PYTHON="$SCRIPT_DIR/.conda_envs/mujoco-maze/bin/python"

if [[ -x "$ENV_PYTHON" ]]; then
  exec "$ENV_PYTHON" "$SCRIPT_DIR/run.py" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/run.py" "$@"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$SCRIPT_DIR/run.py" "$@"
fi

echo "Python was not found. Install Miniconda/Anaconda, then run this again." >&2
exit 1
