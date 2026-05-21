#!/usr/bin/env python
"""
run_phase4.py — Phase 4 Long Protocol main run.
Windows-first. Output -> output_v4/.

Protocol: 50k equilibration + 100k production, Tdamp=1.0, Pdamp=10.0.
Potential: MEAM PtFe.meam.
Grid: 5 comps x 4 temps = 20 points.
Production averaging for final a(T).

Usage:
    python scripts/run_phase4.py                  # auto seed
    python scripts/run_phase4.py --seed 12345     # manual seed
    python scripts/run_phase4.py --seed           # re-use last seed
    python scripts/run_phase4.py --force          # clean 20/20 rerun all

# module-purpose: Sequential Phase 4 Long Protocol runner (output_v4/)
# entry-points: main()
# main-flows:
#   1. resolve seed -> generate structures -> run 20 points sequentially
#   2. parse production -> write CSV + integrity check + plots
# related-modules: lmp_helper (find_lmp, run_lmp, parse_production, write_csv,
#                               write_protocol_log, make_plots, integrity_check)
#                  seed_manager (get_or_create_seed, write_seed_info)
"""
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)

if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import lmp_helper as lmp
import seed_manager as seed_mgr

# -- Parameters --
# intent: MD simulation parameters shared by the long protocol
# sidefx: none
# purity: pure
COMPOSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 600, 900, 1200]
NATOMS = 256
EQ_STEPS = 50000
PROD_STEPS = 100000
TDAMP = 1.0
PDAMP = 10.0
OUT = os.path.join(_PROJ_DIR, 'output_v4')
LOGS = os.path.join(OUT, 'logs')
POT_LINE = "pair_coeff      * * potentials{0}library.meam Fe Pt potentials{0}PtFe.meam Fe Pt".format(os.sep)

# -- Seed --
SEED_FINAL = 12345

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
FORCE = '--force' in sys.argv


def run_point(datafile, comp, T, subdir):
    """
    Run LAMMPS at single T using lmp_helper.

    # intent: Single LAMMPS run for one composition-temperature point
    # allies: main() (called per point), lmp.run_lmp, lmp.write_input,
    #         lmp.extract_result_from_stdout, lmp.extract_result_from_log
    # sidefx: io (writes LAMMPS log + input file)
    # purity: impure
    # errors: returns None on LAMMPS failure / parse failure
    """
    os.makedirs(subdir, exist_ok=True)
    logfile = os.path.join(subdir, "log_{:.2f}_{}.lmp".format(comp, T))
    infile = lmp.write_input(datafile, comp, T, OUT, POT_LINE,
                              EQ_STEPS, PROD_STEPS, TDAMP, PDAMP, SEED_FINAL)

    print("  T={}K...".format(T), end="", flush=True)
    t0 = time.time()
    result = lmp.run_lmp(infile, logfile=logfile, timeout=900)
    dt = time.time() - t0

    r = lmp.extract_result_from_stdout(result)
    if r:
        print(" a={:.6f}A [{:.0f}s]".format(r['a'], dt))
        r['time'] = dt
        return r

    r = lmp.extract_result_from_log(logfile)
    if r:
        print(" a={:.6f}A (log) [{:.0f}s]".format(r['a'], dt))
        r['time'] = dt
        return r

    print(" FAILED [{}s]".format(dt))
    return None


