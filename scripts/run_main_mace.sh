#!/bin/bash
# Linux entry point for run_main_mace.py (main project Nikolay).
# Run from WSL (UbuntuFePt): the project lives on the Windows disk at /mnt/d.
#
#   bash scripts/run_main_mace.sh --quick                 # smoke test
#   bash scripts/run_main_mace.sh --device cuda           # GPU
#   bash scripts/run_main_mace.sh --device cpu            # CPU
#   bash scripts/run_main_mace.sh --eq 50000 --prod 100000 --grid 4
#
# Python autodetect: project venv -> /opt/fept -> python3
set -e
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
# One-click: no .venv-mace yet -> bootstrap it automatically
if [ ! -x "$PROJ/.venv-mace/bin/python" ] && [ -f "$PROJ/bootstrap_mace.sh" ]; then
  echo "  .venv-mace not found - bootstrapping environment (first run) ..."
  bash "$PROJ/bootstrap_mace.sh"
fi
PY=""
for cand in "$PROJ/.venv-mace/bin/python" /opt/fept/bin/python python3; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then echo "ERROR: python3 not found" >&2; exit 1; fi
echo "python: $PY"
exec "$PY" -u "$PROJ/scripts/run_main_mace.py" "$@"
