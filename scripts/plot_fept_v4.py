#!/usr/bin/env python3
"""Plot Phase 4 Fe-Pt results: a(T), a(comp), facets."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, math

PROJ = "/mnt/c/проекты/Nikolay"
os.chdir(PROJ)
OUT = f"{PROJ}/output_v4"

# Read Phase 4 CSV
with open(f"{OUT}/all_results.csv") as f:
    lines = f.readlines()
hdr = lines[0].strip().split(",")
v4 = {}
for line in lines[1:]:
    parts = line.strip().split(",")
    d = dict(zip(hdr, parts))
    x = float(d['x_Pt'])
    T = int(d['T_K'])
    v4[(x, T)] = {
        'a': float(d['a_mean_Angstrom']),
        'std': float(d['a_std_Angstrom']),
        'n': int(d['n_points']),
        'p': float(d['mean_press_bar']),
    }

COMPS = sorted(set(k[0] for k in v4.keys()))
TEMPS = sorted(set(k[1] for k in v4.keys()))

# ── 1. a(T) all comps ──
fig, ax = plt.subplots(figsize=(10, 7))
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
for ci, x in enumerate(COMPS):
    pts = [(T, v4[(x, T)]['a']) for T in TEMPS if (x, T) in v4]
    if pts:
        pts.sort()
        ts, avs = zip(*pts)
        ax.plot(ts, avs, 'o-', color=colors[ci], label=f"FeP{'' if x==0 else 't'}{'$_{'+ (f'{1/x:.0f}' if x<1 else '') +'}$' if x not in (0,1) else ''}: x_Pt={x:.2f}", markersize=7, linewidth=2)
        # Add std bars
        errs = [v4[(x, T)]['std'] for T in TEMPS if (x, T) in v4]
        ax.fill_between(ts, [a-s for a,s in zip(avs, errs)], [a+s for a,s in zip(avs, errs)], alpha=0.15, color=colors[ci])

ax.set_xlabel("Temperature (K)", fontsize=12)
ax.set_ylabel("Lattice parameter a (Å)", fontsize=12)
ax.set_title("Fe-Pt Thermal Expansion — Phase 4 (Long Protocol)", fontsize=14, fontweight='bold')
ax.legend(fontsize=10, loc='upper left')
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(f"{OUT}/a_vs_T_all_v4.png", dpi=150)
plt.close()
print(f"✅ a_vs_T_all_v4.png")

# ── 2. a(comp) at fixed T ──
fig, ax = plt.subplots(figsize=(10, 7))
for Ti, T in enumerate(TEMPS):
    pts = [(x, v4[(x, T)]['a']) for x in COMPS if (x, T) in v4]
    if pts:
        pts.sort()
        xs, avs = zip(*pts)
        ax.plot(xs, avs, 'o-', label=f"T={T}K", markersize=8, linewidth=2)

ax.set_xlabel("Pt fraction x_Pt", fontsize=12)
ax.set_ylabel("Lattice parameter a (Å)", fontsize=12)
ax.set_title("Fe-Pt a(comp) at fixed temperatures — Phase 4 (Long Protocol)", fontsize=14, fontweight='bold')
ax.legend(fontsize=10)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(f"{OUT}/a_vs_comp_v4.png", dpi=150)
plt.close()
print(f"✅ a_vs_comp_v4.png")

# ── 3. Facets 2×3 ──
fig, axes = plt.subplots(2, 3, figsize=(14, 9))
fig.suptitle("Fe-Pt Thermal Expansion — Phase 4 (Long Protocol)", fontsize=14, fontweight='bold')
axes_flat = axes.flatten()
for ci, x in enumerate(COMPS):
    ax = axes_flat[ci]
    pts = [(T, v4[(x, T)]) for T in TEMPS if (x, T) in v4]
    if pts:
        pts.sort()
        ts, vs = zip(*pts)
        avs = [v['a'] for v in vs]
        errs = [v['std'] for v in vs]
        ax.errorbar(ts, avs, yerr=errs, fmt='o-', color=colors[ci], capsize=4, markersize=6)
        rise = avs[-1] - avs[0]
        alpha_eff = rise / avs[0] / 900
        comp_name = f"Fe (x_Pt=0)" if x == 0 else f"Fe$_{int(1/(x))}$Pt" if x < 1 else "Pt"
        ax.set_title(f"{comp_name}\nΔa={rise:.4f}Å α={alpha_eff:.2e}", fontsize=10)
        ax.set_xlabel("T (K)", fontsize=9)
        ax.set_ylabel("a (Å)", fontsize=9)
        ax.grid(alpha=0.3)

# Hide empty facet
for i in range(len(COMPS), len(axes_flat)):
    axes_flat[i].set_visible(False)

plt.tight_layout()
plt.savefig(f"{OUT}/a_vs_T_facets_v4.png", dpi=150)
plt.close()
print(f"✅ a_vs_T_facets_v4.png")
print("All plots done.")
