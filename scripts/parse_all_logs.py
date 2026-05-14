#!/usr/bin/env python
"""Parse all existing LAMMPS logs and build calibration table."""
import sys, glob, json

# Load parse_log from the main script
with open('scripts/run_pt_calibration_v3.py') as f:
    src = f.read()

# Extract parse_log function
exec(src.split('if __name__')[0])

logs = sorted(glob.glob('output_v3/logs/log_*.lmp'))
print(f'Total logs: {len(logs)}')

results = []
failed = []
for lp in logs:
    fname = lp.split('/')[-1]
    parsed = parse_log(lp)
    ok = parsed.get('n_points', 0) > 0 and parsed.get('a_mean') is not None
    if ok:
        results.append((fname, parsed))
    else:
        failed.append((fname, parsed))

# Print header
header = f"{'Tag':<40} {'a_mean':<10} {'a_std':<10} {'n_points':<8} {'P_mean':<10} {'Type':<6}"
print('=' * len(header))
print(header)
print('=' * len(header))

for fname, p in results:
    tag = fname.replace('log_', '').replace('.lmp', '')
    pm = p.get('mean_press', 'N/A')
    if pm is not None and pm != 'N/A':
        pm_str = f'{pm:.1f}'
    else:
        pm_str = 'N/A'
    
    # Determine type
    if 'long' in tag:
        t = 'long'
    elif 'aniso' in tag:
        t = 'aniso'
    else:
        t = 'short'
    
    print(f"{tag:<40} {p['a_mean']:<10.6f} {p['a_std']:<10.6f} {p['n_points']:<8} {pm_str:<10} {t:<6}")

print(f'\nFailed: {len(failed)}')
for fname, p in failed:
    print(f'  {fname}: {p}')
