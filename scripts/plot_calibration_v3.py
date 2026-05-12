#!/usr/bin/env python3
"""Plot Pt calibration results vs reference."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, math

PROJ = "/mnt/c/проекты/Nikolay"
os.chdir(PROJ)

# Parse CSV
with open("output_v3/pt_calibration_matrix.csv") as f:
    lines = f.readlines()
header = lines[0].strip().split(",")
rows = []
for line in lines[1:]:
    parts = line.strip().split(",")
    d = dict(zip(header, parts))
    rows.append(d)

EXP_CTE = 9.0e-6

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("Pt Thermal Expansion — Calibration v3", fontsize=14, fontweight='bold')

# Left: CTE by run configuration
ax = axes[0]
short_eam, long_eam = [], []
short_meam, long_meam = [], []
for r in rows:
    if 'aniso' in r['label']: continue
    a300 = float(r['T_K']) == 300
    a1200 = float(r['T_K']) == 1200
    # Only use pairs
    label = r['label']
    T = int(r['T_K'])
    if T != 300: continue  # de-duplicate, use 300 as base per run
    
    tag = label.replace('_T300', '')
    # Find corresponding 1200
    twin = label.replace('T300', 'T1200')
    tr = None
    for rr in rows:
        if rr['label'] == twin:
            tr = rr
            break
    if tr is None: continue
    
    a300v = float(r['a_mean_Angstrom'])
    a1200v = float(tr['a_mean_Angstrom'])
    da = a1200v - a300v
    cte = da / a300v / 900
    cte_ratio = cte / EXP_CTE
    
    pot = r['pot']
    mode = 'long' if 'long' in label else 'short'
    color = 'C0' if pot == 'eam_u3' else 'C1'
    marker = 'o' if mode == 'long' else 's'
    size = 120 if mode == 'long' else 60
    
    ax.scatter(tag, cte_ratio, color=color, marker=marker, s=size, zorder=5, 
               label=f"{pot}_{mode}" if not (short_eam and long_eam and short_meam and long_meam) else "")

ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.7, label='Exp CTE (9e-6)')
ax.set_ylabel("CTE / Experimental")
ax.set_xlabel("Run configuration")
ax.tick_params(axis='x', rotation=45)
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

# Right: a300 vs a1200 scatter
ax2 = axes[1]
for r in rows:
    T = int(r['T_K'])
    if T != 300: continue
    label = r['label']
    twin = label.replace('T300', 'T1200')
    tr = None
    for rr in rows:
        if rr['label'] == twin:
            tr = rr
            break
    if tr is None: continue
    
    a300v = float(r['a_mean_Angstrom'])
    a1200v = float(tr['a_mean_Angstrom'])
    pot = r['pot']
    mode = 'long' if 'long' in label else 'short'
    
    color = 'C0' if pot == 'eam_u3' else 'C1'
    marker = 'o' if mode == 'long' else 's'
    
    # Draw thermal expansion line
    ax2.plot([a300v, a1200v], [300, 1200], color=color, alpha=0.3, linewidth=0.5)
    ax2.scatter(a300v, 300, color=color, marker=marker, s=50)
    ax2.scatter(a1200v, 1200, color=color, marker=marker, s=50)

# Expected
exp_a300 = 3.92
exp_a1200 = 3.96
ax2.axvline(x=exp_a300, color='gray', linestyle=':', alpha=0.5)
ax2.axvline(x=exp_a1200, color='gray', linestyle=':', alpha=0.5)

ax2.set_xlabel("Lattice parameter a (Å)")
ax2.set_ylabel("Temperature (K)")
ax2.set_title("a(T) for each configuration")
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("output_v3/pt_md_vs_cte_reference.png", dpi=150)
plt.close()
print("✅ pt_md_vs_cte_reference.png")
