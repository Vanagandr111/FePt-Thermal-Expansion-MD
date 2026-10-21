#!/usr/bin/env bash
# FePt Web GUI — one-click launcher (Linux analog of run_gui.bat).
# Starts gui/server.py and prints the URL (browser opens automatically
# unless --no-browser is passed).
set -e
cd "$(dirname "$0")"

if [ -x .venv-mace/bin/python ]; then
    PY=.venv-mace/bin/python
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    echo "ERROR: python3 not found (project venv .venv-mace or system python3)."
    echo "Install python3 or run ./bootstrap_mace.sh first."
    exit 1
fi

echo "Using: $PY"
exec "$PY" -u gui/server.py "$@"
