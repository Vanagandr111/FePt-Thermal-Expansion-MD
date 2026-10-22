# Molecular Dynamics Study of Thermal Expansion in Fe–Pt Alloys

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![LAMMPS](https://img.shields.io/badge/LAMMPS-2Aug2023-orange)](https://www.lammps.org/)
[![Release v1.8.0](https://img.shields.io/badge/release-v1.8.0-brightgreen)](https://github.com/Vanagandr111/FePt-Thermal-Expansion-MD/releases/tag/v1.8.0)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

This repository contains the complete pipeline for computing lattice parameters and
thermal expansion coefficients (CTE) of face-centred cubic (fcc) Fe–Pt binary alloys using
molecular dynamics (MD) simulations with LAMMPS. The project spans **30 independent MD
simulations** across the full composition range at six temperatures, with a long
equilibration and production protocol for converged results.

**Key output:** Lattice parameter $a(T)$ for $x_{\mathrm{Pt}} = 0.00$, $0.25$, $0.50$, $0.75$, $1.00$
at $T = 300$, $500$, $700$, $900$, $1100$, $1200$ K, with effective coefficient of thermal expansion (CTE)
for each composition.

---

## Web GUI (v1.8.0)

One window for the whole pipeline — mode switch, dependencies, run form,
live console, charts:

```bat
run_gui.bat            :: Windows (opens http://127.0.0.1:8321/)
./run_gui.sh           :: Linux
```
or `.venv-mace/Scripts/python.exe gui/server.py` / `python3 gui/server.py`.

- **Mode MACE (GPU) / LAMMPS (CPU)** — switching the mode re-points the
  potential picker: neural weights are indexed from `potentials/gpu/`
  (`.pt`, `.model`), classic EAM/MEAM files from `potentials/cpu/`.
- **Precision selector** — fp16 (default, recommended; Turing T4+ and
  newer), bf16 (Ampere+), fp32 (no autocast). The estimate follows the
  mode (memory x0.95/x1.0/x1.6, fp32 ~x1.7 slower); verified with real
  quick runs in every mode.
- **Machine profile tab** — live GPU/CPU/RAM gauges, calibration table,
  atom budget, one-click recalibration (calibration points are shared
  with the estimator and MCP).
- **Live MD frame log** — every thermo frame streams into the console in
  the LAMMPS-style table (Step, Time_ps, phase eq/prod, PotEng, KinEng,
  TotEng, Temp, Press, Volume, Latt.a; eV / bar / A^3 / ps) and the same
  rows go per point to `results.../md_comp_XX_TYY.log`; the header
  records x_Pt, T, atoms, grid, eq/prod steps, dt, thermo interval, seed,
  and closes every run with the client's `# === FINAL ===` stats block
  (total_steps_done, log_records, a_mean/std/min/max, drift,
  n_prod_points, runtime, mean_pressure_all_results_bar cross-referenced
  to all_results.csv, last_row_above note) in both console and file.
- **Dependencies tab** — torch/CUDA/GPU, mace/ase/numpy, `lmp` binary
  lookup, **Download LAMMPS** (official zip/tarball into `lammps/`) and
  the **on-demand model catalog**: all 18 ACEsuit foundation checkpoints
  (MP-0/0b/0b2/0b3, MPA-0, OMAT-0, MATPES, MH-0/1) with a filter box;
  already-downloaded files drop out of the list; weights are fetched by
  one click into `potentials/gpu/` (nothing heavy is stored in the repo).
- **Run form** — composition, lattice grid (atom count), temperatures,
  eq/prod steps; **console** streams the run log; charts show a(T) and
  CTE with every number; **open results folder** jumps to the current
  run's files.
- **Results tab** — scientific summary card (system, model, precision,
  seed, alpha fit/chordal, R2, segmental CTE 300-600/600-900/900-1200 K
  filled on ANY grid - the engine fits the canonical nodes, not just
  adjacent pairs), a(T)/alpha charts, open-folder and **Excel** buttons
  (`.xlsx` is written next to every CSV).
- **3D visualisation** — fcc supercell with rotation/zoom, drag atoms,
  composition colouring; **thermal motion mode** with a 100-1200 K
  slider (amplitude ~ sqrt(T)).
- **Agent control is visible**: the MCP server `gui/mcp_server.py`
  (registered as `fept_gui`, 12 tools) edits the same server-side form,
  and the browser pulses each touched field with an `[agent] ...` line.
- **Single-file exe** (`dist/FePt-GUI.exe`, ~9.2 MB) is built with
  PyInstaller keeping `potentials/`, `lammps/`, `libs/` OUTSIDE the
  binary (only our own code is bundled; torch/mace are deliberately
  excluded - the GUI drives an external engine Python, so the bundle
  stays small and clean). `build_exe.bat` builds it and smoke-tests the
  result on :8321; ready-made builds ship as the release asset
  [v1.8.0](https://github.com/Vanagandr111/FePt-Thermal-Expansion-MD/releases/tag/v1.8.0).
  On hosts with Smart App Control the local build may be held by the
  OS policy — use `run_gui.bat` in that case.  On start the exe POPS a
  visible browser window (cmd `start` -> `os.startfile` ->
  `webbrowser.open` fallback chain).

## Development — TDD

Long-term project: features land test-first.

```bat
.venv-mace\Scripts\python.exe -m pytest     :: Windows (fast, no GPU needed)
.venv-mace/bin/python -m pytest             :: Linux
```

- `tests/` — unit suite for the GUI core (browser pop-up chain, engine
  interpreter resolution incl. the frozen self-relaunch guard, shared
  form state + agent logging, potential indexing).  Runs in <1 s with
  NO torch/CUDA import; heavy integrations stay in
  `scripts/test_nl_cache.py` (run manually).
- Workflow: write the failing test in `tests/`, make it pass with the
  smallest change in `gui/server.py` / `scripts/`, keep the suite green
  (`pytest` before every commit).  `requirements-dev.txt` holds dev-only
  deps (pytest).

---

- Compute lattice parameter $a(T)$ for pure Pt at the fcc structure.
- Compute lattice parameter $a(T)$ for Fe–Pt alloys at four Pt concentrations.
- Determine the composition dependence $a(x_{\mathrm{Pt}})$ at fixed temperatures.
- Validate the thermal expansion protocol against the Pt reference CTE ($9.5 \times 10^{-6}$ K$^{-1}$).
- Ensure all results originate from raw MD output, not empirical fitting.

---

## Physical Background

Thermal expansion in solids arises from the **anharmonicity** of interatomic potentials.
In classical molecular dynamics, this is captured naturally in the **NPT ensemble** (constant
number of atoms, constant pressure, constant temperature). As the temperature increases,
the equilibrium interatomic spacing shifts outward because the potential energy surface is
steeper on the compressive side than on the expansive side.

In an NPT simulation, the box dimensions fluctuate around an equilibrium volume that
increases with temperature. The lattice parameter $a$ is extracted from the time-averaged
volume:

$$a = \left(\frac{4 V}{N_{\text{atoms}}}\right)^{1/3}$$

Pure Pt is used as a **benchmark system** because its CTE is well
known from experiment ($9.5 \times 10^{-6}$ K$^{-1}$, mean over 300–1200 K range from
Kirby, 1991 / Touloukian, NBS),
allowing us to validate the protocol before applying it to Fe–Pt alloys.

---

## Methodology

### Software

- **LAMMPS** (2 Aug 2023) — molecular dynamics engine
- **Python 3.10+** — pipeline orchestration, data analysis, plotting

### Simulation Protocol

| Parameter | Value |
|-----------|-------|
| Supercell | $4 \times 4 \times 4$ fcc (256 atoms) |
| Ensemble | `fix npt` (isotropic, $P = 0$ bar) |
| Equilibration | 50 000 steps |
| Production | 100 000 steps |
| Thermo output | Every 100 steps → 1002 data points per run |
| Averaging | Mean over all production thermo lines |
| Potential (alloy grid) | **MEAM** (Kim, Koo, Lee, 2006) — `PtFe.meam` |
| Potential (Pt benchmark) | **EAM u3** (Zhou _et al._) — `Pt_u3.eam` |

### Compositions and Temperatures

| $x_{\mathrm{Pt}}$ | Composition | Phase structure |
|-------------------|-------------|-----------------|
| 0.00 | Fe | fcc (metastable) |
| 0.25 | Fe$_3$Pt | L1$_2$ |
| 0.50 | FePt | L1$_0$ |
| 0.75 | FePt$_3$ | L1$_2$ |
| 1.00 | Pt | fcc |

| All six temperatures ($300$, $500$, $700$, $900$, $1100$, $1200$ K) are simulated for each composition,
|giving **30 independent MD runs**. The finer temperature grid (200 K spacing) provides better
|resolution for the thermal expansion curve.

### Potentials

- **MEAM** (Kim, Koo, Lee, 2006) — used for the full Fe–Pt composition grid. This potential
  includes explicit Fe–Pt cross-interactions (`Ec(1,2)=5.86`, `re(1,2)=2.7181`, `alpha(1,2)=5.97`,
  plus 9 `Cmin/Cmax` pairs for angular screening). It is **not** a linear interpolation of
  the pure-element EAM potentials.
- **EAM u3** (Zhou _et al._) — used only as a pure Pt benchmark for protocol validation.
  This potential is **not** used for Fe–Pt alloys.

---

## Pt Thermal Expansion Calibration

An earlier short protocol (10 000 eq + 50 000 prod) underestimated the Pt CTE significantly.
The **long protocol** (50 000 eq + 100 000 prod, tested here with a 256‑atom supercell) gives
much better agreement with experiment.

| Potential | Supercell | Protocol | CTE (300–1200 K) | Fraction of exp. ($9.5 \\times 10^{-6}$ K$^{-1}$) |
|-----------|-----------|----------|-------------------|----------------------------------------------|
| EAM u3 | 256‑atom | Short | $4.32 \\times 10^{-6}$ K$^{-1}$ | 45% |
| MEAM | 256‑atom | Short | $4.3 \\times 10^{-6}$ K$^{-1}$ | ~45% |
| **EAM u3** | **256‑atom** | **Long** | **$9.12 \\times 10^{-6}$ K$^{-1}$** | **96%** |
| **MEAM (this work)** | **256‑atom** | **Long (turbo)** | **$9.151 \\times 10^{-6}$ K$^{-1}$** | **96%** |

The MEAM potential with the long protocol achieves 96 % of the experimental Pt CTE, a
substantial improvement over the short protocol (45 %).

Full calibration details are available in:
- [`docs/PHYSICAL_VALIDATION.md`](docs/PHYSICAL_VALIDATION.md)

---

## Phase 4 Results — 256‑atom Supercell (Turbo)

All results were obtained with the **turbo** mode (50 000 eq + 100 000 prod) using a
$4\\times4\\times4$ fcc supercell (256 atoms), MEAM potential, OpenMP backend, and a
single seed (26365). Six temperatures per composition give **30 independent MD runs**.

### Lattice Parameters

| $x_{\\mathrm{Pt}}$ | Composition | $a_{300}$ (Å) | $a_{500}$ (Å) | $a_{700}$ (Å) | $a_{900}$ (Å) | $a_{1100}$ (Å) | $a_{1200}$ (Å) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.00 | Fe | 3.6270 | 3.6374 | 3.6476 | 3.6585 | 3.6690 | 3.6747 |
| 0.25 | Fe$_3$Pt | 3.7975 | 3.8066 | 3.8145 | 3.8214 | 3.8283 | 3.8316 |
| 0.50 | FePt | 3.8698 | 3.8760 | 3.8817 | 3.8874 | 3.8928 | 3.8952 |
| 0.75 | FePt$_3$ | 3.9059 | 3.9118 | 3.9176 | 3.9228 | 3.9279 | 3.9309 |
| 1.00 | Pt | 3.9290 | 3.9352 | 3.9421 | 3.9493 | 3.9577 | 3.9614 |

### Thermal Expansion (300–1200 K)

| $x_{\\mathrm{Pt}}$ | Composition | $\\Delta a$ (Å) | $\\alpha_{\\mathrm{eff}}$ (K$^{-1}$) |
|:---:|:---:|:---:|:---:|
| 0.00 | Fe | 0.0477 | $1.460 \\times 10^{-5}$ |
| 0.25 | Fe$_3$Pt | 0.0341 | $9.985 \\times 10^{-6}$ |
| 0.50 | FePt | 0.0254 | $7.289 \\times 10^{-6}$ |
| 0.75 | FePt$_3$ | 0.0250 | $7.117 \\times 10^{-6}$ |
| 1.00 | Pt | 0.0324 | $9.151 \\times 10^{-6}$ |

### Key Trends

1. **Lattice parameter** increases with both temperature and Pt content, consistent
   with Vegard-like behaviour and the larger atomic radius of Pt (1.39 Å vs Fe 1.26 Å).
2. **CTE minimum** occurs at $x_{\\mathrm{Pt}} = 0.75$ (FePt$_3$): $\\alpha \\approx
   7.117 \\times 10^{-6}$ K$^{-1}$.
3. **Pt CTE ($9.151 \\times 10^{-6}$ K$^{-1}$) reaches 96 % of the experimental reference
   ($9.5 \\times 10^{-6}$ K$^{-1}$)**, validating the long protocol for pure Pt.
4. **Pure Fe CTE** ($1.460 \\times 10^{-5}$ K$^{-1}$) is the highest, consistent with
   the weaker bonding in metastable fcc-Fe.
5. **Error bars** ($a_{\\mathrm{std}}$) range from 0.002–0.010 Å, confirming converged
   production trajectories.
6. **200 K temperature grid** (300–1200 K, 6 points) gives finer resolution of the
   $a(T)$ curve compared with the earlier 4-point protocol.

### Figures

Generated plots are in the output directory (seed 26365 in metadata):

| Output path | Description |
|-------------|-------------|
| `output_v4_256/a_vs_T_turbo_256at_omp.png` | Lattice parameter $a(T)$ for all five compositions with error bands |
| `output_v4_256/a_vs_T_turbo_256at_omp_facets.png` | Individual subplots per composition |
| `output_v4_256/a_vs_comp.png` | Isothermal cross-sections $a(x_{\\mathrm{Pt}})$ |
| `output_v4_256/all_results_turbo_256at_omp.csv` | Full results CSV (30 points) |
| `output_v4_256/integrity_check_v4_turbo.txt` | Cross-check of CSV vs raw logs |

---

## How to Run — Windows Pipeline

### Requirements

- **Windows 10/11**
- **Python 3.10 or newer** (uses `py` launcher or `python` automatically)
- A pre-compiled LAMMPS executable

> **No WSL is required.** The pipeline runs natively on Windows.
>
> **Active runtime is Windows-only.** WSL is not required and not supported for final runtime.
> Legacy WSL development scripts have been cleaned from the repository.

### Quick Start

1. **Clone the repository**

   ```cmd
   git clone <repo-url>
   cd FePt-Thermal-Expansion-MD
   ```

2. **Bootstrap the environment**

   Double-click `bootstrap.bat`, or run from Command Prompt:

   ```cmd
   bootstrap.bat
   ```

   Interactive bootstrap (Windows `bootstrap.bat` / Linux `bootstrap.sh`):
   - Finds a WORKING Python (3.10-3.14, skips the Microsoft Store alias)
   - Menu: [1] GPU install (torch cu128) / [2] CPU-only / [3] deps only /
     [4] environment check without changes
   - Creates `.venv-mace`, installs `requirements-mace.txt`
   - Prints a final report (python / torch / CUDA / mace / ase)

3. **Run the full calculation**

   ```cmd
   run.bat
   ```

   Interactive menu with 9 modes. See below for details.

### Run Modes

The project provides several calculation modes. The easiest way is to use `run.bat`
which presents an interactive menu for seed, resume/force, and mode selection.

| Mode | `.bat` file | Script | Protocol | Output dir | Purpose |
|------|------------|--------|----------|------------|---------|
| **0** DEMO | `run.bat [0]` | `run_mode.py --mode demo` | 50 eq + 100 prod, 2048at | `output_v4/` | Quick environment verification |
| **1** TURBO-FAST | `run.bat [1]` | `run_mode.py --mode turbo-fast` | 20k eq + 50k prod, 256at | `output_v4_256/` | Fast prototyping (⚠️ NOT final) |
| **2** TURBO 256at | `run.bat [2]` | `run_mode.py --mode turbo --natoms 256 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | Main 256‑atom result |
| **3** TURBO 2048at (OMP) | `run.bat [3]` | `run_mode.py --mode turbo --natoms 2048 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | 2048‑atom cross‑check |
| **4** TURBO 2048at (KOKKOS) | `run.bat [4]` | `run_mode.py --mode turbo --natoms 2048 --backend kokkos` | 50k eq + 100k prod, parallel | `output_v4_256/` | GPU‑accelerated |
| **5** LONG 256at | `run.bat [5]` | `run_mode.py --mode long --natoms 256 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | Full protocol (neigh 2.0) |
| **6** LONG 2048at (OMP) | `run.bat [6]` | `run_mode.py --mode long --natoms 2048 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | Full 2048‑atom |
| **7** LONG 2048at (KOKKOS) | `run.bat [7]` | `run_mode.py --mode long --natoms 2048 --backend kokkos` | 50k eq + 100k prod, parallel | `output_v4_256/` | Full 2048‑atom GPU |
| **8** TURBO-EXP | `run.bat [8]` | `run_mode.py --mode turbo-experimental` | 50k eq + 100k prod, OMP 4t, neigh/5 | `output_v4_256/` | Experimental tuning |

**For the final scientific result, use mode `2` (Turbo 256at).** The results in
`output_v4_256/` (seed 26365) are the principal 256‑atom dataset.

All modes support `--seed`, `--resume`, and `--force` flags. The interactive `run.bat`
handles seed configuration (auto / manual / re-use) and asks whether to resume or
recalculate when existing log files are found.

#### Direct script invocation

```cmd
REM TURBO 256at (recommended)
%%PYTHON%% scripts\run_mode.py --mode turbo --natoms 256 --backend omp [--seed N | --reuse-seed] [--resume | --force]

REM TURBO 2048at
%%PYTHON%% scripts\run_mode.py --mode turbo --natoms 2048 --backend omp [--seed N | --reuse-seed] [--resume | --force]

REM LONG 256at
%%PYTHON%% scripts\run_mode.py --mode long --natoms 256 --backend omp [--seed N | --reuse-seed] [--resume | --force]
```

### Seed Management

- **Auto (default):** a new random seed is generated for each run
- **Manual (`--seed 12345`):** specify a particular seed for reproducibility
- **Re-use (`--reuse-seed` or `--seed` without value):** uses the last seed from `seed.txt`
- On **resume (`--resume`)**, the seed from existing output is automatically re-used
- On **fresh run (`--force`)**, old logs and PNGs are deleted before starting

All output files include the seed number in their titles and metadata.

### Output Files

| Mode | Output directory | Key files |
|------|-----------------|-----------|
| DEMO (`run_mode.py --mode demo`) | `output_v4/` | `logs/`, `in/` (quick test only) |
| TURBO/LONG 256at | `output_v4_256/` | `all_results_turbo_256at_omp.csv`, `.xlsx`, `a_vs_T_turbo_256at_omp.png`, `a_vs_T_turbo_256at_omp_facets.png`, `a_vs_comp.png`, `integrity_check_v4_turbo.txt`, `cte_report.csv`, `seed_info.txt`, `run_protocol.txt` |

Raw LAMMPS log files are in `output_v4_256/logs/`. Each log file covers one
composition–temperature pair. LAMMPS input files are in `output_v4_256/in/`.
A `seed_info.txt` in the output directory records the seed and its source.

Raw LAMMPS log files are in `*/logs/`. A `seed_info.txt` in the output directory
records the seed and its source.

---

## MACE Neural Potential — Windows/Linux, CPU/GPU

### Which model for platinum (screened 2026-10-22)

Seven foundation models were screened on the identical protocol
(256 Pt atoms, 4x4x4 grid, NPT, fp16, seed 42, eq 500 + prod 1000
steps, sweep 300..1200 K; full 7-point run for the winner). The
experiment to beat: a(300K) = 3.924 A and alpha(300-1200K) =
9.5..9.8e-6 /K for Pt.

| Model | a(300K), A | a(1200K), A | alpha_fit, /K | deviation vs exp |
|---|---|---|---|---|
| **MACE-MPA-0 medium (winner)** | 3.99062 | 4.03021 | **1.136e-5** | +17% |
| MACE-MP-0b3 medium | 3.99312 | 4.03452 | ~1.15e-5 (chord) | +19% |
| MACE-MP-0 large (old default) | 3.99307 | 4.03800 | 1.261e-5 | +33% |
| MACE-OMAT-0 medium | 3.97555 | 4.02347 | ~1.34e-5 (chord) | +41% |
| MACE-MATPES-r2SCAN-0 medium | **3.94117** | 3.99156 | ~1.42e-5 (chord) | +49% (volume +0.4%, best lattice match) |
| MACE-MPA-0 (chord cross-check) | - | - | 1.102e-5 | consistent across protocols |
| MACE-MH-0 / MH-1 | - | - | - | multi-head models: the runner needs a head= keyword (not wired yet) |

MACE-MPA-0 full 7-point report (`results_mace_20261022_154637`):
fit alpha = 1.136e-5 /K, R2 = 0.9891, Da = 0.03960 A; facet segments
300-600K = 7.5e-6, 600-900K = 1.3e-5, 900-1200K = 1.3e-5 (monotonic
checkmark). The low-temperature segment is already within ~10% of the
experiment; the systematic PBE+U over-expansion concentrates above
600 K. r2SCAN models reproduce the lattice constant almost exactly
(+0.4%) but expand too fast - pick the trade-off per task. All
catalog URLs are HEAD-verified 200; models are fetched on demand
from the ACEsuit release pages (nothing is bundled with the repo).



Alternative runner that replaces classical MEAM/EAM with the `FePt_potential.pt`
neural network potential (MACE, ASE-MD). The LAMMPS pipeline above is untouched;
this runner is fully independent.

- `scripts/run_main_mace.py` — cross-platform NPT runner (no `cmd`/`.bat` code)
- `run_mace.bat` (Windows) / `scripts/run_main_mace.sh` (Linux/WSL) — launchers
- Python env: `.venv-mace` (created separately so the existing `.venv` used by
  the LAMMPS scripts stays untouched)
- Model lookup: `potentials/FePt_potential.pt` (already installed), `scripts/`,
  project root, or `--model <path>`

Device selection (works on both OSes):

```bat
run_mace.bat --quick                :: smoke test, CPU/GPU auto
run_mace.bat --device cuda          :: force GPU (falls back to CPU + warning)
run_mace.bat --device cpu           :: force CPU
run_mace.bat --eq 50000 --prod 100000 --grid 4 --device cuda --out output_mace_256
```

```bash
bash scripts/run_main_mace.sh --quick
bash scripts/run_main_mace.sh --device cuda --eq 50000 --prod 100000 --grid 4
```

`--grid 4` = 256-atom supercell (same size as the LAMMPS phase-4 runs);
`--grid 2` = 32 atoms for smoke tests. Default grid is 4 (32 in `--quick`).

**Precision modes** (`--precision fp16|bf16|fp32`, default `fp16`):
autocast around the MACE calculator; fp16 runs on Turing T4 and newer,
fp32 disables autocast entirely. All modes verified end-to-end (exit 0,
artifacts written, estimator adjusted per-mode).

**Foundation model catalog** — weights come from the official
[ACEsuit/mace-foundations](https://github.com/ACEsuit/mace-foundations)
releases (89 elements, DFT PBE+U datasets). The GUI lists all 18
checkpoints with one-click download into `potentials/gpu/`; locally we
keep only the models actually used. Licenses: MIT (MP family), ASL
(OMAT/MATPES/MH). MACE-OMOL (molecules, wB97M-V) is intentionally not
listed - wrong domain for metallic alloys.

Latest benchmark, pure Pt, MACE-MP-0-large.pt, fp16, 256 atoms, 7
temperatures (300-1200 K, 500 eq + 1000 prod steps, seed 42):

| $T$ (K) | 300 | 450 | 600 | 750 | 900 | 1050 | 1200 |
|---------|-----|-----|-----|-----|-----|------|------|
| $a$ (Å) | 3.99307 | 4.00106 | 4.00605 | 4.01593 | 4.02404 | 4.03043 | 4.03800 |

alpha_fit = 1.261e-5 /K (R^2 = 0.9967); segmental 300-600 K = 1.083e-5,
600-900 K = 1.497e-5, 900-1200 K = 1.156e-5. The ~25-35 % overshoot
vs experiment (9.5e-6 /K) is the usual systematic bias of an
UNFITTED PBE+U foundation model (a(300 K) is also ~2 % above the
experimental 3.924 A); foundation models are meant for relative
comparisons, fine-tuning closes the gap.

Verified 2026-10-19 on `FePt_potential.pt` (ScaleShiftMACE, r_max = 6 Å):

| Run | T = 300 K a (Å) | T = 1200 K a (Å) | CTE (1/K) |
|-----|-----------------|------------------|-----------|
| Windows (torch 2.9.1, CPU) | 3.851093 | 3.885100 | 9.8118e-06 |
| WSL Ubuntu (torch 2.14, CPU) | 3.851093 | 3.885100 | 9.8118e-06 |

Identical results on both OSes (seed = 42, quick protocol — smoke-test quality,
not publication numbers).

---

## Reproducibility and Data Integrity

- **Raw logs as source of truth:** All lattice parameters are extracted directly from
  LAMMPS thermo output. No manual fitting, scaling, or interpolation is applied.
- **Integrity check:** An automated cross-check verifies that every row in the CSV
  corresponds to a valid, completed LAMMPS log file. See
  `output_v4/integrity_check_v4.txt` or `output_v4_parallel/integrity_check_v4_turbo.txt`.
- **Seed tracking:** Every run records its seed. Re-running with `--reuse-seed` gives
  bit-identical results.
- **No Vegard-law fitting:** The composition dependence $a(x_{\mathrm{Pt}})$ is computed
  directly from MD trajectories, not from an empirical mixing rule.
- **Reference CTE:** The experimental Pt CTE is used only for validation — it does not
  enter the MD simulation or the data analysis pipeline.
- **Structures regenerated per run:** Each simulation starts from a freshly generated
  supercell (fixed seed 42 for structure generation) to avoid metastable traps from
  restarted data files.

---

## Limitations

1. **Classical potentials** — MEAM does not capture quantum effects, magnetic
   contributions, or electronic excitations that may influence thermal expansion.
2. **fcc-Fe metastability** — Iron is stable in the bcc phase at room temperature.
   The fcc structure studied here is appropriate for Fe–Pt alloys (which crystallise
   in fcc-derived ordered phases) but does not describe pure Fe in its ground state.
3. **MEAM accuracy** — The Kim–Koo–Lee (2006) potential was optimised for formation
   energies and melting temperatures, not specifically for the temperature-dependent
   lattice parameter.
4. **System size** — 256-atom supercells may exhibit finite-size effects. Larger
   supercells (8×8×8, 2048 atoms) are recommended for higher precision.
5. **Finite MD time** — Although the long protocol significantly improves convergence,
   the 100 000-step production run may not fully sample all anharmonic degrees of freedom
   at high temperatures.
6. **Single seed** — All runs currently use one seed per composition. Multiple independent
   seeds with ensemble averaging would reduce statistical noise.

---

## Future Work

- Larger supercells ($8 \times 8 \times 8$ or larger) for reduced finite-size effects.
- Multiple random seeds per composition for ensemble averaging.
- Nanoparticle and slab geometries for surface-related thermal expansion.
- Comparison with density functional theory (DFT) quasi-harmonic calculations.
- Alternative interatomic potentials (EAM, ML-IAP, second-nearest-neighbour MEAM).
- Experimental validation using published Fe–Pt thermal expansion data.

---

## File Structure

```
FePt-Thermal-Expansion-MD/
|── scripts/
│   ├── run_mode.py              ← Universal launcher (all modes)
│   ├── lmp_helper.py            ← Core LAMMPS helper (launcher, parser, plotting, CSV)
│   ├── seed_manager.py          ← Seed generation and persistence
│   ├── gen_structure.py         ← Supercell generator (fcc Fe-Pt)
│   ├── _run_one_point.py        ← Single-point run helper
│   ├── _test_single_run.py      ← Single-point test
│   ├── regenerate_plots.py      ← Regenerate plots from existing CSV/logs
│   ├── run_fe_only.py           ← Pure Fe runs
│   ├── run_pt_eam.py            ← Pt EAM benchmark runs
│   ├── test_kokkos.py           ← KOKKOS backend test
│   └── in.thermal_expansion     ← Production LAMMPS input template
├── data/
│   ├── *.lmp                      ← Generated supercell data files
│   └── data.fept_demo.lmp         ← Demo supercell
├── output_v4_256/                 ← ★ PRINCIPAL RESULTS (Turbo, 256‑atom, seed 26365)
│   ├── all_results_turbo_256at_omp.csv / .xlsx
│   ├── a_vs_T_turbo_256at_omp.png
│   ├── a_vs_T_turbo_256at_omp_facets.png
│   ├── a_vs_comp.png
│   ├── cte_report.csv
│   ├── integrity_check_v4_turbo.txt
│   ├── seed_info.txt
│   ├── run_protocol.txt
│   ├── in/                          ← LAMMPS input files
│   └── logs/                        ← Raw LAMMPS outputs (30 runs)
├── output_v4/                     ← Legacy 128‑atom Phase 4 results
├── output_v4_parallel/            ← Legacy 128‑atom Phase 4 Turbo results
├── output_v4_reduced/             ← Legacy
├── results/                       ← Legacy
├── potentials/
│   ├── PtFe.meam                  ← MEAM alloy potential
│   ├── library.meam               ← MEAM library file
│   ├── Fe_Zhou.eam.alloy          ← Fe EAM (Zhou _et al._)
│   ├── Pt_Zhou.eam.alloy          ← Pt EAM (Zhou _et al._)
│   ├── Pt_u3.eam                  ← Pt EAM benchmark
│   ├── Fe_mm.eam.fs               ← Fe EAM (Mendelev, 2007)
│   └── ...                        ← Additional EAM variants
├── docs/
│   ├── PHYSICAL_VALIDATION.md     ← Protocol validation details
│   └── REPORT.md                  ← MATLAB script status
├── bin/                            ← LAMMPS executable + DLLs + utilities
├── run.bat                        ← ★ INTERACTIVE LAUNCHER (auto-detects Python)
├── _run_lmp.bat                   ← LAMMPS wrapper (used by Python scripts)
├── gui/
│   ├── server.py                  ← GUI server + engine orchestration
│   ├── mcp_server.py              ← MCP tool layer for agents
│   └── static/                    ← Web UI (tabs: form/run/deps/results/profile)
├── potentials/
│   ├── gpu/                       ← MACE neural weights (.pt/.model, on-demand)
│   └── cpu/                       ← EAM/MEAM files for the LAMMPS pipeline
├── tests/                         ← pytest suite (fast, no GPU)
├── bootstrap.bat                  ← Interactive setup (Windows)
├── bootstrap.sh                   ← Interactive setup (Linux)
├── build_exe.bat                  ← PyInstaller build + smoke test
├── FePt-GUI.spec                  ← PyInstaller spec (one-file exe)
├── requirements.txt               ← Python dependencies
├── seed.txt                       ← Last used seed
├── .gitattributes
└── .gitignore
```

---

## License

This project is provided as-is for collaborative research use. See the [LICENSE](LICENSE)
file for details.
