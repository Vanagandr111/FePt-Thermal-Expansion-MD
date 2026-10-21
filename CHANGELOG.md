# Changelog — FePt Thermal Expansion (MACE pipeline)

## v1.8.3 (2026-10-22) — memory audit (VRAM/RAM) + allocator hygiene
- **Audit of the 6 memory suspects (run_main_mace.py):**
  1. model weights were ALREADY frozen (0/31 with requires_grad) — MACE
     freezes on load; a `[audit] model weights ... requires_grad=0` line
     now proves it every run;
  2. autograd flags clean: inference uses create_graph=False; the only
     create_graph=True is dielectric-only (not our model);
  3. no detached-tensor leaks: records are plain float tuples, MACE
     keeps no GPU batches in self (grep-checked);
  4. compute_stress is unconditionally True in MACE — but the NPT
     barostat needs stress EVERY step, so only the BFGS relax would
     benefit (<1% of steps) → deliberately NOT forked;
  5. allocator: PYTORCH_CUDA_ALLOC_CONF extended to
     `expandable_segments:True,garbage_collection_threshold:0.8`
     (live-verified on cu128/WDDM; max_split_size_mb:128 documented as
     the fallback), reserved peak 1468→1442 MB (-26 MB);
  6. history is compact (tens of float tuples, no atoms.copy()).
  Plus: ONE gc.collect()+empty_cache()+reset_peak pass before the heavy
  loop (main AND worker paths), never inside the step loop.
- **[mem] telemetry**: per-point `alloc/reserved/MB + rss` lines
  (psutil primary, ctypes fallback), peak reset before the loop;
  added psutil to requirements-mace.
- Control run protocol (256 atoms, 300K, seed=42, eq2000/prod5000):
  BEFORE a=3.85163 A / 54.2 ms/step / alloc 1358 / reserved 1468 MB;
  AFTER a=3.85218 A / 54.4 ms/step / alloc 1360 / reserved 1442 MB /
  RSS 1841 MB. a-delta 0.0143% — above the 0.01% gate; ms/step within
  noise. See audit notes: allocator layout shifts perturb atomic
  reductions -> different BFGS branch (relax 200s vs 1200s), candidate
  for an isolated revert A/B of garbage_collection_threshold.
- **Found (outside the memory scope): BFGS relax runs on a broken
  BLAS** — after the first torch op in-process, numpy eigh degrades
  1.6s→64s (OMP runtime clash), so the 100-step relax costs 7-50 min
  instead of ~3 min. Isolated repro in a 4-line script; fix candidates
  (OPENBLAS_NUM_THREADS=1 / warm-up ordering) need their own A/B —
  NOT applied here.

## v1.8.2 (2026-10-22) — editable element system + potential hints
- **System = two editable elements** (generalization step 1): the GUI
  card "Система — элементы сплава" lists A/B from `data/elements.json`
  with per-element ⚙ edit / 🗑 delete / ＋ add; both open a MODAL form
  (symbol / label / seed lattice a) with inline hints and validation
  messages.  Server: `GET/POST /api/elements`, module `gui/elements.py`
  (CRUD + validation + atomic save), form fields `elem_a`/`elem_b`
  (MCP-visible).
- **Potential compatibility hints**: `GET /api/elements/compat` reads a
  potential file and reports whether it contains the chosen elements —
  parser understands EAM setfl/alloy headers ("16 Cu Ag ..."), old EAM
  blocks ("1 Fe"), Z-headers ("78 195.09 FCC"), MEAM library lines
  ("'Pt' 'fcc'"), MEAM alloy comments ("# Element 1 = Fe"), and treats
  MACE weights as universal; the UI shows ✓/⚠ pills and refreshes on
  mode/model/system change; project-escape guard on the file param.
- **Broken downloads cleanup**: removed six potentials that were
  actually "404: Not Found" pages saved as .eam.alloy (Fe_Zhou,
  Pt_Zhou, Pt_Zhou04*); remaining set verified byte-wise.
- TDD: +22 unit tests (39 total, <0.2 s).

## v1.8.1 (2026-10-22) — visible browser pop, TDD harness, tree cleanup
- **Browser pop is now assertive**: `browser_open_chain()` tries
  `cmd /c start` (fresh focused window) -> `os.startfile` ->
  `webbrowser.open` on Windows, `xdg-open` on Linux; every primitive is
  injectable so the chain is unit-tested.
- **Frozen self-relaunch guard narrowed to FROZEN** (regression caught
  while writing tests: the guard must NOT refuse `sys.executable` in dev
  mode, where it IS the engine python).
- **TDD harness**: `tests/` pytest suite (17 fast unit tests: browser
  chain, engine interpreter resolution + frozen guard, shared form
  state/agent logging, potential indexing) — no torch import, <1 s;
  `pytest.ini`, `requirements-dev.txt`; heavy integration test stays in
  `scripts/test_nl_cache.py`.
- **Tree cleanup** (~1 GB removed, all in git history / GitHub
  releases): hello-world exe debug artifacts, superseded release
  archives, old `output_*` run folders and backups, dead phase-4
  pipeline scripts (`run_phase4*`, `rebuild_phase4`, `phases_bench`,
  `run_fe_only`, `run_pt_eam`, `phase4_analysis.m`, old `.lmp` test
  files, `lmp_helper.py.bak_*`), May `bootstrap.bat` + its `.venv`,
  old `results/`.  Kept: working pipeline (`run.bat`+`run_mode.py`),
  MACE bootstraps, release tooling, docs, `bin/lmp.exe`, potentials.

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
- **Frozen-run bugfixes** (found by running the exe): deps probe no
  longer relaunches the exe itself (was an infinite hang — now returns a
  clear message), engine interpreter candidates extended
  (`libs/venv` -> `.venv-mace`/`venv`), `FEPT_PROJECT_DIR` pinned for
  frozen so `lmp_helper` finds `lammps/` NEXT TO the exe, run start
  errors cleanly when no engine python exists. Verified end-to-end:
  exe on port 8321 lists potentials, reports CUDA/lmp, and completes a
  mini MACE run (108 atoms, exit 0, 237 s).
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
