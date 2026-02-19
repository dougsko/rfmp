#!/usr/bin/env bash
set -euo pipefail

# Quick start script for rfmp-daemon
# - creates a virtualenv if missing
# - installs/updates requirements
# - runs the daemon via `python -m rfmpd.main`

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

# Default venv directory (can be overridden by first arg or RFMP_VENV env var)
PYTHON_CMD="${PYTHON:-python3}"

# If the first argument is present and does NOT start with a dash, treat it as the
# venv directory. Otherwise use the RFMP_VENV env var or default to 'venv'.
if [ "${1:-}" ] && [[ "${1:0:1}" != "-" ]]; then
  VENV_DIR="$1"
  shift
else
  VENV_DIR="${RFMP_VENV:-venv}"
fi

echo "[rfmp-daemon] script dir: $script_dir"
echo "[rfmp-daemon] using venv: $VENV_DIR"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_CMD not found. Install Python 3 or set PYTHON environment variable." >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[rfmp-daemon] creating virtualenv in '$VENV_DIR'..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

VENV_PY="$script_dir/$VENV_DIR/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "ERROR: venv python not found at $VENV_PY" >&2
  exit 1
fi

echo "[rfmp-daemon] upgrading pip and installing requirements..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null
if [ -f "requirements.txt" ]; then
  "$VENV_PY" -m pip install -r requirements.txt
else
  echo "[rfmp-daemon] warning: requirements.txt not found in $script_dir"
fi

echo "[rfmp-daemon] starting daemon (foreground)..."
# Forward any remaining args to the daemon entrypoint
exec "$VENV_PY" -m rfmpd.main "$@"
