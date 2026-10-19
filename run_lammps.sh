#!/bin/bash
# LAMMPS pipeline entry point (Linux), one-click.
# First run bootstraps .venv automatically (bootstrap_lammps.sh).
#
#   bash run_lammps.sh                 # full pipeline (run_main.py)
#   PYTHON=python3.12 bash run_lammps.sh   # pin interpreter
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "  .venv not found - bootstrapping LAMMPS pipeline environment ..."
    bash bootstrap_lammps.sh
fi

if ! command -v lmp >/dev/null 2>&1 && [ ! -x bin/lmp ]; then
    echo "WARNING: LAMMPS (lmp) not found - install with: sudo apt-get install -y lammps" >&2
fi

exec .venv/bin/python -u scripts/run_main.py "$@"
