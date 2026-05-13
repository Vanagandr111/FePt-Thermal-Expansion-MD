# Molecular Dynamics Study of Thermal Expansion in Fe–Pt Alloys

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![LAMMPS](https://img.shields.io/badge/LAMMPS-2Aug2023-orange)](https://www.lammps.org/)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2022b%2B-green)](https://www.mathworks.com/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

This repository contains the complete pipeline for computing lattice parameters and
thermal expansion coefficients of face-centred cubic (fcc) Fe–Pt binary alloys using
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
- Validate the thermal expansion protocol against the Pt reference CTE.
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

for a cubic fcc cell. Pure Pt is used as a **benchmark system** because its CTE is well
known from experiment ($9.0 \times 10^{-6}$ K$^{-1}$ at 300 K), allowing us to validate
the protocol before applying it to Fe–Pt alloys.

---

## Methodology

### Software

- **LAMMPS** (2 Aug 2023) — molecular dynamics engine
- **Python 3.10+** — pipeline orchestration, data analysis, plotting
- **MATLAB R2022b+** — alternative analysis pipeline (see below)

### Simulation Protocol

| Parameter | Value |
|-----------|-------|
| Supercell | $4 \times 4 \times 4$ fcc (256 atoms) |
| Ensemble | `fix npt` (isotropic, $P = 0$ bar) |
| Equilibration | 50 000 steps |
| Production | 100 000 steps |
| Thermo output | Every 100 steps → 1002 data points per run |
| Averaging | Mean over all production thermo lines |
| Potentials | MEAM (Fe–Pt cross-interaction) for alloy grid; EAM u3 for Pt benchmark |

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
  includes Fe–Pt cross-interactions, which are essential for modelling alloy thermal expansion.
- **EAM u3** (Zhou _et al._) — used only as a pure Pt benchmark for protocol validation.
  This potential is **not** used for Fe–Pt alloys.

---

## Pt Thermal Expansion Calibration

An earlier short protocol (10 000 eq + 50 000 prod) underestimated the Pt CTE significantly.
The **long protocol** (50 000 eq + 100 000 prod) brings the computed CTE much closer to the
experimental reference.

| Potential | Protocol | CTE (300–1200 K) | Fraction of exp. |
|-----------|----------|-------------------|------------------|
| EAM u3 | Short | $4.32 \times 10^{-6}$ K$^{-1}$ | 48% |
| MEAM | Short | — | ~50% |
| EAM u3 | Long | $9.12 \times 10^{-6}$ K$^{-1}$ | 101% |
| MEAM | Long | $7.58 \times 10^{-6}$ K$^{-1}$ | 84% |

The Fe–Pt alloy grid uses **MEAM** because Fe–Pt cross-interactions are required. The long
protocol substantially improves the Pt CTE compared with the short protocol, although MEAM
may still underestimate the absolute value to some degree.

Full calibration details are available in:
- [`docs/PHYSICAL_VALIDATION.md`](docs/PHYSICAL_VALIDATION.md)
- [`output_v3/pt_calibration_summary.txt`](output_v3/pt_calibration_summary.txt)

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

---

## Figures

All figures are available in the [`figures/`](figures/) directory.

| Figure | Description |
|--------|-------------|
| [`figures/a_vs_T_all.png`](figures/a_vs_T_all.png) | Lattice parameter $a(T)$ for all five compositions with error bars |
| [`figures/a_vs_T_facets.png`](figures/a_vs_T_facets.png) | Individual subplots per composition |
| [`figures/a_vs_xPt.png`](figures/a_vs_xPt.png) | Isothermal cross-sections $a(x_{\mathrm{Pt}})$ |
| [`figures/cte_vs_xPt.png`](figures/cte_vs_xPt.png) | CTE vs Pt fraction with annotated values |
| [`figures/delta_a_percent.png`](figures/delta_a_percent.png) | Relative thermal expansion $\Delta a / a_0$ (%) |

---

## How to Run — Python / Windows Pipeline

### Requirements

- **Windows 10/11**
- **Python 3.10 or newer**
- A pre-compiled LAMMPS executable placed in `bin/lmp.exe`

> No WSL is required. The pipeline runs natively on Windows.

### Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/USERNAME/FePt-Thermal-Expansion-MD.git
   cd FePt-Thermal-Expansion-MD
   ```

2. **Run bootstrap**

   Double-click `bootstrap.bat`, or run from Command Prompt:

   ```cmd
   bootstrap.bat
   ```

   This script:
   - Creates a Python virtual environment (`.venv`)
   - Installs required packages (`numpy`, `matplotlib`, `pandas`)
   - Checks that `bin/lmp.exe` exists
   - Runs a quick demo to verify the environment

3. **Run the demo**

   ```cmd
   run_demo.bat
   ```

   This runs a single MD simulation for pure Fe at 300 K and produces a quick plot.

4. **Run the full Phase 4 calculation**

   ```cmd
   run_main.bat
   ```

   This executes all 20 MD simulations (this may take several hours depending on hardware).

### Output Files

| Path | Description |
|------|-------------|
| `output_v4/all_results.csv` | Master table of all 20 runs |
| `output_v4/integrity_check_v4.txt` | Cross-check of CSV vs raw logs |
| `figures/*.png` | Publication-quality PNG figures |

---

## How to Run — MATLAB Analysis

**Status:** ⚠️ Prepared — runtime test pending

The MATLAB script `scripts/phase4_analysis.m` was written and logically verified but
**not executed** on the development machine (MATLAB was not installed). It should be
run on a target machine with MATLAB available.

### Steps

1. Clone the repository:

   ```bash
   git clone https://github.com/USERNAME/FePt-Thermal-Expansion-MD.git
   cd FePt-Thermal-Expansion-MD
   ```

2. Open **MATLAB R2022b or newer** on Windows.

3. Set the **Current Folder** to the project root:

   ```matlab
   >> cd('C:\path\to\FePt-Thermal-Expansion-MD')
   ```

4. Run the analysis:

   ```matlab
   >> scripts\phase4_analysis
   ```

   or in MATLAB:

   ```matlab
   >> run('scripts/phase4_analysis.m')
   ```

### MATLAB Output

The script reads `output_v4/all_results.csv` and creates:

| File | Description |
|------|-------------|
| `output_v4/a_vs_T_all.png` | a(T) for all compositions with error bars |
| `output_v4/a_vs_T_facets.png` | Faceted subplots |
| `output_v4/a_vs_xPt.png` | Isothermal cross-sections |
| `output_v4/cte_vs_xPt.png` | CTE vs Pt fraction |
| `output_v4/delta_a_percent.png` | Relative thermal expansion |
| `output_v4/phase4_summary.csv` | Summary table |

> If MATLAB is not available, equivalent Python-generated figures are already available
> in [`figures/`](figures/).

---

## Reproducibility and Data Integrity

- **Raw logs as source of truth:** All lattice parameters are extracted directly from
  LAMMPS thermo output. No manual fitting, scaling, or interpolation is applied.
- **Integrity check:** An automated cross-check verifies that every row in the CSV
  corresponds to a valid, completed LAMMPS log file. See
  [`output_v4/integrity_check_v4.txt`](output_v4/integrity_check_v4.txt).
- **No Vegard-law fitting:** The composition dependence $a(x_{\mathrm{Pt}})$ is computed
  directly from MD trajectories, not from an empirical mixing rule.
- **Reference CTE:** The experimental Pt CTE is used only for validation — it does not
  enter the MD simulation or the data analysis pipeline.
- **Structures regenerated per run:** Each simulation starts from a freshly generated
  supercell (fixed seed 42) to avoid metastable traps from restarted data files.

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

---

## Future Work

- Larger supercells ($8 \times 8 \times 8$ or larger) for reduced finite-size effects.
- Multiple random seeds per composition to assess statistical uncertainty.
- Nanoparticle and slab geometries for surface-related thermal expansion.
- Comparison with density functional theory (DFT) quasi-harmonic calculations.
- Alternative interatomic potentials (EAM, ML-IAP, second-nearest-neighbour MEAM).
- Experimental validation using published Fe–Pt thermal expansion data.

---

## File Structure

```
FePt-Thermal-Expansion-MD/
├── scripts/
│   ├── phase4_analysis.m          ← MATLAB analysis script
│   ├── run_fept_grid_v4.py        ← Phase 4 LAMMPS runner
│   ├── analyze_pt_calibration_v3.py
│   ├── build_final_artifacts.py
│   └── ...                        ← Additional analysis and utility scripts
├── figures/
│   ├── a_vs_T_all.png
│   ├── a_vs_T_facets.png
│   ├── a_vs_xPt.png
│   ├── cte_vs_xPt.png
│   └── delta_a_percent.png
├── docs/
│   ├── REPORT.md                  ← MATLAB script status
│   └── PHYSICAL_VALIDATION.md     ← Protocol validation details
├── output_v4/
│   ├── all_results.csv            ← Phase 4 master data
│   ├── integrity_check_v4.txt     ← Integrity verification
│   └── logs/                      ← Raw LAMMPS output
├── output_v3/                     ← Pt calibration (Phase 3)
├── output_v2/                     ← Short protocol (Phase 2, replaced)
├── potentials/
│   ├── PtFe.meam                  ← MEAM alloy potential
│   ├── Fe_Zhou.eam.alloy          ← Fe EAM
│   ├── Pt_Zhou.eam.alloy          ← Pt EAM
│   ├── Pt_u3.eam                  ← Pt EAM benchmark
│   └── library.meam               ← MEAM library file
├── bootstrap.bat                  ← Environment setup (Windows)
├── run_demo.bat                   ← Quick demo run
├── run_main.bat                   ← Full Phase 4 pipeline
├── requirements.txt               ← Python dependencies
├── INSTALL_AND_RUN.txt            ← Quick-start instructions
├── README_phase4.md               ← MATLAB-specific documentation
└── README.md                      ← This file
```

---

## License

This project is provided as-is for collaborative research use. See the [LICENSE](LICENSE)
file for details.
