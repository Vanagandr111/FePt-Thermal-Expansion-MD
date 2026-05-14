#!/usr/bin/env python
"""check_shebangs.py - Check all scripts shebangs are Windows-compatible (python, not python3)."""
import os, sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT, "scripts")
found = []

for fname in sorted(os.listdir(SCRIPTS_DIR)):
    if not fname.endswith('.py'):
        continue
    fpath = os.path.join(SCRIPTS_DIR, fname)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            first = f.readline().strip()
    except Exception:
        continue
    if 'python3' in first:
        found.append(fname)

if found:
    print("!! WSL-style python3 shebangs found:")
    for f in found:
        print(f"  {f}")
    sys.exit(1)
else:
    print("  All shebangs use 'python' (not 'python3') OK")
    sys.exit(0)
