#!/usr/bin/env python
"""
run_main.py -- Fe-Pt MD Thermal Expansion single calculation engine.
Output: results/  (one folder, full 1002-point production logs)
Protocol: 50k equilibration + 100k production, Tdamp=1.0, Pdamp=10.0
Potential: MEAM PtFe.meam
Grid: 5 compositions x 4 temperatures = 20 points
Windows-only. No WSL. No hardcoded Linux paths.

Usage:
    python scripts/run_main.py                       # auto seed
    python scripts/run_main.py --seed 12345           # manual seed
    python scripts/run_main.py --seed                 # re-use last seed

# module-purpose: Main sequential MD runner (results/ output dir)
# entry-points: main()
# main-flows:
#   1. resolve seed -> generate structures -> run 20 points -> parse -> report
#   2. write CSV + CTE report + plots to results/
# related-modules: lmp_helper, seed_manager
"""
import os
import sys
import time
import math

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_THIS = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_THIS)

if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

import lmp_helper as lmp
import seed_manager as seed_mgr

# -- Parameters --
# intent: MD simulation parameters for the main sequential runner
# sidefx: none
# purity: pure
COMP = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 500, 700, 900, 1100, 1200]
NATOMS = 2048
EQ = 50000
PROD = 100000
TDAMP = 1.0
PDAMP = 10.0

OUT = os.path.join(_PROJ, 'results')
LOGS = os.path.join(OUT, 'logs')
PLOTS = os.path.join(OUT, 'plots')
INS = os.path.join(OUT, 'input')
POT_LINE = "pair_coeff      * * potentials\\library.meam Fe Pt potentials\\PtFe.meam Fe Pt"

os.makedirs(LOGS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)
os.makedirs(INS, exist_ok=True)

# -- Seed management --
SEED_ARG = None
for i, arg in enumerate(sys.argv):
    if arg == '--seed':
        if i + 1 >= len(sys.argv):
            SEED_ARG = -1
            break
        try:
            SEED_ARG = int(sys.argv[i + 1])
        except ValueError:
            SEED_ARG = -1
        break
REUSE_SEED = '--reuse-seed' in sys.argv
RESUME = '--resume' in sys.argv

SEED, SEED_SOURCE = seed_mgr.get_or_create_seed(
    _PROJ, OUT,
    manual_seed=SEED_ARG if SEED_ARG not in (None, -1) else None,
    reuse_last=REUSE_SEED or SEED_ARG == -1,
    resume=RESUME,
)
seed_mgr.write_seed_info(OUT, SEED, "main", SEED_SOURCE)


