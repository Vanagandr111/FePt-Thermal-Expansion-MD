#!/usr/bin/env python3
"""Regenerate plots from existing CSV with updated make_plots()."""
import sys, os, csv

PROJDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJDIR, 'scripts'))

import lmp_helper as lmp

csv_path = os.path.join(PROJDIR, 'output_v4', 'all_results_v4_turbo.csv')
seed = 100101

parsed_all = {}
comps_set = set()
temps_set = set()

with open(csv_path, 'r') as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        comp = float(row['x_Pt'])
        T = int(row['T_K'])
        parsed_all[(comp, T)] = {
            'a_mean': float(row['a_mean_Angstrom']),
            'a_std': float(row['a_std_Angstrom']),
            'n_points': int(row['n_points']),
            'drift': float(row['drift']),
            'mean_press_bar': float(row['mean_press_bar']),
            'std_press_bar': float(row['std_press_bar']),
            'runtime_s': float(row['runtime_s']),
        }
        comps_set.add(comp)
        temps_set.add(T)

comps = sorted(comps_set)
temps = sorted(temps_set)
print(f"Compositions: {comps}")
print(f"Temperatures: {temps}")
print(f"Data points: {len(parsed_all)}")

out_dir = os.path.join(PROJDIR, 'output_v4')
lmp.make_plots(parsed_all, comps, temps, seed, out_dir,
               title_prefix='Fe-Pt (turbo)')
print("All plots regenerated successfully!")

# Check file sizes
for fn in ['a_vs_T_all.png', 'a_vs_comp.png', 'a_vs_T_facets.png']:
    fpath = os.path.join(out_dir, fn)
    if os.path.isfile(fpath):
        size = os.path.getsize(fpath)
        print(f"  {fn}: {size} bytes")
    else:
        print(f"  {fn}: MISSING!")
