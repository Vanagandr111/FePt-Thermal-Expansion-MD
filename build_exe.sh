#!/usr/bin/env bash
# Fe-Pt MD - GUI Linux builder (PyInstaller, one-file).
# Run from the repo root:  bash build_exe.sh
# Output: dist/FePt-GUI   (no extension on Linux; Windows builds keep
# dist/FePt-GUI.exe via build_exe.bat).
set -euo pipefail
cd "$(dirname "$0")"

echo "================================================================"
echo " Fe-Pt MD - GUI Linux builder (PyInstaller, one-file)"
echo " Output: dist/FePt-GUI"
echo "================================================================"

TOOLS=buildtools-venv
PY="${PYTHON:-python3}"

if [ ! -x "$TOOLS/bin/python" ]; then
    echo "  [1/3] Creating $TOOLS ..."
    if ! "$PY" -m venv "$TOOLS"; then
        echo "  ERROR: python3 -m venv failed (missing python3-venv /"
        echo "         ensurepip). Install your distro package, or use"
        echo "         the GUI's Python-link installer."
        exit 1
    fi
    "$TOOLS/bin/pip" install -q --upgrade pip
    "$TOOLS/bin/pip" install -q pyinstaller
else
    echo "  [1/3] $TOOLS exists"
fi

echo "  [2/3] Building dist/FePt-GUI (one-file; torch/mace excluded on"
echo "        purpose - the exe drives an external engine Python) ..."
"$TOOLS/bin/python" -m PyInstaller FePt-GUI.spec --noconfirm --clean

echo "  [3/3] done"
ls -la dist/FePt-GUI
