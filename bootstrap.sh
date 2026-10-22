#!/usr/bin/env bash
# Fe-Pt MD - interactive bootstrap (Linux/macOS).
# Finds python3 (3.10-3.14), creates .venv-mace, installs torch + deps.
set -u
cd "$(dirname "$0")"

echo "================================================================"
echo " Fe-Pt MD - Interactive bootstrap (Linux/macOS)"
echo "================================================================"
echo

PYEXE=""
[ -x ".venv-mace/bin/python" ] && PYEXE=".venv-mace/bin/python"

if [ -z "$PYEXE" ]; then
    for cand in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            if "$cand" -c 'import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,14) else 1)' 2>/dev/null; then
                PYEXE="$cand"
                break
            fi
        fi
    done
fi

if [ -z "$PYEXE" ]; then
    echo "  ERROR: python3.10-3.14 not found. Install it first."
    exit 1
fi
echo "[ok] Python: $PYEXE ($("$PYEXE" -V 2>&1))"

echo
echo "  [1] Full setup (venv + torch + deps)   (default)"
echo "  [2] Deps only (venv exists)"
echo "  [3] Check environment (no changes)"
read -r -p "  Enter 1/2/3 [1]: " choice
choice="${choice:-1}"

if [ "$choice" = "3" ]; then
    [ -x .venv-mace/bin/python ] || { echo "  no .venv-mace yet - run option 1"; exit 1; }
elif [ "$choice" = "1" ]; then
    if [ ! -x ".venv-mace/bin/python" ]; then
        "$PYEXE" -m venv .venv-mace || { echo "  venv failed"; exit 1; }
    fi
    .venv-mace/bin/python -m pip install -q --upgrade pip
    .venv-mace/bin/python -m pip install torch || echo "  torch install failed"
fi

if [ "$choice" != "3" ]; then
    .venv-mace/bin/python -m pip install -r requirements-mace.txt || {
        echo "  requirements failed"; exit 1; }
fi

echo
echo "==============================================================="
echo " Environment check"
echo "==============================================================="
.venv-mace/bin/python -c 'import sys; print("python  :", sys.version.split()[0])'
.venv-mace/bin/python -c 'import torch; print("torch   :", torch.__version__, "| cuda:", torch.cuda.is_available())' 2>/dev/null || echo "  torch   : NOT INSTALLED"
.venv-mace/bin/python -c 'import mace; print("mace    : ok")' 2>/dev/null || echo "  mace    : NOT INSTALLED"
echo "==============================================================="
echo " Next: ./run_gui.sh  (GUI at http://127.0.0.1:8321)"
echo "==============================================================="
