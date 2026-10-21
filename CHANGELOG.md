# Changelog — FePt Thermal Expansion (MACE pipeline)

## v1.8.0 (2026-10-21) — Web GUI + agent MCP + single-exe prep
- **Web GUI** (`gui/server.py`, stdlib only, no framework): run modes
  **MACE (GPU)** vs **LAMMPS (CPU)** in one switch; potential picker is
  indexed from `potentials/gpu/` (`.pt`/`.model` weights) and
  `potentials/cpu/` (EAM/MEAM) — both folders are the single source of
  truth, weights relocated there.
- **Dependencies tab**: torch/CUDA/GPU name, mace/ase/numpy presence,
  lmp lookup (folder `lammps/` → `bin/` → Program Files) with a
  **Download LAMMPS** button (official windows zip / linux tarball),
  **Download model** button (MACE-MP-0-medium from the registry),
  per-dependency pass/fail and remedies.
- **Run form**: composition slider, lattice grid (atom count shown),
  temperature points, eq/prod steps, live `a(T)`/CTE charts with all
  numbers, interactive console streaming the run log (SSE), and an
  **open results folder** button for the current run.
- **Agent control, visible in the browser**: shared server-side form +
  SSE `state` events — every MCP edit pulses the touched field and logs
  `[agent] comp <- 0.75`; runs started by the agent log `[AGENT]`.
  MCP server `gui/mcp_server.py` (stdio, 12 tools) registered as
  `fept_gui` in Hermes config.
- **Single-exe prep** (patent-friendly layout): frozen-aware paths —
  `potentials/`, `lammps/`, `libs/` live NEXT TO the exe, only our own
  code is bundled; engine runs through an external interpreter
  (`$FEPT_PYTHON` → `libs/venv` → sys.executable); deps probed in that
  interpreter via subprocess (torch never imported by the GUI);
  `FEPT_PROJECT_DIR` passed to the engine; `--port`/`FEPT_PORT`;
  console-less build guarded. Build: PyInstaller onefile ≈ 9-17 MB
  (`buildtools-venv`, excludes torch/mace/ase/scipy/pandas/matplotlib).
  **Blocked on this host**: Smart App Control (registry
  `VerifiedAndReputablePolicyState=2`) + unreachable MS reputation
  endpoints (`curl=000`) make ANY locally built exe hang inside
  `LoadLibrary(python312.dll copy)` — reproduces with one ctypes line;
  the installed original DLL loads instantly. Dev-mode launcher
  `run_gui.bat` works around it (signed python.exe).
- **Linux**: identical code path (`xdg-open`, official linux lmp
  tarball); `run_gui.sh` equivalent.

## v1.7.4 (2026-10-21)
- **Seed lattice constant: no more hidden hardcode.** `LC_TABLE` in
  `scripts/gen_structure.py` with printed provenance per run:
  pt = 4.0065 A (our MACE-MP-0 EOS fit, E(V) parabola),
  fe = 3.5647 A (our EOS fit, fcc),
  fept = 3.615 A (historical v1.5 seed, kept only for old-run
  comparability). Override per run: `--lc <A>`.
- **Lever D merged: Verlet-skin neighbour-list cache** (`--nl-skin`,
  default 1.0 A). Same pairs, same order as the matscipy builder
  (array_equal), verified by `scripts/test_nl_cache.py`; gate:
  56.0 -> 52.5 ms/step (256 atoms, RTX 3070 Ti), a(300K) shift +0.004%.
- **torch-2.6 weights_only fix**: `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`
  is now set inside `run_main_mace.py` — imports work in any shell
  (was UnpicklingError/hang wherever the variable was not preset).
- **Spawned workers get per-PID triton/inductor sub-caches** (Windows
  PermissionError on shared .cubin when 2 workers compile at once).
- `scripts/eos_pt.py`: `--model`, `--device`; no torch.compile on CPU
  (inductor wants MSVC cl.exe and buys nothing for an EOS scan).
- Gate A (max-autotune-no-cudagraphs): FAIL — 52.5 -> 52.0 ms/step is
  within noise and the bf16 reduction order shifts a(300K) by 0.022%
  (> 0.01% budget); reverted, default stays `compile=default`.
- **Potential survey (EOS Pt vs exp 3.92 A, CTE 300-1200K vs exp
  9.5e-6 /K)**: MACE-MP-0 stays best: CTE 98.3% of exp. MACE-MPA-0
  203%, MP-0b3 136%, MP-0b2 119% (all slightly worse on Pt position
  too). No replacement found in the foundation-model round; models
  kept in `potentials/` for reference (not shipped in the release).
- Speed story vs v1.7.1 baseline 94.2 ms/step: -> 55 (compile+bf16)
  -> 52.5 (skin cache) = x1.79.

## v1.7.3 (2026-10-19)
- LC_TABLE-based generator defaults + `--lc` documentation, release
  assets with weights.

## v1.7.2 (2026-10-18)
- Gate harness (before/after windows), phase micro-benchmark,
  torch.compile + bf16 speed mode, parallel workers.
