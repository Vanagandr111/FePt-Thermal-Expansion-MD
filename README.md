     1|# Molecular Dynamics Study of Thermal Expansion in Fe–Pt Alloys
     2|
     3|[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
     4|[![LAMMPS](https://img.shields.io/badge/LAMMPS-2Aug2023-orange)](https://www.lammps.org/)
     5|[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)
     6|
     7|This repository contains the complete pipeline for computing lattice parameters and
     8|thermal expansion coefficients (CTE) of face-centred cubic (fcc) Fe–Pt binary alloys using
     9|molecular dynamics (MD) simulations with LAMMPS. The project spans **20 independent MD
    10|simulations** across the full composition range at four temperatures, with a long
    11|equilibration and production protocol for converged results.
    12|
    13|**Key output:** Lattice parameter $a(T)$ for $x_{\mathrm{Pt}} = 0.00$, $0.25$, $0.50$, $0.75$, $1.00$
    14|at $T = 300$, $500$, $700$, $900$, $1100$, $1200$ K, with effective coefficient of thermal expansion (CTE)
    15|for each composition.
    16|
    17|---
    18|
    19|## Research Goals
    20|
    21|- Compute lattice parameter $a(T)$ for pure Pt at the fcc structure.
    22|- Compute lattice parameter $a(T)$ for Fe–Pt alloys at four Pt concentrations.
    23|- Determine the composition dependence $a(x_{\mathrm{Pt}})$ at fixed temperatures.
    24|- Validate the thermal expansion protocol against the Pt reference CTE ($9.5 \times 10^{-6}$ K$^{-1}$).
    25|- Ensure all results originate from raw MD output, not empirical fitting.
    26|
    27|---
    28|
    29|## Physical Background
    30|
    31|Thermal expansion in solids arises from the **anharmonicity** of interatomic potentials.
    32|In classical molecular dynamics, this is captured naturally in the **NPT ensemble** (constant
    33|number of atoms, constant pressure, constant temperature). As the temperature increases,
    34|the equilibrium interatomic spacing shifts outward because the potential energy surface is
    35|steeper on the compressive side than on the expansive side.
    36|
    37|In an NPT simulation, the box dimensions fluctuate around an equilibrium volume that
    38|increases with temperature. The lattice parameter $a$ is extracted from the time-averaged
    39|volume:
    40|
    41|$$a = \left(\frac{4 V}{N_{\text{atoms}}}\right)^{1/3}$$
    42|
    43|Pure Pt is used as a **benchmark system** because its CTE is well
    44|known from experiment ($9.5 \times 10^{-6}$ K$^{-1}$, mean over 300–1200 K range from
    45|Kirby, 1991 / Touloukian, NBS),
    46|allowing us to validate the protocol before applying it to Fe–Pt alloys.
    47|
    48|---
    49|
    50|## Methodology
    51|
    52|### Software
    53|
    54|- **LAMMPS** (2 Aug 2023) — molecular dynamics engine
    55|- **Python 3.10+** — pipeline orchestration, data analysis, plotting
    56|
    57|### Simulation Protocol
    58|
    59|| Parameter | Value |
    60||-----------|-------|
    61|| Supercell | $4 \times 4 \times 4$ fcc (256 atoms) |
    62|| Ensemble | `fix npt` (isotropic, $P = 0$ bar) |
    63|| Equilibration | 50 000 steps |
    64|| Production | 100 000 steps |
    65|| Thermo output | Every 100 steps → 1002 data points per run |
    66|| Averaging | Mean over all production thermo lines |
    67|| Potential (alloy grid) | **MEAM** (Kim, Koo, Lee, 2006) — `PtFe.meam` |
    68|| Potential (Pt benchmark) | **EAM u3** (Zhou _et al._) — `Pt_u3.eam` |
    69|
    70|### Compositions and Temperatures
    71|
    72|| $x_{\mathrm{Pt}}$ | Composition | Phase structure |
    73||-------------------|-------------|-----------------|
    74|| 0.00 | Fe | fcc (metastable) |
    75|| 0.25 | Fe$_3$Pt | L1$_2$ |
    76|| 0.50 | FePt | L1$_0$ |
    77|| 0.75 | FePt$_3$ | L1$_2$ |
    78|| 1.00 | Pt | fcc |
    79|
    80|| All six temperatures ($300$, $500$, $700$, $900$, $1100$, $1200$ K) are simulated for each composition,
    81||giving **30 independent MD runs**. The finer temperature grid (200 K spacing) provides better
    82||resolution for the thermal expansion curve.
    83|
    84|### Potentials
    85|
    86|- **MEAM** (Kim, Koo, Lee, 2006) — used for the full Fe–Pt composition grid. This potential
    87|  includes explicit Fe–Pt cross-interactions (`Ec(1,2)=5.86`, `re(1,2)=2.7181`, `alpha(1,2)=5.97`,
    88|  plus 9 `Cmin/Cmax` pairs for angular screening). It is **not** a linear interpolation of
    89|  the pure-element EAM potentials.
    90|- **EAM u3** (Zhou _et al._) — used only as a pure Pt benchmark for protocol validation.
    91|  This potential is **not** used for Fe–Pt alloys.
    92|
    93|---
    94|
    95|## Pt Thermal Expansion Calibration
    96|
    97|An earlier short protocol (10 000 eq + 50 000 prod) underestimated the Pt CTE significantly.
    98|The **long protocol** (50 000 eq + 100 000 prod, tested here with a 256‑atom supercell) gives
    99|much better agreement with experiment.
   100|
   101|| Potential | Supercell | Protocol | CTE (300–1200 K) | Fraction of exp. ($9.5 \\times 10^{-6}$ K$^{-1}$) |
   102||-----------|-----------|----------|-------------------|----------------------------------------------|
   103|| EAM u3 | 256‑atom | Short | $4.32 \\times 10^{-6}$ K$^{-1}$ | 45% |
   104|| MEAM | 256‑atom | Short | $4.3 \\times 10^{-6}$ K$^{-1}$ | ~45% |
   105|| **EAM u3** | **256‑atom** | **Long** | **$9.12 \\times 10^{-6}$ K$^{-1}$** | **96%** |
   106|| **MEAM (this work)** | **256‑atom** | **Long (turbo)** | **$9.151 \\times 10^{-6}$ K$^{-1}$** | **96%** |
   107|
   108|The MEAM potential with the long protocol achieves 96 % of the experimental Pt CTE, a
   109|substantial improvement over the short protocol (45 %).
   110|
   111|Full calibration details are available in:
   112|- [`docs/PHYSICAL_VALIDATION.md`](docs/PHYSICAL_VALIDATION.md)
   113|
   114|---
   115|
   116|## Phase 4 Results — 256‑atom Supercell (Turbo)
   117|
   118|All results were obtained with the **turbo** mode (50 000 eq + 100 000 prod) using a
   119|$4\\times4\\times4$ fcc supercell (256 atoms), MEAM potential, OpenMP backend, and a
   120|single seed (26365). Six temperatures per composition give **30 independent MD runs**.
   121|
   122|### Lattice Parameters
   123|
   124|| $x_{\\mathrm{Pt}}$ | Composition | $a_{300}$ (Å) | $a_{500}$ (Å) | $a_{700}$ (Å) | $a_{900}$ (Å) | $a_{1100}$ (Å) | $a_{1200}$ (Å) |
   125||:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
   126|| 0.00 | Fe | 3.6270 | 3.6374 | 3.6476 | 3.6585 | 3.6690 | 3.6747 |
   127|| 0.25 | Fe$_3$Pt | 3.7975 | 3.8066 | 3.8145 | 3.8214 | 3.8283 | 3.8316 |
   128|| 0.50 | FePt | 3.8698 | 3.8760 | 3.8817 | 3.8874 | 3.8928 | 3.8952 |
   129|| 0.75 | FePt$_3$ | 3.9059 | 3.9118 | 3.9176 | 3.9228 | 3.9279 | 3.9309 |
   130|| 1.00 | Pt | 3.9290 | 3.9352 | 3.9421 | 3.9493 | 3.9577 | 3.9614 |
   131|
   132|### Thermal Expansion (300–1200 K)
   133|
   134|| $x_{\\mathrm{Pt}}$ | Composition | $\\Delta a$ (Å) | $\\alpha_{\\mathrm{eff}}$ (K$^{-1}$) |
   135||:---:|:---:|:---:|:---:|
   136|| 0.00 | Fe | 0.0477 | $1.460 \\times 10^{-5}$ |
   137|| 0.25 | Fe$_3$Pt | 0.0341 | $9.985 \\times 10^{-6}$ |
   138|| 0.50 | FePt | 0.0254 | $7.289 \\times 10^{-6}$ |
   139|| 0.75 | FePt$_3$ | 0.0250 | $7.117 \\times 10^{-6}$ |
   140|| 1.00 | Pt | 0.0324 | $9.151 \\times 10^{-6}$ |
   141|
   142|### Key Trends
   143|
   144|1. **Lattice parameter** increases with both temperature and Pt content, consistent
   145|   with Vegard-like behaviour and the larger atomic radius of Pt (1.39 Å vs Fe 1.26 Å).
   146|2. **CTE minimum** occurs at $x_{\\mathrm{Pt}} = 0.75$ (FePt$_3$): $\\alpha \\approx
   147|   7.117 \\times 10^{-6}$ K$^{-1}$.
   148|3. **Pt CTE ($9.151 \\times 10^{-6}$ K$^{-1}$) reaches 96 % of the experimental reference
   149|   ($9.5 \\times 10^{-6}$ K$^{-1}$)**, validating the long protocol for pure Pt.
   150|4. **Pure Fe CTE** ($1.460 \\times 10^{-5}$ K$^{-1}$) is the highest, consistent with
   151|   the weaker bonding in metastable fcc-Fe.
   152|5. **Error bars** ($a_{\\mathrm{std}}$) range from 0.002–0.010 Å, confirming converged
   153|   production trajectories.
   154|6. **200 K temperature grid** (300–1200 K, 6 points) gives finer resolution of the
   155|   $a(T)$ curve compared with the earlier 4-point protocol.
   156|
   157|### Figures
   158|
   159|Generated plots are in the output directory (seed 26365 in metadata):
   160|
   161|| Output path | Description |
   162||-------------|-------------|
   163|| `output_v4_256/a_vs_T_turbo_256at_omp.png` | Lattice parameter $a(T)$ for all five compositions with error bands |
   164|| `output_v4_256/a_vs_T_turbo_256at_omp_facets.png` | Individual subplots per composition |
   165|| `output_v4_256/a_vs_comp.png` | Isothermal cross-sections $a(x_{\\mathrm{Pt}})$ |
   166|| `output_v4_256/all_results_turbo_256at_omp.csv` | Full results CSV (30 points) |
   167|| `output_v4_256/integrity_check_v4_turbo.txt` | Cross-check of CSV vs raw logs |
   168|
   169|---
   170|
   171|## How to Run — Windows Pipeline
   172|
   173|### Requirements
   174|
   175|- **Windows 10/11**
   176|- **Python 3.10 or newer** (uses `py` launcher or `python` automatically)
   177|- A pre-compiled LAMMPS executable
   178|
   179|> **No WSL is required.** The pipeline runs natively on Windows.
   180|>
   181|> **Active runtime is Windows-only.** WSL is not required and not supported for final runtime.
   182|> Legacy WSL development scripts have been cleaned from the repository.
   183|
   184|### Quick Start
   185|
   186|1. **Clone the repository**
   187|
   188|   ```cmd
   189|   git clone <repo-url>
   190|   cd FePt-Thermal-Expansion-MD
   191|   ```
   192|
   193|2. **Bootstrap the environment**
   194|
   195|   Double-click `bootstrap.bat`, or run from Command Prompt:
   196|
   197|   ```cmd
   198|   bootstrap.bat
   199|   ```
   200|
   201|   This script:
   202|   - Creates a Python virtual environment (`.venv`)
   203|   - Installs required packages (`numpy`, `matplotlib`)
   204|   - Checks that `bin/lmp.exe` exists
   205|
   206|3. **Run the demo**
   207|
   208|   ```cmd
   209|   run_demo.bat
   210|   ```
   211|
   212|   Runs 2 MD simulations (pure Pt at 300 K and 600 K). Quick environment verification.
   213|
   214|4. **Run the full calculation**
   215|
   216|   ```cmd
   217|   run.bat
   218|   ```
   219|
   220|   Interactive menu with 9 modes. See below for details.
   221|
   222|### Run Modes
   223|
   224|The project provides several calculation modes. The easiest way is to use `run.bat`
   225|which presents an interactive menu for seed, resume/force, and mode selection.
   226|
   227|| Mode | `.bat` file | Script | Protocol | Output dir | Purpose |
   228||------|------------|--------|----------|------------|---------|
   229|| **0** DEMO | `run.bat [0]` | `run_mode.py --mode demo` | 50 eq + 100 prod, 2048at | `output_v4/` | Quick environment verification |
   230|| **1** TURBO-FAST | `run.bat [1]` | `run_mode.py --mode turbo-fast` | 20k eq + 50k prod, 256at | `output_v4_256/` | Fast prototyping (⚠️ NOT final) |
   231|| **2** TURBO 256at | `run.bat [2]` | `run_mode.py --mode turbo --natoms 256 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | Main 256‑atom result |
   232|| **3** TURBO 2048at (OMP) | `run.bat [3]` | `run_mode.py --mode turbo --natoms 2048 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | 2048‑atom cross‑check |
   233|| **4** TURBO 2048at (KOKKOS) | `run.bat [4]` | `run_mode.py --mode turbo --natoms 2048 --backend kokkos` | 50k eq + 100k prod, parallel | `output_v4_256/` | GPU‑accelerated |
   234|| **5** LONG 256at | `run.bat [5]` | `run_mode.py --mode long --natoms 256 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | Full protocol (neigh 2.0) |
   235|| **6** LONG 2048at (OMP) | `run.bat [6]` | `run_mode.py --mode long --natoms 2048 --backend omp` | 50k eq + 100k prod, parallel | `output_v4_256/` | Full 2048‑atom |
   236|| **7** LONG 2048at (KOKKOS) | `run.bat [7]` | `run_mode.py --mode long --natoms 2048 --backend kokkos` | 50k eq + 100k prod, parallel | `output_v4_256/` | Full 2048‑atom GPU |
   237|| **8** TURBO-EXP | `run.bat [8]` | `run_mode.py --mode turbo-experimental` | 50k eq + 100k prod, OMP 4t, neigh/5 | `output_v4_256/` | Experimental tuning |
   238|
   239|**For the final scientific result, use mode `2` (Turbo 256at).** The results in
   240|`output_v4_256/` (seed 26365) are the principal 256‑atom dataset.
   241|
   242|All modes support `--seed`, `--resume`, and `--force` flags. The interactive `run.bat`
   243|handles seed configuration (auto / manual / re-use) and asks whether to resume or
   244|recalculate when existing log files are found.
   245|
   246|#### Direct script invocation
   247|
   248|```cmd
   249|REM TURBO 256at (recommended)
   250|%%PYTHON%% scripts\run_mode.py --mode turbo --natoms 256 --backend omp [--seed N | --reuse-seed] [--resume | --force]
   251|
   252|REM TURBO 2048at
   253|%%PYTHON%% scripts\run_mode.py --mode turbo --natoms 2048 --backend omp [--seed N | --reuse-seed] [--resume | --force]
   254|
   255|REM LONG 256at
   256|%%PYTHON%% scripts\run_mode.py --mode long --natoms 256 --backend omp [--seed N | --reuse-seed] [--resume | --force]
   257|```
   258|
   259|### Seed Management
   260|
   261|- **Auto (default):** a new random seed is generated for each run
   262|- **Manual (`--seed 12345`):** specify a particular seed for reproducibility
   263|- **Re-use (`--reuse-seed` or `--seed` without value):** uses the last seed from `seed.txt`
   264|- On **resume (`--resume`)**, the seed from existing output is automatically re-used
   265|- On **fresh run (`--force`)**, old logs and PNGs are deleted before starting
   266|
   267|All output files include the seed number in their titles and metadata.
   268|
   269|### Output Files
   270|
   271|| Mode | Output directory | Key files |
   272||------|-----------------|-----------|
   273|| DEMO (`run_mode.py --mode demo`) | `output_v4/` | `logs/`, `in/` (quick test only) |
   274|| TURBO/LONG 256at | `output_v4_256/` | `all_results_turbo_256at_omp.csv`, `.xlsx`, `a_vs_T_turbo_256at_omp.png`, `a_vs_T_turbo_256at_omp_facets.png`, `a_vs_comp.png`, `integrity_check_v4_turbo.txt`, `cte_report.csv`, `seed_info.txt`, `run_protocol.txt` |
   275|
   276|Raw LAMMPS log files are in `output_v4_256/logs/`. Each log file covers one
   277|composition–temperature pair. LAMMPS input files are in `output_v4_256/in/`.
   278|A `seed_info.txt` in the output directory records the seed and its source.
   279|
   280|Raw LAMMPS log files are in `*/logs/`. A `seed_info.txt` in the output directory
   281|records the seed and its source.
   282|
   283|---
   284|
   285|## Reproducibility and Data Integrity
   286|
   287|- **Raw logs as source of truth:** All lattice parameters are extracted directly from
   288|  LAMMPS thermo output. No manual fitting, scaling, or interpolation is applied.
   289|- **Integrity check:** An automated cross-check verifies that every row in the CSV
   290|  corresponds to a valid, completed LAMMPS log file. See
   291|  `output_v4/integrity_check_v4.txt` or `output_v4_parallel/integrity_check_v4_turbo.txt`.
   292|- **Seed tracking:** Every run records its seed. Re-running with `--reuse-seed` gives
   293|  bit-identical results.
   294|- **No Vegard-law fitting:** The composition dependence $a(x_{\mathrm{Pt}})$ is computed
   295|  directly from MD trajectories, not from an empirical mixing rule.
   296|- **Reference CTE:** The experimental Pt CTE is used only for validation — it does not
   297|  enter the MD simulation or the data analysis pipeline.
   298|- **Structures regenerated per run:** Each simulation starts from a freshly generated
   299|  supercell (fixed seed 42 for structure generation) to avoid metastable traps from
   300|  restarted data files.
   301|
   302|---
   303|
   304|## Limitations
   305|
   306|1. **Classical potentials** — MEAM does not capture quantum effects, magnetic
   307|   contributions, or electronic excitations that may influence thermal expansion.
   308|2. **fcc-Fe metastability** — Iron is stable in the bcc phase at room temperature.
   309|   The fcc structure studied here is appropriate for Fe–Pt alloys (which crystallise
   310|   in fcc-derived ordered phases) but does not describe pure Fe in its ground state.
   311|3. **MEAM accuracy** — The Kim–Koo–Lee (2006) potential was optimised for formation
   312|   energies and melting temperatures, not specifically for the temperature-dependent
   313|   lattice parameter.
   314|4. **System size** — 256-atom supercells may exhibit finite-size effects. Larger
   315|   supercells (8×8×8, 2048 atoms) are recommended for higher precision.
   316|5. **Finite MD time** — Although the long protocol significantly improves convergence,
   317|   the 100 000-step production run may not fully sample all anharmonic degrees of freedom
   318|   at high temperatures.
   319|6. **Single seed** — All runs currently use one seed per composition. Multiple independent
   320|   seeds with ensemble averaging would reduce statistical noise.
   321|
   322|---
   323|
   324|## Future Work
   325|
   326|- Larger supercells ($8 \times 8 \times 8$ or larger) for reduced finite-size effects.
   327|- Multiple random seeds per composition for ensemble averaging.
   328|- Nanoparticle and slab geometries for surface-related thermal expansion.
   329|- Comparison with density functional theory (DFT) quasi-harmonic calculations.
   330|- Alternative interatomic potentials (EAM, ML-IAP, second-nearest-neighbour MEAM).
   331|- Experimental validation using published Fe–Pt thermal expansion data.
   332|
   333|---
   334|
   335|## File Structure
   336|
   337|```
   338|FePt-Thermal-Expansion-MD/
   339||── scripts/
   340|│   ├── run_mode.py              ← Universal launcher (all modes)
   341|│   ├── lmp_helper.py            ← Core LAMMPS helper (launcher, parser, plotting, CSV)
   342|│   ├── seed_manager.py          ← Seed generation and persistence
   343|│   ├── gen_structure.py         ← Supercell generator (fcc Fe-Pt)
   344|│   ├── _run_one_point.py        ← Single-point run helper
   345|│   ├── _test_single_run.py      ← Single-point test
   346|│   ├── regenerate_plots.py      ← Regenerate plots from existing CSV/logs
   347|│   ├── run_fe_only.py           ← Pure Fe runs
   348|│   ├── run_pt_eam.py            ← Pt EAM benchmark runs
   349|│   ├── test_kokkos.py           ← KOKKOS backend test
   350|│   └── in.thermal_expansion     ← Production LAMMPS input template
   351|├── data/
   352|│   ├── *.lmp                      ← Generated supercell data files
   353|│   └── data.fept_demo.lmp         ← Demo supercell
   354|├── output_v4_256/                 ← ★ PRINCIPAL RESULTS (Turbo, 256‑atom, seed 26365)
   355|│   ├── all_results_turbo_256at_omp.csv / .xlsx
   356|│   ├── a_vs_T_turbo_256at_omp.png
   357|│   ├── a_vs_T_turbo_256at_omp_facets.png
   358|│   ├── a_vs_comp.png
   359|│   ├── cte_report.csv
   360|│   ├── integrity_check_v4_turbo.txt
   361|│   ├── seed_info.txt
   362|│   ├── run_protocol.txt
   363|│   ├── in/                          ← LAMMPS input files
   364|│   └── logs/                        ← Raw LAMMPS outputs (30 runs)
   365|├── output_v4/                     ← Legacy 128‑atom Phase 4 results
   366|├── output_v4_parallel/            ← Legacy 128‑atom Phase 4 Turbo results
   367|├── output_v4_reduced/             ← Legacy
   368|├── results/                       ← Legacy
   369|├── potentials/
   370|│   ├── PtFe.meam                  ← MEAM alloy potential
   371|│   ├── library.meam               ← MEAM library file
   372|│   ├── Fe_Zhou.eam.alloy          ← Fe EAM (Zhou _et al._)
   373|│   ├── Pt_Zhou.eam.alloy          ← Pt EAM (Zhou _et al._)
   374|│   ├── Pt_u3.eam                  ← Pt EAM benchmark
   375|│   ├── Fe_mm.eam.fs               ← Fe EAM (Mendelev, 2007)
   376|│   └── ...                        ← Additional EAM variants
   377|├── docs/
   378|│   ├── PHYSICAL_VALIDATION.md     ← Protocol validation details
   379|│   └── REPORT.md                  ← MATLAB script status
   380|├── bin/                            ← LAMMPS executable + DLLs + utilities
   381|├── run.bat                        ← ★ INTERACTIVE LAUNCHER (auto-detects Python)
   382|├── _run_lmp.bat                   ← LAMMPS wrapper (used by Python scripts)
   383|├── bootstrap.bat                  ← Environment setup (Windows)
   384|├── requirements.txt               ← Python dependencies
   385|├── seed.txt                       ← Last used seed
   386|├── .gitattributes
   387|└── .gitignore
   388|```
   389|
   390|---
   391|
   392|## License
   393|
   394|This project is provided as-is for collaborative research use. See the [LICENSE](LICENSE)
   395|file for details.
   396|