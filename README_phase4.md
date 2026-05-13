# Phase 4 — Fe₁₋ₓPtₓ MD Long Runs: Lattice Parameter Analysis

## Overview

Phase 4 molecular dynamics (MD) simulations of Fe–Pt binary alloys across the full composition range using LAMMPS.
Long equilibration (50 k steps) and production runs (100 k steps) to obtain converged lattice parameters at four temperatures.

**Compositions:** x(Pt) = 0.00 (Fe), 0.25 (Fe₃Pt), 0.50 (FePt), 0.75 (FePt₃), 1.00 (Pt)  
**Temperatures:** T = 300, 600, 900, 1200 K  
**Total:** 20 independent MD simulations, all verified.

---

## Input Data

| File | Description |
|------|-------------|
| `output_v4/all_results.csv` | Master table (20 rows × 10 columns) |
| `output_v4/integrity_check_v4.txt` | Cross-check of all 20 runs |

### CSV columns

`x_Pt, T_K, a_mean_Angstrom, a_std_Angstrom, result_last_point, drift, n_points, mean_press_bar, std_press_bar, runtime_s`

---

## Generated Figures (saved to `output_v4/`)

### 1. `a_vs_T_all.png`
Lattice parameter a(T) for all five compositions with error bars. Shows thermal expansion and increase of lattice constant with Pt content.

### 2. `a_vs_T_facets.png`
Individual subplots per composition, annotated with total expansion Δa.

### 3. `a_vs_xPt.png`
Isothermal cross-sections: lattice parameter vs Pt fraction at each temperature.

### 4. `cte_vs_xPt.png`
Effective CTE (α = Δa / a₀ / ΔT) vs Pt fraction with annotated values.

### 5. `delta_a_percent.png`
Relative thermal expansion Δa/a₀(%) vs temperature.

---

## Key Trends

- **Lattice parameter** increases with both temperature and Pt content (Vegard-like behaviour).
- **CTE** drops sharply from Fe (1.47 × 10⁻⁵ K⁻¹) with Pt alloying:
  - Minimum at x(Pt) = 0.75 (FePt₃): α ≈ 7.11 × 10⁻⁶ K⁻¹
  - Slight recovery toward pure Pt: α ≈ 7.58 × 10⁻⁶ K⁻¹
- **Relative expansion** Δa/a₀ — pure Fe expands ~1.3% from 300→1200 K, Pt-rich alloys significantly less.

---

## How to Run

1. Open **MATLAB R2022b or newer** on Windows.
2. Set the project root as the **Current Folder**:

   ```
   C:\проекты\Nikolay\
   ```

3. Run the analysis script:

   ```matlab
   >> scripts\phase4_analysis.m
   ```

   or drag `scripts/phase4_analysis.m` into the MATLAB Editor and click **Run**.

All output (5 PNG figures + `phase4_summary.csv`) is written to `output_v4/`.

---

## File Structure

```
C:\проекты\Nikolay\
├── scripts\
│   └── phase4_analysis.m       ← MATLAB analysis script
├── output_v4\
│   ├── all_results.csv
│   ├── integrity_check_v4.txt
│   ├── a_vs_T_all.png          ← Plot 1
│   ├── a_vs_T_facets.png       ← Plot 2
│   ├── a_vs_xPt.png            ← Plot 3
│   ├── cte_vs_xPt.png          ← Plot 4
│   ├── delta_a_percent.png     ← Plot 5
│   └── phase4_summary.csv      ← Condensed results
└── README_phase4.md            ← This file
```

---

## Summary Table (`phase4_summary.csv`)

| Column | Description |
|--------|-------------|
| `x_Pt` | Pt fraction |
| `Delta_a_Angstrom` | Total variation a_max − a_min over [300, 1200] K |
| `Alpha_eff_K-1` | Effective CTE: α = Δa / a₀ / ΔT |
