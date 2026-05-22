#!/usr/bin/env python
"""
run_mode.py — Универсальный параллельный движок для всех режимов Fe-Pt MD.

Режимы:
  demo       — 50 eq + 100 prod, 2048 atoms, OpenMP, 1 worker (тест)
  turbo-fast — 20k eq + 50k prod, 256 atoms, neighbour 1.0, OpenMP
  turbo      — neighbour 1.0, 50k eq + 100k prod, параллельно
  long       — neighbour 2.0, 50k eq + 100k prod, параллельно

Бэкенды:
  omp    — OpenMP (по умолчанию)
  kokkos — KOKKOS (только для 2048 atoms)

Количество атомов:
  --natoms 256   → 4×4×4 supercell, OpenMP (для turbo, long)
  --natoms 2048  → 8×8×8 supercell (по умолчанию для turbo, long)

Usage:
    python scripts/run_mode.py --mode demo
    python scripts/run_mode.py --mode turbo-fast --seed 12345
    python scripts/run_mode.py --mode turbo --natoms 256 --backend omp
    python scripts/run_mode.py --mode turbo --natoms 2048 --backend omp
    python scripts/run_mode.py --mode turbo --natoms 2048 --backend kokkos
    python scripts/run_mode.py --mode long --natoms 256 --backend omp
    python scripts/run_mode.py --mode long --natoms 2048 --backend omp --seed 100100 --force

Windows-first. Output -> output_v4/.
"""
import os
import sys
import time
import threading
import argparse
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

# ── Windows-only guard ──
if os.name == 'posix':
    print("=" * 60)
    print("  ERROR: WSL/Linux Python detected!")
    print("  run_mode.py requires Windows Python, not WSL.")
    print("=" * 60)
    print("  Your 'python' in PATH points to WSL Python.")
    print("  Fix: use Windows Python explicitly:")
    print("    C:\\Users\\home\\AppData\\Local\\Python\\bin\\python.exe scripts\\run_mode.py ...")
    print("=" * 60)
    sys.exit(1)


# ── Парсинг аргументов ──
parser = argparse.ArgumentParser(description='Fe-Pt MD — универсальный раннер')
parser.add_argument('--mode', choices=['demo', 'turbo-fast', 'turbo', 'turbo-experimental', 'long'],
                    default='turbo', help='Режим расчёта')
parser.add_argument('--backend', choices=['omp', 'kokkos'],
                    default='omp', help='Бэкенд: omp (OpenMP) или kokkos')
parser.add_argument('--natoms', type=int, choices=[256, 2048], default=2048,
                    help='Количество атомов: 256 (4×4×4) или 2048 (8×8×8)')
parser.add_argument('--seed', nargs='?', const='reuse', default=None,
                    help='Seed: число, "reuse" или опустить для авто')
parser.add_argument('--force', action='store_true',
                    help='Пересоздать всё с нуля')
parser.add_argument('--output-dir', default=None,
                    help='Выходная директория (относительно проекта)')
print("  [RAW_ARGV] os.name='{}' sys.argv={}".format(os.name, sys.argv))
args = parser.parse_args()

MODE = args.mode
print("  [HERMES_DIAG] MODE = '{}'  os.name = '{}'  sys.argv = {}".format(MODE, os.name, sys.argv))

BACKEND = args.backend
FORCE = args.force
NATOMS = args.natoms

# ── Валидация ──
if BACKEND == 'kokkos' and NATOMS == 256:
    print('ERROR: KOKKOS backend only works with 2048 atoms. Use --backend omp for --natoms 256')
    sys.exit(1)

# ── Параметры режимов ──
COMPOSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 500, 700, 900, 1100, 1200]

if MODE == 'demo':
    EQ_STEPS = 50
    PROD_STEPS = 100
    NX, NY, NZ = 8, 8, 8
    NEIGHBOR = '2.0'
    N_WORKERS = 1
    OMP_THREADS = 2
    MODE_LABEL = 'demo'
    MODE_DISPLAY = 'Demo'

