#!/usr/bin/env python3
"""Plot Pt calibration v3 results."""
import os, re, math
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJ = "/mnt/c/проекты/Nikolay"
OUT = f"{PROJ}/output_v3"
NATOMS = 256

def parse_log(logpath):
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return None
    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    in_prod = False
    a_vals = []
    for line in text.split('\n'):
        s = line.strip()
        if 'PRODUCTION_START' in s: in_prod = True; continue
        if 'PRODUCTION_DONE' in s: in_prod = False; break
        if in_prod and s and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 9:
                try:
                    vol = float(parts[5])
                    a = (vol * 4 / NATOMS) ** (1/3)
                    a_vals.append(a)
                except: pass
    if not a_vals: return None
    return {'a_mean': sum(a_vals)/len(a_vals), 'n': len(a_vals)}

logs_dir = f"{OUT}/logs"
results = {}
for fname in sorted(os.listdir(logs_dir)):
    if fname.startswith("log_") and fname.endswith(".lmp"):
        label = fname[4:-4]
        parsed = parse_log(os.path.join(logs_dir, fname))
        if parsed:
            results[label] = parsed

# ── Group by potential and find 300/1200 pairs ──
potentials = sorted(set(r.split('_')[0] if '_T' in r else r for r in results.keys()))

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
colors = plt.cm.tab10.colors

# Left: CTE comparison
ax = axes[0]
x_positions = []
labels_list = []
cte_list = []
color_list = []
exp_cte = 9.0

for pot_idx, pot_name in enumerate(potentials):
    pairs = defaultdict(dict)
    for label, parsed in results.items():
        if not label.startswith(pot_name): continue
        if '_T300_' in label:
            base = label.replace('_T300_', '_TX_')
            pairs[base][300] = parsed
        elif '_T1200_' in label:
            base = label.replace('_T1200_', '_TX_')
            pairs[base][1200] = parsed
    
    # Find longest run from this potential
    best_cte = 0
    best_label = ""
    p300_best = p1200_best = None
    for base_key, pair in sorted(pairs.items()):
        if 300 in pair and 1200 in pair:
            a300 = pair[300]['a_mean']
            delta = pair[1200]['a_mean'] - a300
            cte = delta / (a300 * 900)
            n300 = pair[300]['n']
            n1200 = pair[1200]['n']
            total_n = n300 + n1200
            if cte >= best_cte and total_n == results[base_key.replace('_TX_', '_T300_')]['n']:
                # Prefer longer runs
                if total_n > (results.get(base_key.replace('_TX_', '_T1200_'), {}) or {}).get('n', 0) + results.get(base_key.replace('_TX_', '_T300_'), {}) or {}).get('n', 0):
                    pass
    
    # Just list CTEs for all meaningful pairs
    for base_key in sorted(pairs.keys()):
        pair = pairs[base_key]
        if 300 in pair and 1200 in pair:
            a300 = pair[300]['a_mean']
            delta = pair[1200]['a_mean'] - a300
            cte = delta / (a300 * 900)
            short = base_key.replace(f'{pot_name}_', '').replace('_TX', '')
            x_positions.append(len(x_positions))
            labels_list.append(f"{pot_name[:3]}\n{short[:12]}")
            cte_list.append(cte * 1e6)
            color_list.append(colors[pot_idx % len(colors)])

# Bar chart
bars = ax.bar(x_positions, cte_list, color=color_list, alpha=0.7)
ax.axhline(exp_cte, color='r', ls='--', lw=2, label=f'α_experimental = {exp_cte}×10⁻⁶')
ax.set_xticks(x_positions)
ax.set_xticklabels(labels_list, fontsize=7, rotation=45, ha='right')
ax.set_ylabel('CTE (×10⁻⁶ K⁻¹)')
ax.set_title('Pt: CTE for different NPT settings')
ax.legend()
ax.grid(ls=':', alpha=0.3)

# Right: CTE vs production length
ax = axes[1]
n_vs_cte = []
for label, parsed in results.items():
    pot = label.split('_')[0]
    if '_T300_' in label and pot in potentials:
        base = label.replace('_T300_', '_TX_')
        T1200_label = f"{pot}_{base.split('_TX_')[1].replace(base.split('_TX_')[1].split('_')[0], 'T1200')}"
        # Try to reconstruct
        t1200_label = label.replace('_T300_', '_T1200_')
        if t1200_label in results:
            a300 = parsed['a_mean']
            a1200 = results[t1200_label]['a_mean']
            delta = a1200 - a300
            cte = delta / (a300 * 900)
            n_vs_cte.append((parsed['n'], cte * 1e6, pot, label))

ax.scatter([n for n, c, p, l in n_vs_cte], 
           [c for n, c, p, l in n_vs_cte],
           c=[colors[potentials.index(p) % len(colors)] for n, c, p, l in n_vs_cte],
           alpha=0.7, s=80)
for n, c, p, l in n_vs_cte:
    ax.annotate(f"{c:.1f}", (n, c), fontsize=6, alpha=0.7)
ax.axhline(exp_cte, color='r', ls='--', lw=2, label=f'α_exp = {exp_cte}×10⁻⁶')
ax.set_xlabel('Production steps')
ax.set_ylabel('CTE (×10⁻⁶ K⁻¹)')
ax.set_title('Pt: CTE vs production length')
ax.legend()
ax.grid(ls=':', alpha=0.3)
ax.set_xscale('log')

plt.tight_layout()
plt.savefig(f"{OUT}/pt_calibration_v3.png", dpi=150)
print(f"✓ {OUT}/pt_calibration_v3.png")
plt.close()
