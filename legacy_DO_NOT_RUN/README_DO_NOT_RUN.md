# ⚠️ DO NOT RUN — Legacy Scripts

This directory (`legacy_DO_NOT_RUN/`) contains **old development scripts** from earlier phases of the Fe-Pt MD project.

## WSL-only scripts → `wsl_old/`

The `wsl_old/` subdirectory contains scripts that:
- use hardcoded `/mnt/c/...` Linux/WSL paths
- run only from WSL (Windows Subsystem for Linux)
- use Linux shell commands (bash, python3, grep, etc.)
- are **not compatible with the final Windows runtime**

These scripts are kept for reference only. **Do not use them for production runs.**

## Short-protocol script

`run_all_short_protocol.py` — old Phase 2/3 pipeline (5k equilibration + 10k production).  
Replaced by Phase 4 long protocol (50k eq + 100k prod) in `scripts/run_phase4.py`.

## Final Windows Runtime

Only these entry points are supported:

| Script | Purpose |
|--------|---------|
| `bootstrap.bat` | One-click setup (Python, venv, LAMMPS) |
| `run_demo.bat` | Quick 2-point demo |
| `run_main.bat` | Full Phase 4 run (20 points) |

**No WSL is required.** The pipeline runs natively on Windows using `bin\lmp.exe`.
