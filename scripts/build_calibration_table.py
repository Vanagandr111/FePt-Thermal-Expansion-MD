#!/usr/bin/env python
"""Build complete Pt calibration matrix from parsed logs."""
import sys, glob, json, math

# Load parse_log
with open('scripts/run_pt_calibration_v3.py') as f:
    src = f.read()
exec(src.split('if __name__')[0])

logs = sorted(glob.glob('output_v3/logs/log_*.lmp'))

EXP_CTE = 9.0e-6

# Parse all
results = {}
for lp in logs:
    fname = lp.split('/')[-1]
    tag = fname.replace('log_', '').replace('.lmp', '')
    parsed = parse_log(lp)
    if parsed and parsed.get('n_points', 0) > 0 and parsed.get('a_mean') is not None:
        results[tag] = parsed

# Classify
def classify(tag):
    if 'long' in tag: return 'long'
    if 'aniso' in tag: return 'aniso'
    return 'short'

# Group by (pot, mode)
pairs = {}
for tag, p in results.items():
    if 'aniso' in tag: continue
    # Extract pot and mode
    parts = tag.split('_')
    pot = parts[0]  # eam or meam
    # Determine short/long
    mode = 'long' if 'long' in tag else 'short'
    pdamp = None
    T = None
    for pp in parts:
        if pp.startswith('pdamp'):
            pdamp = float(pp.replace('pdamp', ''))
        if pp.startswith('T'):
            T = int(pp.replace('T', ''))
    key = (pot, mode, pdamp)
    if key not in pairs:
        pairs[key] = {}
    pairs[key][T] = p

# Build table
header = f"{'Pot':<8} {'Mode':<6} {'Pdamp':<6} {'a300':<10} {'a1200':<10} {'d_a':<10} {'CTE':<12} {'CTE/exp':<10} {'n300':<6} {'n1200':<6} {'P300':<10} {'P1200':<10} {'std300':<10} {'std1200':<10}"
print('=' * len(header))
print(header)
print('=' * len(header))

rows = []
for (pot, mode, pdamp), temps in sorted(pairs.items()):
    if 300 not in temps or 1200 not in temps:
        continue
    a300 = temps[300]['a_mean']
    a1200 = temps[1200]['a_mean']
    da = a1200 - a300
    cte = da / a300 / 900
    cte_ratio = cte / EXP_CTE
    
    n300 = temps[300]['n_points']
    n1200 = temps[1200]['n_points']
    p300 = temps[300].get('mean_press', None) or 0
    p1200 = temps[1200].get('mean_press', None) or 0
    s300 = temps[300]['a_std']
    s1200 = temps[1200]['a_std']
    
    row = f"{pot:<8} {mode:<6} {pdamp:<6.1f} {a300:<10.6f} {a1200:<10.6f} {da:<10.6f} {cte:<12.3e} {cte_ratio:<10.3f} {n300:<6} {n1200:<6} {p300:<10.1f} {p1200:<10.1f} {s300:<10.6f} {s1200:<10.6f}"
    rows.append((cte_ratio, row))
    print(row)

print('=' * len(header))
