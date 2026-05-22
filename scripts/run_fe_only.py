"""Run only Fe-0% composition (x_Pt=0.00) for Long Fast mode.
Needs longer timeout than Fe-Pt alloys (~7000s vs ~5000s).
"""
import sys, os, time, glob, shutil, csv

PROJDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJDIR, 'scripts'))
import lmp_helper as lmp

sys.path.insert(0, os.path.join(PROJDIR, 'scripts'))
# Re-import with correct PROJDIR
import importlib
importlib.reload(lmp)

# ── Config ────────────────────────────────────────
POT_LINE = "pair_coeff      * * potentials\\library.meam Fe Pt potentials\\PtFe.meam Fe Pt"
EQ_STEPS = 50000
PROD_STEPS = 100000
TDAMP = 1.0
PDAMP = 10.0
OMP_THREADS = 2
SEED = 100100
TIMEOUT = 9000  # 150 minutes — Fe is slower
WORKERS = 6  # 6 temps for 0.00 only

OUT = os.path.join(PROJDIR, 'output_v4', 'long_fast')
LOGS = os.path.join(OUT, 'logs')
IN_DIR = os.path.join(OUT, 'in')
DATA_DIR = os.path.join(PROJDIR, 'data')

# Clean only 0.00 logs and results
for f in glob.glob(os.path.join(LOGS, 'log_0.00_*.lmp')):
    os.remove(f)
for f in glob.glob(os.path.join(IN_DIR, 'in_phase4_0.00_*.lmp')):
    os.remove(f)
if os.path.exists(os.path.join(OUT, 'a_T_comp_0.00_turbo.csv')):
    os.remove(os.path.join(OUT, 'a_T_comp_0.00_turbo.csv'))

lmp.check_stale_lammps()

os.makedirs(LOGS, exist_ok=True)
os.makedirs(IN_DIR, exist_ok=True)

T_LIST = [300, 500, 700, 900, 1100, 1200]
datafile = os.path.join(DATA_DIR, 'data.fept_c0.00.lmp')
comp = 0.00

print("="*60)
print("  Fe-0% Long Fast — 6 temps, timeout={}s".format(TIMEOUT))
print("="*60)
print()

from concurrent.futures import ThreadPoolExecutor, as_completed

def worker(T):
    logfile = os.path.join(LOGS, "log_0.00_{}.lmp".format(T))
    infile = lmp.write_input(datafile, comp, T, OUT, POT_LINE,
                              EQ_STEPS, PROD_STEPS, TDAMP, PDAMP,
                              SEED, neighbor_radius="2.0",
                              omp_threads=OMP_THREADS, use_kokkos=False)
    t0 = time.time()
    try:
        result = lmp.run_lmp(infile, logfile=logfile, timeout=TIMEOUT,
                             lmp_label="Fe x_Pt=0.00 T={}K".format(T),
                             omp_threads=OMP_THREADS, use_kokkos=False)
    except Exception as e:
        return (T, None, str(e))
    dt = time.time() - t0
    if not result.get('ok', False):
        return (T, None, result.get('stderr', '')[:200])
    # Parse result
    from lmp_helper import parse_logfile
    parsed = parse_logfile(logfile)
    if parsed is None:
        return (T, None, "Parse fail")
    a_mean, a_std, n_pts, drift = parsed
    return (T, a_mean, None)

results = []
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    futures = {pool.submit(worker, T): T for T in T_LIST}
    for fut in as_completed(futures):
        T, a_val, err = fut.result()
        if a_val:
            results.append((T, a_val))
            print("  T={}K → a={:.6f} ✅".format(T, a_val))
        else:
            print("  T={}K → FAIL: {}".format(T, err[:120]))

results.sort(key=lambda x: x[0])

# Write per-comp CSV
out_path = os.path.join(OUT, 'a_T_comp_0.00_turbo.csv')
with open(out_path, 'w', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['T_K', 'a_mean_Angstrom'])
    for T, a in results:
        w.writerow(['{:.0f}'.format(T), '{:.6f}'.format(a)])

print()
print("  Written: {}".format(out_path))
print()
print("  Fe-0% results:")
for T, a in results:
    print("    T={:4d}K → a = {:.6f} A".format(T, a))
print("\n  DONE ({:.1f} min)".format(len(results) * 0))  # just placeholder
