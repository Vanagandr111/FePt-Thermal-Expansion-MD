#!/usr/bin/env python
"""
run_phase4_turbo.py — Parallel Phase 4 run with auto-detect CPU cores.

TURBO mode:      parallel + neighbor 1.0 bin (50k eq + 100k prod) — NO QUALITY LOSS
TURBO-PLUS mode: parallel + neighbor 1.0 bin + 20k eq + 50k prod — FASTER, slight quality risk

Windows-first. Output -> output_v4/.
Potential: MEAM PtFe.meam.
Grid: 5 comps x 4 temps = 20 points.

Usage:
    python scripts/run_phase4_turbo.py --turbo            # parallel + neighbor fix
    python scripts/run_phase4_turbo.py --turbo-plus       # parallel + neighbor + shorter steps
    python scripts/run_phase4_turbo.py --turbo --force    # force rerun all
    python scripts/run_phase4_turbo.py --help             # show this help

# module-purpose: Parallel Phase 4 runner (turbo/turbo-plus modes)
# entry-points: main(), run_point_worker()
# main-flows:
#   1. parse CLI flags -> resolve seed -> parallel ThreadPoolExecutor
#   2. per-worker: run_point_worker -> parse_production -> aggregate
#   3. write CSV (turbo-specific naming) + integrity + plots
# related-modules: lmp_helper, seed_manager
"""
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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
# intent: Shared MD simulation parameters between turbo/turbo-plus modes
# sidefx: none
# purity: pure
COMPOSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 500, 700, 900, 1100, 1200]
NATOMS = 2048
TDAMP = 1.0
PDAMP = 10.0
POT_LINE = "pair_coeff      * * potentials{0}library.meam Fe Pt potentials{0}PtFe.meam Fe Pt".format(os.sep)

# -- Output dir --
_output_dir_arg = None
for i, arg in enumerate(sys.argv):
    if arg == '--output-dir' and i + 1 < len(sys.argv):
        _output_dir_arg = sys.argv[i + 1]
        break
if _output_dir_arg:
    if os.path.isabs(_output_dir_arg):
        OUT = _output_dir_arg
    else:
        OUT = os.path.join(_PROJ_DIR, _output_dir_arg)
else:
    OUT = os.path.join(_PROJ_DIR, 'output_v4')
LOGS = os.path.join(OUT, 'logs')

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

# -- Flags --
if '--help' in sys.argv or '-h' in sys.argv:
    print(__doc__.strip())
    sys.exit(0)

IS_TURBO = '--turbo' in sys.argv
IS_TURBO_PLUS = '--turbo-plus' in sys.argv
FORCE = '--force' in sys.argv

if not (IS_TURBO or IS_TURBO_PLUS):
    print("Specify --turbo or --turbo-plus")
    print("  python scripts/run_phase4_turbo.py --turbo")
    print("  python scripts/run_phase4_turbo.py --turbo-plus")
    sys.exit(1)

if IS_TURBO_PLUS:
    EQ_STEPS = 20000
    PROD_STEPS = 50000
else:
    EQ_STEPS = 50000
    PROD_STEPS = 100000

N_WORKERS = max(1, os.cpu_count() or 1)
MODE_LABEL = "turbo_plus" if IS_TURBO_PLUS else "turbo"
MODE_NEIGHBOR = "1.0"  # neighbor radius for turbo modes


# intent: Thread-safe LAMMPS worker for parallel execution; returns timing only
# allies: ThreadPoolExecutor (in main()), lmp.write_input, lmp.run_lmp, lmp.parse_production
# sidefx: io (writes LAMMPS log + input file)
# purity: impure
# errors: returns (comp, T, None, error_str) on any failure, never raises
def run_point_worker(datafile, comp, T, subdir):
    """Run LAMMPS at single T (worker). Returns (comp, T, timing_or_None, error_or_None)."""
    os.makedirs(subdir, exist_ok=True)
    logfile = os.path.join(subdir, "log_{:.2f}_{}.lmp".format(comp, T))
    infile = lmp.write_input(datafile, comp, T, OUT, POT_LINE,
                              EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                              SEED_FINAL, neighbor_radius=MODE_NEIGHBOR)

    t0 = time.time()
    try:
        result = lmp.run_lmp(infile, logfile=logfile, timeout=900,
                              lmp_label="x_Pt={:.2f} T={}K".format(comp, T))
    except Exception as e:
        dt = time.time() - t0
        return (comp, T, None, "EXCEPTION: {}".format(e))

    dt = time.time() - t0
    return (comp, T, {'time': dt}, None)


