# Molecular Dynamics Study of Thermal Expansion in Fe–Pt Alloys

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![LAMMPS](https://img.shields.io/badge/LAMMPS-2Aug2023-orange)](https://www.lammps.org/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

This repository contains the complete pipeline for computing lattice parameters and
thermal expansion coefficients (CTE) of face-centred cubic (fcc) Fe–Pt binary alloys using
molecular dynamics (MD) simulations with LAMMPS. The project spans **20 independent MD
simulations** across the full composition range at four temperatures, with a long
equilibration and production protocol for converged results.

**Key output:** Lattice parameter $a(T)$ for $x_{\mathrm{Pt}} = 0.00$, $0.25$, $0.50$, $0.75$, $1.00$
at $T = 300$, $600$, $900$, $1200$ K, with effective coefficient of thermal expansion (CTE)
for each composition.

---

## Research Goals

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

All four temperatures ($300$, $600$, $900$, $1200$ K) are simulated for each composition,
giving **20 independent MD runs**.

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
The **long protocol** (50 000 eq + 100 000 prod) brings the computed CTE much closer to the
experimental reference.

| Potential | Protocol | CTE (300–1200 K) | Fraction of exp. ($9.5 \times 10^{-6}$ K$^{-1}$) |
|-----------|----------|-------------------|----------------------------------------------|
| EAM u3 | Short | $4.32 \times 10^{-6}$ K$^{-1}$ | 45% |
| MEAM | Short | $4.3 \times 10^{-6}$ K$^{-1}$ | ~45% |
| **EAM u3** | **Long** | **$9.12 \times 10^{-6}$ K$^{-1}$** | **96%** |
| **MEAM** | **Long** | **$7.58 \times 10^{-6}$ K$^{-1}$** | **80%** |

The Fe–Pt alloy grid uses **MEAM** because Fe–Pt cross-interactions are required. The long
protocol substantially improves the Pt CTE compared with the short protocol, although MEAM
may still underestimate the absolute value to some degree.

Full calibration details are available in:
- [`docs/PHYSICAL_VALIDATION.md`](docs/PHYSICAL_VALIDATION.md)

---

## Phase 4 Results

### Lattice Parameters and Thermal Expansion

| $x_{\mathrm{Pt}}$ | Composition | $a_{300}$ (Å) | $a_{1200}$ (Å) | $\Delta a$ (Å) | $\alpha_{\mathrm{eff}}$ (K$^{-1}$) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.00 | Fe | 3.6273 | 3.6753 | 0.0480 | $1.47 \times 10^{-5}$ |
| 0.25 | Fe$_3$Pt | 3.7976 | 3.8315 | 0.0339 | $9.91 \times 10^{-6}$ |
| 0.50 | FePt | 3.8699 | 3.8957 | 0.0258 | $7.41 \times 10^{-6}$ |
| 0.75 | FePt$_3$ | 3.9059 | 3.9308 | 0.0250 | $7.11 \times 10^{-6}$ |
| 1.00 | Pt | 3.9292 | 3.9560 | 0.0268 | $7.58 \times 10^{-6}$ |

### Key Trends

1. **Lattice parameter** increases with both temperature and Pt content, consistent
   with Vegard-like behaviour and the larger atomic radius of Pt (1.39 Å vs Fe 1.26 Å).
2. **CTE decreases sharply** with Pt alloying — Fe$_3$Pt already shows $\alpha \approx
   9.91 \times 10^{-6}$ K$^{-1}$, a 33% reduction from pure Fe.
3. **Minimum CTE** occurs at $x_{\mathrm{Pt}} = 0.75$ (FePt$_3$): $\alpha \approx
   7.11 \times 10^{-6}$ K$^{-1}$, followed by a slight uptick at pure Pt.
4. **Error bars** ($a_{\mathrm{std}}$) are consistent across all runs (0.003–0.010 Å),
   confirming converged production trajectories.

### Figures

Generated plots are placed alongside the output data (seed number is shown in the title):

| Output path | Description |
|-------------|-------------|
| `output_v4/a_vs_T_all_v4.png` | Lattice parameter $a(T)$ for all five compositions with error bands |
| `output_v4/a_vs_T_facets_v4.png` | Individual subplots per composition |
| `output_v4/a_vs_comp_v4.png` | Isothermal cross-sections $a(x_{\mathrm{Pt}})$ |
| `output_v4/integrity_check_v4.txt` | Cross-check of CSV vs raw logs |

---

## How to Run — Windows Pipeline

### Requirements

- **Windows 10/11**
- **Python 3.10 or newer**
- A pre-compiled LAMMPS executable placed in `bin/lmp.exe`

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

   This script:
   - Creates a Python virtual environment (`.venv`)
   - Installs required packages (`numpy`, `matplotlib`)
   - Checks that `bin/lmp.exe` exists

3. **Run the demo**

   ```cmd
   run_demo.bat
   ```

   Runs 2 MD simulations (pure Pt at 300 K and 600 K). Quick environment verification.

4. **Run the full calculation**

   ```cmd
   run.bat
   ```

   Interactive menu with 4 modes. See below for details.

### Run Modes

The project provides four calculation modes. The easiest way is to use `run.bat`
which presents an interactive menu for seed, resume/force, and mode selection.

| Mode | `.bat` file | Script | Protocol | Output dir | Purpose |
|------|------------|--------|----------|------------|---------|
| **M** MAIN | `run_main.bat` | `run_main.py` | 50k eq + 100k prod, **sequential** | `results/` | Single clean run with separate output |
| **T** TURBO | `run_turbo.bat` | `run_phase4_turbo.py --turbo` | 50k eq + 100k prod, **parallel** | `output_v4_parallel/` | High-accuracy parallel (cross-validation) |
| **P** TURBO-PLUS | `run_turbo.bat` | `run_phase4_turbo.py --turbo-plus` | 20k eq + 50k prod, **parallel** | `output_v4_parallel/` | Fast prototyping (⚠️ NOT final) |
| **L** LONG | `run.bat [L]` | `run_phase4.py` | 50k eq + 100k prod, **sequential** | `output_v4/` | Full validated protocol (main result) |

**For the final scientific result in `output_v4/`, select mode `L` (Long).**

All modes support `--seed`, `--resume`, and `--force` flags. The interactive `run.bat`
handles seed configuration (auto / manual / re-use) and asks whether to resume or
recalculate when existing log files are found.

#### Direct script invocation

```cmd
REM MAIN mode (results/)
python scripts\run_main.py [--seed N | --reuse-seed] [--resume | --force]

REM LONG mode (output_v4/)
python scripts\run_phase4.py [--seed N | --reuse-seed] [--resume | --force]

REM TURBO mode (output_v4_parallel/)
python scripts\run_phase4_turbo.py [--turbo | --turbo-plus] [--seed N | --reuse-seed] [--resume | --force]
```

### Seed Management

- **Auto (default):** a new random seed is generated for each run
- **Manual (`--seed 12345`):** specify a particular seed for reproducibility
- **Re-use (`--reuse-seed` or `--seed` without value):** uses the last seed from `seed.txt`
- On **resume (`--resume`)**, the seed from existing output is automatically re-used
- On **fresh run (`--force`)**, old logs and PNGs are deleted before starting

All output files include the seed number in their titles and metadata.

### Output Files

| Script mode | Output directory | Key files |
|-------------|-----------------|-----------|
| MAIN (`run_main.py`) | `results/` | `results.csv`, `plots/a_vs_T.png`, `plots/a_vs_comp.png`, `plots/a_vs_T_facets.png` |
| LONG (`run_phase4.py`) | `output_v4/` | `all_results.csv`, `integrity_check_v4.txt`, `a_vs_T_all_v4.png`, `a_vs_comp_v4.png`, `a_vs_T_facets_v4.png` |
| TURBO (`run_phase4_turbo.py`) | `output_v4_parallel/` | `all_results_v4_turbo.csv`, `integrity_check_v4_turbo.txt`, `a_vs_T_all_v4_turbo.png`, `a_vs_comp_v4_turbo.png`, `a_vs_T_facets_v4_turbo.png` |

Raw LAMMPS log files are in `*/logs/`. A `seed_info.txt` in the output directory
records the seed and its source.

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
├── scripts/
│   ├── run_phase4.py              ← Long protocol (sequential, output_v4/)
│   ├── run_phase4_turbo.py        ← Turbo protocol (parallel, output_v4_parallel/)
│   ├── run_main.py                ← MAIN protocol (sequential, results/)
│   ├── lmp_helper.py              ← Core LAMMPS helper (launcher, parser, plotting, CSV/XLSX)
│   ├── seed_manager.py            ← Seed generation and persistence
│   ├── gen_structure.py           ← Supercell generator (fcc Fe-Pt)
│   ├── rebuild_phase4.py          ← Rebuild results from raw logs
│   ├── phase4_analysis.m          ← MATLAB analysis script (experimental)
│   ├── in.thermal                 ← Demo LAMMPS input template
│   └── in.thermal_expansion       ← Production LAMMPS input template
├── data/
│   ├── *.lmp                      ← Generated supercell data files
│   └── data.fept_demo.lmp         ← Demo supercell
├── output_v4/                     ← Phase 4 Long results
│   ├── all_results.csv / .xlsx    ← CSV + Excel with numeric type formatting
│   ├── cte_report.csv             ← CTE metrics per composition
│   ├── integrity_check_v4.txt
│   ├── a_vs_T_all_v4.png
│   ├── a_vs_comp_v4.png
│   ├── a_vs_T_facets_v4.png
│   └── logs/                      ← Raw LAMMPS output
├── output_v4_parallel/            ← Phase 4 Turbo results
│   ├── all_results_v4_turbo.csv / .xlsx
│   ├── cte_report.csv
│   ├── integrity_check_v4_turbo.txt
│   ├── a_vs_T_all_v4_turbo.png
│   └── logs/                      ← Raw LAMMPS output
├── results/                       ← MAIN mode results
│   ├── results.csv / .xlsx
│   ├── plots/
│   └── logs/
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
├── bin/
│   └── lmp.exe                    ← LAMMPS executable (user-provided)
├── run.bat                        ← ★ INTERACTIVE LAUNCHER (recommended entry)
├── run_main.bat                   ← Direct MAIN mode launcher
├── run_turbo.bat                  ← Direct TURBO mode launcher
├── run_demo.bat                   ← Demo launcher
├── _run_lmp.bat                   ← LAMMPS wrapper (used by Python scripts)
├── bootstrap.bat                  ← Environment setup (Windows)
├── README_phase4.md               ← Legacy reference docs
├── requirements.txt               ← Python dependencies
├── seed.txt                       ← Last used seed
├── .gitattributes
└── .gitignore
```

---

## License

This project is provided as-is for collaborative research use. See the [LICENSE](LICENSE)
file for details.