def main():
    """
    # intent: Orchestrate Phase 4 Long Protocol -- 20 MD runs, analysis, output
    # allies: run_point, lmp.*, seed_mgr.*
    # sidefx: io (writes output_v4/ with CSVs, logs, plots, integrity)
    # purity: impure
    # errors: returns 0 on success, 1 on LAMMPS not found or failures
    """
    print('=' * 60)
    print('  Fe-Pt Phase 4 -- Long Protocol (MEAM)')
    print('  Protocol: {} eq + {} prod, Tdamp={}, Pdamp={}'.format(EQ_STEPS, PROD_STEPS, TDAMP, PDAMP))
    print('  Grid: {} comps x {} temps = {} points'.format(
        len(COMPOSITIONS), len(TEMPS), len(COMPOSITIONS) * len(TEMPS)))
    print('  Output: ' + OUT)

    lmp_path = lmp.find_lmp_display()
    print('  LAMMPS: ' + (lmp_path or 'NOT FOUND'))
    print('=' * 60)

    if not lmp.find_lmp():
        print('\nERROR: lmp.exe not found')
        return 1

    # Clean if --force
    if FORCE and os.path.exists(OUT):
        import shutil
        shutil.rmtree(OUT)

    os.makedirs(LOGS, exist_ok=True)

    # Seed
    global SEED_FINAL
    SEED_FINAL, seed_source = seed_mgr.get_or_create_seed(
        _PROJ_DIR, OUT,
        manual_seed=SEED_ARG if SEED_ARG not in (None, -1) else None,
        reuse_last=REUSE_SEED or SEED_ARG == -1,
        resume=RESUME,
    )
    seed_mgr.write_seed_info(OUT, SEED_FINAL, "phase4", seed_source)

    # Protocol log
    lmp.write_protocol_log(OUT, 'run_phase4.py', EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                           COMPOSITIONS, TEMPS, SEED_FINAL,
                           proto_name='run_main_protocol.txt')

    # Generate structures
    print('\nGenerating structures...')
    for comp in COMPOSITIONS:
        lmp.gen_structure(comp)
    print('  Structures OK')

    # Run all 20 points
    results = {}
    total_start = time.time()
    for i, comp in enumerate(COMPOSITIONS):
        for T in TEMPS:
            label = '[{}/{}] x_Pt={:.2f} T={}K'.format(
                i * 4 + TEMPS.index(T) + 1,
                len(COMPOSITIONS) * len(TEMPS), comp, T)
            print('\n  ' + label)
            datafile = os.path.join(lmp.DATA_DIR, 'data.fept_c{:.2f}.lmp'.format(comp))
            r = run_point(datafile, comp, T, LOGS)
            if r:
                p = lmp.parse_production(os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T)), NATOMS)
                p['runtime'] = r.get('time', 0)
            else:
                p = {'n_points': 0, 'a_mean': None, 'runtime': 0}
            results[(comp, T)] = p

    total = time.time() - total_start
    print('\n\nTotal time: {:.1f} min'.format(total / 60))

    # Results table
    print('\n' + '=' * 95)
    print('  RESULTS (seed={})'.format(SEED_FINAL))
    print('=' * 95)
    hdr = '{:>6} {:>5} {:>11} {:>9} {:>6} {:>9} {:>9}'.format(
        'x_Pt', 'T', 'a_mean', 'a_std', 'n', 'drift', 'time')
    print(hdr)
    print('-' * 95)
    for comp in COMPOSITIONS:
        for T in TEMPS:
            p = results.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                print('{:>6.2f} {:>5} {:>11.6f} {:>9.6f} {:>6} {:>9.2e} {:>5.0f}s'.format(
                    comp, T, p['a_mean'], p.get('a_std', 0),
                    p['n_points'], p.get('drift', 0), p.get('runtime', 0)))
            else:
                print('{:>6.2f} {:>5} {:>11}'.format(comp, T, 'NO DATA'))

    # Trends
    lmp.print_trends(results, COMPOSITIONS, TEMPS, SEED_FINAL)

    # CSV
    lmp.write_csv(results, COMPOSITIONS, TEMPS, OUT, SEED_FINAL)

    # Integrity
    lmp.integrity_check(results, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                        EQ_STEPS, PROD_STEPS, TDAMP, PDAMP)

    # Plots (using shared make_plots from lmp_helper)
    try:
        lmp.make_plots(results, COMPOSITIONS, TEMPS, SEED_FINAL, OUT,
                       a_vs_T_fn='a_vs_T_all.png',
                       a_vs_T_facets_fn='a_vs_T_facets.png')
    except Exception as e:
        print('  Plot error: {}'.format(e))

    # Summary
    ok = sum(1 for p in results.values() if p and p.get('a_mean') is not None)
    fail = len(COMPOSITIONS) * len(TEMPS) - ok
    print('\n' + '=' * 60)
    if fail == 0:
        print('  COMPLETE -- All {} points verified (seed={})'.format(ok, SEED_FINAL))
    else:
        print('  {} OK, {} FAILURES (seed={})'.format(ok, fail, SEED_FINAL))
    print('  Output: ' + OUT)
    print('  Seed info: seed_info.txt')
    print('=' * 60)

    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
