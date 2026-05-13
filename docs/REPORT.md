# Phase 4 MATLAB Analysis — Status Report

**Project:** Fe–Pt MD Long Runs (LAMMPS)  
**Script:** `scripts/phase4_analysis.m`  
**Generated:** Hermes Agent (WSL / Windows)

---

## MATLAB Script Status

**Status:** Prepared — runtime test pending

The MATLAB script was written and logically verified:

- Column names match `all_results.csv` (`x_Pt`, `T_K`, `a_mean_Angstrom`, `a_std_Angstrom`)
- CTE computation: α = (a_max − a₀) / a₀ / ΔT
- Logic verified against Python emulation (values match expected)

The script was **not executed** on the development machine because MATLAB is not installed (no MathWorks license available).

The script uses only standard MATLAB functions (R2022b+):

- `readtable`, `errorbar`, `subplot`, `saveas`, `table`, `writetable`

### Required for Execution

- MATLAB R2022b or newer installed on Windows
- Project root set as Current Folder: `C:\проекты\Nikolay\`
- Run: `>> scripts\phase4_analysis`

### Generated Output (after successful run)

| File | Description |
|------|-------------|
| `output_v4/a_vs_T_all.png` | a(T) for all compositions, with error bars |
| `output_v4/a_vs_T_facets.png` | Faceted subplots per composition |
| `output_v4/a_vs_xPt.png` | Isothermal cross-sections |
| `output_v4/cte_vs_xPt.png` | CTE vs Pt fraction |
| `output_v4/delta_a_percent.png` | Relative thermal expansion |
| `output_v4/phase4_summary.csv` | Condensed results table |

### Alternative (MATLAB Not Available)

Equivalent Python scripts in `scripts/` (e.g., `plot_fept_v4.py`) produce the same analysis from the same `all_results.csv`.

---

## Conclusion

The MATLAB analysis script is ready for deployment. Final execution must be performed on a target machine with MATLAB installed.
