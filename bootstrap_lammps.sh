#!/bin/bash
# LAMMPS pipeline environment bootstrap (Linux) - one-time setup.
# Creates .venv with pinned requirements.txt (numpy/matplotlib).
set -e
cd "$(dirname "$0")"

echo "============================================"
echo " Fe-Pt MD - LAMMPS pipeline bootstrap (Linux)"
echo "============================================"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || { echo "ERROR: python3 not found"; exit 1; }

# requirements.txt pins numpy==1.26.4 -> needs Python <= 3.12
"$PY" - <<'EOF' || { echo "ERROR: use Python 3.10-3.12 for the LAMMPS pipeline (set PYTHON=python3.12 ...)"; exit 1; }
import sys
assert sys.version_info < (3, 13), "need <=3.12"
EOF

if [ ! -x .venv/bin/python ]; then
    echo "[1/3] Creating virtualenv .venv ..."
    "$PY" -m venv .venv
fi

echo "[2/3] Installing requirements.txt ..."
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] Checking LAMMPS ..."
if command -v lmp >/dev/null 2>&1; then
    echo "  lmp found: $(command -v lmp)"
else
    sudo apt-get install -y lammps || \
      echo "  Install LAMMPS manually (apt install lammps / conda install -c conda-forge lammps)"
fi

echo
echo "Bootstrap complete. Run: bash run_lammps.sh"