# intent: Run full Phase 4 simulation sweep (compositions × temperatures)
# allies: lmp_helper, seed_manager
# sidefx: io (writes logs, CSVs, plots to output_v4/)
# purity: impure
# errors: returns 0 on success, 1 on failure
def main():
    """
    # intent: Orchestrate 20-point sequential MD run with CSV + plots output
    # allies: lmp.*, seed_mgr.*
    # sidefx: io (writes results/ with logs, CSVs, plots)
    # purity: impure
    # errors: returns 0 on success, 1 on LAMMPS not found
    """
    print('=' * 60)
    print('  Fe-Pt MD Thermal Expansion')
    print('  Protocol: {} eq + {} prod, Tdamp={}, Pdamp={}'.format(EQ, PROD, TDAMP, PDAMP))
    print('  Seed: {} ({})'.format(SEED, SEED_SOURCE))
    print('  Grid: {} comps x {} temps = {} points'.format(
        len(COMP), len(TEMPS), len(COMP) * len(TEMPS)))
    print('  Output: ' + OUT)
    lmp_path = lmp.find_lmp_display()
    print('  LAMMPS: ' + (lmp_path or 'NOT FOUND'))
    print('=' * 60)

    if not lmp.find_lmp():
        print('\nERROR: lmp.exe not found in bin/ or PATH')
        return 1

    # Cleanup old files if not resuming
    if not RESUME:
        for f in os.listdir(LOGS):
            if f.endswith('.lmp'):
                os.remove(os.path.join(LOGS, f))
        for f in os.listdir(PLOTS):
            if f.endswith('.png'):
                os.remove(os.path.join(PLOTS, f))
        print('  Cleaned old logs and PNGs')

    # Generate structures
    print('\nGenerating structures...')
    for comp in COMP:
        lmp.gen_structure(comp)
    print('  Structures OK')

    # Protocol log
    lmp.write_protocol_log(OUT, 'run_main.py', EQ, PROD, TDAMP, PDAMP,
                           COMP, TEMPS, SEED, proto_name='run_protocol.txt')

    # Run all 20 points sequentially
    results = {}
    total_start = time.time()
    for i, comp in enumerate(COMP):
        for T in TEMPS:
            label = '[{}/{}] x_Pt={:.2f} T={}K'.format(i * len(TEMPS) + TEMPS.index(T) + 1, len(COMP) * len(TEMPS), comp, T)
            print('\n  ' + label)
            datafile = os.path.join(lmp.DATA_DIR, 'data.fept_c{:.2f}.lmp'.format(comp))
            logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
            infile = lmp.write_input(datafile, comp, T, OUT, POT_LINE,
                                      EQ, PROD, TDAMP, PDAMP, SEED)

            t0 = time.time()
            r = lmp.run_lmp(infile, logfile=logfile)
            dt = time.time() - t0

            p = lmp.parse_production(logfile, NATOMS)
            if p and p.get('a_mean') is not None:
                print('    a={:.6f} n={} t={:.0f}s'.format(p['a_mean'], p['n_points'], dt))
            else:
                print('    FAILED t={:.0f}s'.format(dt))
                if not r.get('ok') and r.get('stderr'):
                    print('    stderr: ' + r['stderr'][:200])
            p['runtime'] = dt
            results[(comp, T)] = p

    total = time.time() - total_start
    print('\n\nTotal time: {:.1f} min'.format(total / 60))

    # Results table
    print('\n' + '=' * 95)
    print('  RESULTS (seed={})'.format(SEED))
    print('=' * 95)
    hdr = '{:>6} {:>5} {:>11} {:>9} {:>6} {:>9} {:>9}'.format(
        'x_Pt', 'T', 'a_mean', 'a_std', 'n', 'drift', 'time')
    print(hdr)
    print('-' * 95)
    for comp in COMP:
        for T in TEMPS:
            p = results.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                print('{:>6.2f} {:>5} {:>11.6f} {:>9.6f} {:>6} {:>9.2e} {:>5.0f}s'.format(
                    comp, T, p['a_mean'], p.get('a_std', 0),
                    p['n_points'], p.get('drift', 0), p.get('runtime', 0)))
            else:
                print('{:>6.2f} {:>5} {:>11}'.format(comp, T, 'NO DATA'))

    # Trends
    lmp.print_trends(results, COMP, TEMPS, SEED)

    # CSV
    lmp.write_csv(results, COMP, TEMPS, OUT, SEED)

    # Pt benchmark
    pt300 = results.get((1.0, 300), {})
    pt1200 = results.get((1.0, 1200), {})
    if pt300.get('a_mean') and pt1200.get('a_mean'):
        alpha_pt = (pt1200['a_mean'] - pt300['a_mean']) / pt300['a_mean'] / 900
        print('\n  --- Pt Benchmark (seed={}) ---'.format(SEED))
        print('  a(300K) = {:.6f} (expected ~3.929)'.format(pt300['a_mean']))
        print('  a(1200K) = {:.6f} (expected ~3.956)'.format(pt1200['a_mean']))
        print('  a_Pt = {:.3e} (expected ~7.5e-6)'.format(alpha_pt))

    # CTE report CSV -- using lmp helper
    lmp.write_cte_csv(results, COMP, TEMPS, OUT)

    # Plots (via shared make_plots)
    try:
        lmp.make_plots(results, COMP, TEMPS, SEED, PLOTS)
    except Exception as e:
        print('  Plot error: ' + str(e))

    # Summary
    ok = sum(1 for p in results.values() if p and p.get('a_mean') is not None)
    fail = 20 - ok
    print('\n' + '=' * 60)
    if fail == 0:
        print('  COMPLETE -- All {} points verified (seed={})'.format(ok, SEED))
    else:
        print('  {} OK, {} FAILURES (seed={})'.format(ok, fail, SEED))
    print('  Output: ' + OUT)
    print('  Seed info: seed_info.txt')
    print('=' * 60)


if __name__ == '__main__':
    sys.exit(main())
