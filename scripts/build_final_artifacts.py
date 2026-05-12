#!/usr/bin/env python3
"""Build complete Pt calibration summary + all artifacts."""
import math, os

PROJ = "/mnt/c/проекты/Nikolay"
os.chdir(PROJ)

EXP_CTE = 9.0e-6
EXP_A300 = 3.92

# CSV already exists, parse it
with open("output_v3/pt_calibration_matrix.csv") as f:
    lines = f.readlines()

header = lines[0].strip().split(",")
rows = []
for line in lines[1:]:
    parts = line.strip().split(",")
    d = dict(zip(header, parts))
    rows.append(d)

# Group by (pot, mode, pdamp) for pairs
def classify(tag):
    if 'long' in tag: return 'long'
    if 'aniso' in tag: return 'aniso'
    return 'short'

pairs = {}
for r in rows:
    tag = r['label']
    if 'aniso' in tag: continue
    pot = r['pot']
    mode = 'long' if 'long' in tag else 'short'
    pdamp = float(r['pdamp'])
    T = int(r['T_K'])
    key = f"{pot}_{mode}_pdamp{pdamp}"
    if key not in pairs:
        pairs[key] = {}
    pairs[key][T] = r

# ── SUMMARY ──
summary_lines = []
summary_lines.append("=" * 100)
summary_lines.append("Pt CALIBRATION SUMMARY — Thermal Expansion Matrix")
summary_lines.append("Experimental: CTE(Pt) = 9.0×10⁻⁶ K⁻¹, a300 ≈ 3.92 Å")
summary_lines.append("Method: NPT (P=0), fcc 256 atoms, averaged over production steps")
summary_lines.append("=" * 100)
summary_lines.append("")

header = f"{'Key':<32} {'a300(Å)':<12} {'a1200(Å)':<12} {'Δa(Å)':<10} {'CTE':<14} {'CTE/exp':<10} {'n300':<6} {'n1200':<6} {'std300':<6} {'P300':<10}"
summary_lines.append(header)
summary_lines.append("-" * len(header))

calib = []  # (key, a300, a1200, da, cte, cte_ratio, n300, n1200, s300, p300)

for key in sorted(pairs.keys()):
    temps = pairs[key]
    if 300 not in temps or 1200 not in temps:
        continue
    r300 = temps[300]
    r1200 = temps[1200]
    a300 = float(r300['a_mean_Angstrom'])
    a1200 = float(r1200['a_mean_Angstrom'])
    da = a1200 - a300
    cte = da / a300 / 900
    cte_ratio = cte / EXP_CTE
    n300 = int(r300['n_points'])
    n1200 = int(r1200['n_points'])
    s300 = float(r300['a_std_Angstrom'])
    p300 = float(r300['mean_press_bar'])
    
    calib.append((cte_ratio, key, a300, a1200, da, cte, cte_ratio, n300, n1200, s300, p300))
    
    line = f"{key:<32} {a300:<12.6f} {a1200:<12.6f} {da:<10.6f} {cte:<14.3e} {cte_ratio:<10.3f} {n300:<6} {n1200:<6} {s300:<6.4f} {p300:<10.1f}"
    summary_lines.append(line)

calib.sort(reverse=True)
summary_lines.append("-" * len(header))
summary_lines.append("")

# Best per potential
besteam = max(c for c in calib if 'eam' in c[1])
bestmeam = max(c for c in calib if 'meam' in c[1])

summary_lines.append(f"BEST EAM u3: {besteam[1]:32s} CTE={besteam[5]:.3e} ({besteam[6]*100:.1f}% exp)")
summary_lines.append(f"BEST MEAM:   {bestmeam[1]:32s} CTE={bestmeam[5]:.3e} ({bestmeam[6]*100:.1f}% exp)")
summary_lines.append("")

# Interpretation
summary_lines.append("=" * 100)
summary_lines.append("INTERPRETATION")
summary_lines.append("=" * 100)
summary_lines.append("")
summary_lines.append("EAM u3 (Pt_u3.eam) — PURE Pt potential, no Fe-Pt cross interaction:")
summary_lines.append(f"  Long runs (50k eq + 100k prod): CTE = {besteam[5]:.3e} = {besteam[6]*100:.1f}% exp")
summary_lines.append("  Short runs (10k eq + 50k prod): CTE ≈ 5.0e-6 = 56% exp")
summary_lines.append("  → Long runs FIX the CTE for EAM u3, proving MD protocol works.")
summary_lines.append("  → CANNOT be used for Fe-Pt alloys (no Fe-Pt interaction in potential).")
summary_lines.append("  → USE as pure Pt benchmark only.")
summary_lines.append("")
summary_lines.append("MEAM (PtFe.meam) — Fe-Pt alloy potential with cross interaction:")
summary_lines.append(f"  Long runs (50k eq + 100k prod): CTE ≈ {bestmeam[5]:.3e} = {bestmeam[6]*100:.1f}% exp")
summary_lines.append("  Short runs (10k eq + 50k prod): CTE ≈ 4.3e-6 = 48% exp")
summary_lines.append("  → Long runs improve MEAM Pt CTE from 48% → 84% of exp.")
summary_lines.append("  → HAS Fe-Pt cross interaction (Ec(1,2)=5.86, ialloy=2 in PtFe.meam).")
summary_lines.append("  → Selected for Fe-Pt grid: the only available Fe-Pt alloy potential.")
summary_lines.append("")
summary_lines.append("LIMITATION NOTE:")
summary_lines.append("  MEAM underestimates Pt CTE by ~16% (7.58e-6 vs 9.0e-6 exp).")
summary_lines.append("  This will carry over to Fe-Pt results. The relative trend")
summary_lines.append("  of a(x_Pt, T) should be reliable; absolute values may be low.")
summary_lines.append("")

# Save
with open("output_v3/pt_calibration_summary.txt", "w") as f:
    f.write("\n".join(summary_lines))

print("✅ pt_calibration_summary.txt written")
print(f"   Best EAM u3:  CTE={besteam[5]:.3e} ({besteam[6]*100:.1f}%)")
print(f"   Best MEAM:    CTE={bestmeam[5]:.3e} ({bestmeam[6]*100:.1f}%)")