elif MODE == 'turbo-fast':
    EQ_STEPS = 20000
    PROD_STEPS = 50000
    NATOMS = 256
    NX, NY, NZ = 4, 4, 4
    NEIGHBOR = '1.0'
    OMP_THREADS = 2
    N_WORKERS = max(1, (os.cpu_count() or 4) // 2)
    MODE_LABEL = 'turbo_fast'
    MODE_DISPLAY = 'Turbo Fast'

elif MODE == 'turbo':
    EQ_STEPS = 50000
    PROD_STEPS = 100000
    NEIGHBOR = '1.0'
    if NATOMS == 256:
        NX, NY, NZ = 4, 4, 4
        OMP_THREADS = 2
        N_WORKERS = max(1, (os.cpu_count() or 4) // 2)
    else:
        NX, NY, NZ = 8, 8, 8
        OMP_THREADS = 2
        N_WORKERS = max(1, (os.cpu_count() or 4) // 2)
    MODE_LABEL = 'turbo_{}at_{}'.format(NATOMS, BACKEND)
    MODE_DISPLAY = 'Turbo {}at {}'.format(NATOMS, BACKEND.upper())

elif MODE == 'turbo-experimental':
    EQ_STEPS = 50000
    PROD_STEPS = 100000
    NEIGHBOR = '1.0'
    NATOMS = 256
    NX, NY, NZ = 4, 4, 4
    OMP_THREADS = 4
    N_WORKERS = max(1, (os.cpu_count() or 8) // 4)
    NEIGH_MODIFY_EVERY = 5
    MODE_LABEL = 'turbo_exp'
    MODE_DISPLAY = 'Turbo Experimental 256at'

else:  # long
    EQ_STEPS = 50000
    PROD_STEPS = 100000
    NEIGHBOR = '2.0'
    if NATOMS == 256:
        NX, NY, NZ = 4, 4, 4
        OMP_THREADS = 2
        N_WORKERS = max(1, (os.cpu_count() or 4) // 2)
    else:
        NX, NY, NZ = 8, 8, 8
        OMP_THREADS = 2
        N_WORKERS = max(1, (os.cpu_count() or 4) // 2)
    MODE_LABEL = 'long_{}at_{}'.format(NATOMS, BACKEND)
    MODE_DISPLAY = 'Long-Fast {}at {}'.format(NATOMS, BACKEND.upper())

TDAMP = 1.0
PDAMP = 10.0
USE_KOKKOS = (BACKEND == 'kokkos')
NEIGH_MODIFY_EVERY = 1  # default, override per-mode as needed

# ── Output dir: разделяем 256 и 2048 результаты ──
if args.output_dir:
    if os.path.isabs(args.output_dir):
        OUT = args.output_dir
    else:
        OUT = os.path.join(_PROJ_DIR, args.output_dir)
elif NATOMS == 256:
    OUT = os.path.join(_PROJ_DIR, 'output_v4_256')
    print('  NOTE: output in output_v4_256 (256-atoms results)')
else:
    OUT = os.path.join(_PROJ_DIR, 'output_v4')
LOGS = os.path.join(OUT, 'logs')

# ── Seed ──
if args.seed == 'reuse':
    SEED_ARG = -1
elif args.seed is not None:
    SEED_ARG = int(args.seed)
else:
    SEED_ARG = None


# ── Worker function ──
def run_point_worker(datafile, comp, T, subdir):
    """Run LAMMPS at single T (worker). Returns (comp, T, timing_or_None, error_or_None)."""
    os.makedirs(subdir, exist_ok=True)
    logfile = os.path.join(subdir, "log_{:.2f}_{}.lmp".format(comp, T))
    pot_line, pair_style = lmp.get_potential(comp)
    is_pure_fe = (comp <= 0.001)
    infile = lmp.write_input(datafile, comp, T, OUT, pot_line,
                              EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                              12345, neighbor_radius=NEIGHBOR,
                              omp_threads=OMP_THREADS, use_kokkos=USE_KOKKOS,
                              pair_style_type=pair_style,
                              single_run=is_pure_fe,
                              neigh_modify_every=NEIGH_MODIFY_EVERY)

    t0 = time.time()
    try:
        result = lmp.run_lmp(infile, logfile=logfile, timeout=6000,
                              lmp_label="x_Pt={:.2f} T={}K".format(comp, T),
                              omp_threads=OMP_THREADS, use_kokkos=USE_KOKKOS)
    except Exception as e:
        dt = time.time() - t0
        return (comp, T, None, "EXCEPTION: {}".format(e))

    dt = time.time() - t0
    return (comp, T, {'time': dt}, None)


# ── Main ──
def main():
    print('=' * 60)
    print('  Fe-Pt Phase 4 -- {} Mode'.format(MODE_DISPLAY))
    print('  Backend: {}'.format(BACKEND.upper()))
    print('  Atoms: {} ({}x{}x{} cells)'.format(NATOMS, NX, NY, NZ))
    print('  Protocol: {} eq + {} prod, Tdamp={}, Pdamp={}'.format(EQ_STEPS, PROD_STEPS, TDAMP, PDAMP))
    print('  Neighbor: {} bin'.format(NEIGHBOR))
    print('  Workers: {}  |  OMP threads: {}'.format(N_WORKERS, OMP_THREADS))
    print('  Grid: {} comps x {} temps = {} points'.format(
        len(COMPOSITIONS), len(TEMPS), len(COMPOSITIONS) * len(TEMPS)))
    print('  Output: ' + OUT)
    lmp_path = lmp.find_lmp_display()
    print('  LAMMPS: ' + (lmp_path or 'NOT FOUND'))
    print('=' * 60)

    if not lmp.find_lmp():
        print('\nERROR: lmp.exe not found')
        return 1

    lmp.check_stale_lammps()

    import time as _time
    _time.sleep(1)

    if FORCE and os.path.exists(OUT):
        import shutil
        shutil.rmtree(OUT)

    os.makedirs(LOGS, exist_ok=True)

    # Seed
    global SEED_FINAL
    SEED_FINAL, seed_source = seed_mgr.get_or_create_seed(
        _PROJ_DIR, OUT,
        manual_seed=SEED_ARG if SEED_ARG not in (None, -1) else None,
        reuse_last=SEED_ARG == -1,
    )
    seed_mgr.write_seed_info(OUT, SEED_FINAL, MODE_LABEL, seed_source)

    # Protocol log
    lmp.write_protocol_log(OUT, 'run_mode.py', EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                           COMPOSITIONS, TEMPS, SEED_FINAL,
                           proto_name='run_protocol.txt',
                           mode_label=MODE_DISPLAY,
                           mode_extra={'Neighbor': NEIGHBOR + ' bin',
                                       'Workers': str(N_WORKERS),
                                       'Atoms': str(NATOMS),
                                       'Backend': BACKEND.upper()})

    # Generate structures (with correct atom count for mode)
    print()
    print('Generating structures...')
    for comp in COMPOSITIONS:
        lmp.gen_structure(comp, nx=NX, ny=NY, nz=NZ, force=FORCE)
    print('  Structures OK ({} atoms)'.format(NATOMS))

    # Build work list
    all_points = []
    for comp in COMPOSITIONS:
        for T in TEMPS:
            datafile = os.path.join(lmp.DATA_DIR, 'data.fept_c{:.2f}.lmp'.format(comp))
            logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
            all_points.append((datafile, comp, T, LOGS))

    print('\nRunning {} points in parallel ({} workers)...'.format(len(all_points), N_WORKERS))

    # DEMO: sequential, not parallel
    if MODE == 'demo':
        print('  (sequential mode — 1 point at a time)')
        parsed_all = {}
        for datafile, comp, T, subdir in all_points:
            comp_out, T_out, raw_result, error = run_point_worker(datafile, comp, T, subdir)
            logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
            if raw_result:
                p = lmp.parse_production(logfile, NATOMS)
                p['runtime'] = raw_result.get('time', 0)
                msg = '  OK x_Pt={:.2f} T={}K: a={:.6f} n={} t={:.0f}s'.format(
                    comp, T, p.get('a_mean', 0), p.get('n_points', 0), p.get('runtime', 0))
                if p.get('a_mean') is None:
                    msg += ' [no prod thermo]'
                print(msg)
            else:
                print('  FAIL x_Pt={:.2f} T={}K: {}'.format(comp, T, (error or '')[:150]))
                p = {'n_points': 0, 'a_mean': None, 'runtime': 0}
            parsed_all[(comp, T)] = p
        total = 0

    # Parallel execution for all other modes
    else:
        completed_set = set()
        running_set = {(comp, T) for _, comp, T, _ in all_points}
        failed_set = set()
        error_details = {}
        _point_durations = []  # rolling window for ETA
        _monitor_active = True
        total_start = time.time()

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
                if done == _last_done and failed == _last_failed and left == _last_left:
                    continue
                _last_done, _last_failed, _last_left = done, failed, left
                elapsed_min = elapsed / 60
                if done > 0:
                    # ETA by rolling median of last N completed points
                    if len(_point_durations) >= 3:
                        recent = sorted(_point_durations[-5:])
                        med = recent[len(recent)//2]
                        avg_per_point = med
                    else:
                        # fallback: use last point or global average
                        if _point_durations:
                            avg_per_point = max(_point_durations[-1], elapsed / done)
                        else:
                            avg_per_point = elapsed / done
                    remaining = left * avg_per_point / max(N_WORKERS, 1)
                    eta_str = "{:.0f}m".format(remaining / 60) if remaining >= 60 else "{:.0f}s".format(remaining)
                else:
                    eta_str = "~{:.0f}m".format(len(all_points) * 5 / max(N_WORKERS, 1))
                print("  -- Progress [{:.0f}m] OK {} FAIL {} LEFT {} -- ETA {} --".format(
                    elapsed_min, done, failed, left, eta_str))

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

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
                    _point_durations.append(raw_result.get('time', 0))
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
    print('  RESULTS (seed={}, mode={})'.format(SEED_FINAL, MODE_DISPLAY))
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
    csv_name = 'all_results_{}.csv'.format(MODE_LABEL)
    lmp.write_csv(parsed_all, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                  csv_name=csv_name, mode_label=MODE_LABEL,
                  eq_steps=EQ_STEPS, prod_steps=PROD_STEPS)

    # Integrity
    lmp.integrity_check(parsed_all, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                        EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                        label=MODE_DISPLAY, parallel_workers=N_WORKERS)

    # CTE report
    lmp.write_cte_csv(parsed_all, COMPOSITIONS, TEMPS, OUT)

    # Plots
    try:
        lmp.make_plots(parsed_all, COMPOSITIONS, TEMPS, SEED_FINAL, OUT,
                       a_vs_T_fn='a_vs_T_{}.png'.format(MODE_LABEL),
                       a_vs_T_facets_fn='a_vs_T_{}_facets.png'.format(MODE_LABEL))
    except Exception as e:
        print('  Plot error: {}'.format(e))

    # Summary
    ok = sum(1 for p in parsed_all.values() if p and p.get('a_mean') is not None)
    fail = len(all_points) - ok
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
