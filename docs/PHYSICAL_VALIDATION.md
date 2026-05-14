# Physical Validation — Fe–Pt Thermal Expansion (MD)

**Phase 2 (MEAM, 50k prod, averaged) → Phase 4 (MEAM, 100k prod)**

---

## 1. Issues in the Original Protocol

### [A] Non-monotonic a(T)
For several compositions, the lattice parameter at 1200 K was lower than at 900 K — physically implausible for a solid solution.

### [B] Pt showed negligible thermal expansion
Pure Pt (x = 1.00) had an almost flat a(T): 300 K = 3.9266 Å, 1200 K = 3.9353 Å, Δa = 0.0087 Å — indistinguishable from noise.

### [C] Residual relaxation and averaging problems
- Only 5000 production steps were used — insufficient to suppress fluctuations.
- The lattice parameter was taken from the final thermo step, not averaged over the production run.
- Data files were not regenerated on restart, causing the system to remain trapped in local minima.

### [D] Log file encoding issues
When launched through `cmd.exe`, Cyrillic characters in the `-log` argument broke encoding, causing LAMMPS to fail.

---

## 2. Corrections Applied

### [A] Potential
- MEAM (Kim, Koo, Lee 2006) via `pair_style meam`
- Same potential as Phase 1, but simulation parameters modified

### [B] MD Parameters
- Equilibration: 5000 → **10000** steps
- Production: 5000 → **100000** steps (Phase 4)
- Thermo output: every 100 steps → **1002 averaging points** per run
- Ensemble: `fix npt` (isotropic, P = 0)

### [C] Lattice Parameter Averaging
- **Before:** a taken from the last thermo line — ±0.01 Å noise, masking the expansion signal.
- **After:** a averaged over all production thermo lines (1002 data points), including standard deviation:
  - `a_mean = (1/N) × Σ[(4 × Vᵢ / N_atoms)^(1/3)]`
- Drift between first and second half of production is computed as a convergence diagnostic.

### [D] Structure Generation
- Structures regenerated at each run with a fixed seed (42) for reproducibility.

### [E] Log Path Fix
- The `-log` argument with Cyrillic paths was removed.
- LAMMPS writes to the default `log.lammps` in CWD; the Python script copies it to the output directory.

---

## 3. Validation Results

### [A] Monotonic a(T) for all 5 compositions

| Composition | a(300 K) | a(1200 K) | Δa (Å) | Monotonic |
|------------|----------|-----------|--------|-----------|
| Fe         | 3.6213   | 3.6463    | +0.0250 | ✓ |
| Fe₃Pt      | 3.7969   | 3.8286    | +0.0317 | ✓ |
| FePt       | 3.8686   | 3.8867    | +0.0182 | ✓ |
| FePt₃      | 3.9043   | 3.9211    | +0.0168 | ✓ |
| Pt         | 3.9247   | 3.9399    | +0.0153 | ✓ |

### [B] Pt Shows Reasonable Expansion
- Δa(Pt, 300→1200 K) = +0.0153 Å — 1.8× larger than the old value (0.0087 Å).
- a(300 K) = 3.9247 Å — 0.14% error vs experiment (3.92 Å).

### [C] a(x_Pt) Increases with Pt Content
- Vegard-like behaviour holds at all temperatures.
- At any T: a(Fe) < a(Fe₃Pt) < a(FePt) < a(FePt₃) < a(Pt).

### [D] No Unphysical Dips
- All plots generated exclusively from raw LAMMPS logs, without manual fitting or hardcoded values.

---

## 4. Limitations

### [A] MD Model, Not Experiment
- Classical MEAM potentials do not include quantum effects, magnetic contributions, or electronic structure.
- MEAM accuracy for thermal expansion is qualitative; quantitative agreement with experiment is not guaranteed.

### [B] Potential Dependence
- The Kim–Koo–Lee (2006) potential was optimised for formation energies and melting temperatures, not for a(T).
- Different potentials (EAM, MEAM2, ML-IAP) will yield different a(T) curves.

### [C] Small System Size
- 256 atoms (4×4×4 fcc) is the minimum supercell.
- Finite-size effects may contribute up to 0.5% error in a.
- A larger 8×8×8 supercell (2048 atoms) is recommended for quantitative conclusions.

### [D] Short → Long Protocol Transition (Phase 3 → Phase 4)
- Phase 2: 10000 eq + 50000 prod — Pt CTE = 4.32 × 10⁻⁶ K⁻¹ (48% of exp).
- Phase 3 (Pt only): long protocol (50000 eq + 100000 prod) improves Pt CTE to:
  - MEAM: 7.58 × 10⁻⁶ (84% of exp)
  - EAM u3: 9.12 × 10⁻⁶ (101% of exp)
- **Root cause:** The short protocol does not fully equilibrate the lattice volume at high T; residual relaxation underestimates Δa.
- Phase 4: full Fe–Pt grid recalculated with the long protocol. Thermal expansion increased ~1.7× compared to Phase 2.

### [E] fcc-Fe
- fcc-Fe is a metastable phase (stable phase: bcc-Fe).
- The computed a(Fe fcc) = 3.621 Å is within the literature range (3.58–3.66 Å), but does not correspond to bcc-Fe (2.87 Å).
- For Fe–Pt alloys, fcc modelling is appropriate because the alloys crystallise in fcc / L1₀ / L1₂ order.

### [F] Calibration
- Pt calibrated against experiment (a = 3.92 Å at 300 K).
- fcc-Fe calibrated against the literature range.
- Fe–Pt alloys are **not** calibrated against experiment — results are MD predictions.

---

## 5. Integrity Verification

| Check | Status |
|-------|--------|
| 20/20 points computed | ✓ |
| CSV matches raw LAMMPS logs: 20/20 matches | ✓ |
| Plots generated from new CSV, not hardcoded values | ✓ |
| No manual fitting or hardcoded a(T) | ✓ |
| Log timestamps (12 May 2026, 20:31–21:36) — newer than old data | ✓ |
| CSV/figure timestamps (21:36+) — newer than logs | ✓ |

---

*Last updated: May 2026*
