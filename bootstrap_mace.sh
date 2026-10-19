#!/bin/bash
# Fe-Pt MD - MACE environment bootstrap (Linux/WSL), one-time setup.
# Creates .venv-mace, installs torch cu128 + requirements, checks LAMMPS.
set -e
cd "$(dirname "$0")"

echo "============================================"
echo " Fe-Pt MD - MACE environment bootstrap (Linux)"
echo "============================================"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || { echo "ERROR: python3 not found"; exit 1; }

if [ ! -x .venv-mace/bin/python ]; then
    echo "[1/4] Creating virtualenv .venv-mace ..."
    "$PY" -m venv .venv-mace
fi
VPY=.venv-mace/bin/python

echo "[2/4] Upgrading pip ..."
"$VPY" -m pip install -q --upgrade pip

echo "[3/4] Installing torch 2.11 cu128 (~2.8 GB, NVIDIA GPU) ..."
if ! "$VPY" -m pip install torch --index-url https://download.pytorch.org/whl/cu128; then
    echo "  WARNING: cu128 failed, falling back to default torch (CPU-only if no driver)"
    "$VPY" -m pip install torch
fi

echo "[4/4] Installing requirements-mace.txt ..."
"$VPY" -m pip install -r requirements-mace.txt

echo
echo "Checking LAMMPS ..."
if command -v lmp >/dev/null 2>&1; then
    echo "  lmp found: $(command -v lmp)"
else
    echo "  lmp not found - trying: sudo apt-get install -y lammps"
    sudo apt-get install -y lammps || \
      echo "  Could not install LAMMPS automatically. Install it manually"
      echo "  (apt install lammps / conda install -c conda-forge lammps)"
fi

echo
echo "Verifying ..."
"$VPY" -c "import torch, ase, mace; print('torch', torch.__version__, '| cuda:', torch.cuda.is_available())"
echo
echo "Bootstrap complete. Run: bash scripts/run_main_mace.sh"