# intent: Orchestrate parallel turbo/turbo-plus MD run
# allies: run_point_worker, lmp_helper, seed_manager, ThreadPoolExecutor
# sidefx: io (writes output_v4/ with CSVs, logs, plots, integrity)
# purity: impure
# errors: returns 0 on success, 1 on LAMMPS not found or failures
def main():
    mode_display = "Turbo Plus" if IS_TURBO_PLUS else "Turbo"
    print('=' * 60)
    print('  Fe-Pt Phase 4 -- {} Mode (Parallel)'.format(mode_display))
    print('  Protocol: {} eq + {} prod, Tdamp={}, Pdamp={}'.format(EQ_STEPS, PROD_STEPS, TDAMP, PDAMP))
    print('  Workers: {}'.format(N_WORKERS))
    print('  Neighbor: {} bin'.format(MODE_NEIGHBOR))
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
    seed_mgr.write_seed_info(OUT, SEED_FINAL, MODE_LABEL, seed_source)

    # Save Turbo protocol log
    mode_label_display = "Turbo" if IS_TURBO else "Turbo Plus"
    lmp.write_protocol_log(OUT, 'run_phase4_turbo.py', EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                           COMPOSITIONS, TEMPS, SEED_FINAL,
                           proto_name='run_turbo_protocol.txt',
                           mode_label=mode_label_display,
                           mode_extra={'Neighbor': '1.0 bin', 'Workers': str(N_WORKERS)})

    # Generate structures
    print('\nGenerating structures...')
    for comp in COMPOSITIONS:
        lmp.gen_structure(comp)
    print('  Structures OK')

    # Build work list
    all_points = []
    for comp in COMPOSITIONS:
        for T in TEMPS:
            datafile = os.path.join(lmp.DATA_DIR, 'data.fept_c{:.2f}.lmp'.format(comp))
            logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
            if RESUME and os.path.exists(logfile):
                p = lmp.parse_production(logfile, NATOMS)
                if p and p.get('n_points', 0) > 500:
                    print('  Resume: skip x_Pt={:.2f} T={}K (exists, {} pts)'.format(comp, T, p.get('n_points', 0)))
                    continue
            all_points.append((datafile, comp, T, LOGS))

    if not all_points:
        print('\nAll points already run (resume mode). Only updating plots/CSV.')
        # Parse existing logs
        parsed_all = {}
        for comp in COMPOSITIONS:
            for T in TEMPS:
                logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
                p = lmp.parse_production(logfile, NATOMS)
                parsed_all[(comp, T)] = p
        # Re-generate outputs
        lmp.write_csv(parsed_all, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                      mode_label=MODE_LABEL, eq_steps=EQ_STEPS, prod_steps=PROD_STEPS)
        lmp.integrity_check(parsed_all, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                            EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                            label=mode_label_display, parallel_workers=N_WORKERS)
        lmp.print_trends(parsed_all, COMPOSITIONS, TEMPS, SEED_FINAL)
        try:
            lmp.make_plots(parsed_all, COMPOSITIONS, TEMPS, SEED_FINAL, OUT,
                           a_vs_T_fn='a_vs_T_all.png',
                           a_vs_T_facets_fn='a_vs_T_facets.png')
        except Exception as e:
            print('  Plot error: {}'.format(e))
        return 0

    print('\nRunning {} points in parallel ({} workers)...'.format(len(all_points), N_WORKERS))

    # Progress monitor
    completed_set = set()
    running_set = {(comp, T) for _, comp, T, _ in all_points}
    failed_set = set()
    error_details = {}
    _monitor_active = True
    total_start = time.time()

    # intent: Background thread printing progress only when state changes
    # allies: main() (created as daemon thread)
    # sidefx: io (stdout)
    # purity: impure
    # errors: none
    def progress_monitor():
        _last_done = -1
        _last_failed = -1
        _last_left = -1
        while _monitor_active:
            time.sleep(30)
            elapsed = time.time() - total_start
            done = len(completed_set)
            failed = len(failed_set)
            left = len(running_set)
            # Skip if nothing changed
            if done == _last_done and failed == _last_failed and left == _last_left:
                continue
            _last_done, _last_failed, _last_left = done, failed, left
            elapsed_min = elapsed / 60
            # ETA: estimate total time from completed points, scale by remaining
            if done > 0:
                avg_per_point = elapsed / done
                remaining = left * avg_per_point / max(N_WORKERS, 1)
                eta_str = "{:.0f}m".format(remaining / 60) if remaining >= 60 else "{:.0f}s".format(remaining)
            else:
                eta_str = "~{:.0f}m".format(len(all_points) * 5 / max(N_WORKERS, 1))
            print("  -- Progress [{:.0f}m] OK {} FAIL {} LEFT {} -- ETA {} --".format(
                elapsed_min, done, failed, left, eta_str))

    monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
    monitor_thread.start()

    # Parallel execution
    parsed_all = {}
    with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = {executor.submit(run_point_worker, df, c, T, sub):
                   (c, T) for df, c, T, sub in all_points}

        for future in as_completed(futures):
            comp, T, raw_result, error = future.result()
            running_set.discard((comp, T))
            logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))

            if raw_result:
                p = lmp.parse_production(logfile, NATOMS)
                p['runtime'] = raw_result.get('time', 0)
                completed_set.add((comp, T))
                msg = '  OK x_Pt={:.2f} T={}K: a={:.6f} n={} t={:.0f}s'.format(
                    comp, T, p.get('a_mean', 0), p.get('n_points', 0), p.get('runtime', 0))
                if p.get('a_mean') is None:
                    msg += ' [no prod thermo]'
                print(msg)
            else:
                failed_set.add((comp, T))
                error_details[(comp, T)] = error if error else "UNKNOWN"
                print('  FAIL x_Pt={:.2f} T={}K: {}'.format(comp, T, (error or '')[:150]))
                p = {'n_points': 0, 'a_mean': None, 'runtime': 0}
            parsed_all[(comp, T)] = p

    _monitor_active = False
    monitor_thread.join(timeout=2)
    total = time.time() - total_start

    print('\n  -- Summary: OK {} FAIL {} / {} in {:.1f} min --'.format(
        len(completed_set), len(failed_set), len(all_points), total / 60))

    if error_details:
        print('\n  -- FAILED POINTS --')
        for (comp, T), err in sorted(error_details.items()):
            print('  x_Pt={:.2f} T={}K: {}'.format(comp, T, err[:200]))

    print('\nTotal time: {:.1f} min'.format(total / 60))

    # Results table
    print('\n' + '=' * 95)
    print('  RESULTS (seed={}, mode={})'.format(SEED_FINAL, MODE_LABEL))
    print('=' * 95)
    hdr = '{:>6} {:>5} {:>11} {:>9} {:>6} {:>9} {:>9}'.format(
        'x_Pt', 'T', 'a_mean', 'a_std', 'n', 'drift', 'time')
    print(hdr)
    print('-' * 95)
    for comp in COMPOSITIONS:
        for T in TEMPS:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                print('{:>6.2f} {:>5} {:>11.6f} {:>9.6f} {:>6} {:>9.2e} {:>5.0f}s'.format(
                    comp, T, p['a_mean'], p.get('a_std', 0),
                    p['n_points'], p.get('drift', 0), p.get('runtime', 0)))
            else:
                print('{:>6.2f} {:>5} {:>11}'.format(comp, T, 'NO DATA'))

    # Trends
    lmp.print_trends(parsed_all, COMPOSITIONS, TEMPS, SEED_FINAL)

    # CSV
    lmp.write_csv(parsed_all, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                  csv_name='all_results_v4_turbo.csv',
                  mode_label=MODE_LABEL, eq_steps=EQ_STEPS, prod_steps=PROD_STEPS)

    # Integrity
    lmp.integrity_check(parsed_all, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                        EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                        label=mode_label_display, parallel_workers=N_WORKERS)

    # Plots (via shared make_plots)
    try:
        lmp.make_plots(parsed_all, COMPOSITIONS, TEMPS, SEED_FINAL, OUT,
                       a_vs_T_fn='a_vs_T_all.png',
                       a_vs_T_facets_fn='a_vs_T_facets.png')
    except Exception as e:
        print('  Plot error: {}'.format(e))

    # Summary
    ok = len(completed_set)
    fail = len(failed_set)
    print('\n' + '=' * 60)
    if fail == 0:
        print('  COMPLETE -- All {} points verified (seed={})'.format(ok, SEED_FINAL))
    else:
        print('  {} OK, {} FAILURES (seed={})'.format(ok, fail, SEED_FINAL))
    print('  Output: ' + OUT)
    print('=' * 60)
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
