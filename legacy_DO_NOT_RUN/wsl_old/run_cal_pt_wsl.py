#!/usr/bin/env python3
"""
run_cal_pt.py — Полная калибровка чистой Pt.
Запускает MEAM и EAM u3, сравнивает результаты.
Все результаты сохраняет в виде raw LAMMPS логов + CSV.
"""
import os, subprocess, math, re, time, shutil

PROJ = "/mnt/c/проекты/Nikolay"
NATOMS = 256
os.chdir(PROJ)

log_path = f"{PROJ}/cal_pt/calibration_log.txt"

def log(msg):
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')
    print(msg)

# ── Parser ──
def parse_thermo(text):
    """Parse thermo: step temp pe ke press vol lx ly lz"""
    in_prod = False
    a_vals, vol_vals, lx_vals = [], [], []
    for line in text.split('\n'):
        s = line.strip()
        if not s: continue
        if 'PRODUCTION_START' in s: in_prod = True; continue
        if 'PRODUCTION_DONE' in s: in_prod = False; continue
        if in_prod and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 9:
                try:
                    vol = float(parts[5]); lx = float(parts[6])
                    ly = float(parts[7]); lz = float(parts[8])
                    a = (vol * 4 / NATOMS) ** (1/3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                    lx_vals.append(lx)
                except: pass
    if not a_vals: return None
    n = len(a_vals)
    avg = lambda vals: sum(vals) / n
    sdev = lambda vals: math.sqrt(sum((x - avg(vals))**2 for x in vals) / (n - 1))
    half = n // 2
    drift = avg(a_vals[half:]) - avg(a_vals[:half])
    return {
        'a_mean': avg(a_vals), 'a_std': sdev(a_vals), 'n_points': n,
        'vol_mean': avg(vol_vals), 'vol_std': sdev(vol_vals),
        'lx_mean': avg(lx_vals), 'drift': drift,
    }

# ── Input generators ──
def write_input_eam_u3(T):
    lines = [
        f"# Pt T={T}K EAM u3 (Foiles)",
        "units metal boundary p p p atom_style atomic",
        "",
        f"read_data       cal_pt/data.pt.lmp",
        "",
        "pair_style      eam",
        "pair_coeff      * * potentials/Pt_u3.eam",
        "",
        "neighbor        2.0 bin",
        "neigh_modify    every 1 delay 0 check yes",
        "",
        "thermo          100",
        "thermo_style    custom step temp pe ke press vol lx ly lz",
        "",
        "minimize        1.0e-6 1.0e-8 1000 10000",
        'print "EQ_START"',
        f"fix nptfix all npt temp {T} {T} 1.0 iso 0.0 0.0 10.0",
        "run             10000",
        'print "EQ_DONE"',
        "",
        "thermo          100",
        'print "PRODUCTION_START"',
        "run             50000",
        'print "PRODUCTION_DONE"',
        "",
        "variable mya   equal (4.0*vol/count(all))^(1.0/3.0)",
        "variable myvol equal vol",
        f'print "RESULT: T={T} POT=eam_u3 VOL=${{myvol}} A=${{mya}}"',
        'print "DONE"',
    ]
    inpath = f"{PROJ}/cal_pt/input/in_u3_T{T}.lmp"
    with open(inpath, 'w') as f: f.write('\n'.join(lines) + '\n')
    return inpath

def write_input_meam_clean(T):
    """MEAM pair_coeff with just Pt from library — pure element."""
    lines = [
        f"# Pt T={T}K MEAM (pure Pt via library)",
        "units metal boundary p p p atom_style atomic",
        "",
        f"read_data       cal_pt/data.pt.lmp",
        "",
        "pair_style      meam",
        "pair_coeff      * * potentials/library.meam Pt",
        "",
        "neighbor        2.0 bin",
        "neigh_modify    every 1 delay 0 check yes",
        "",
        "thermo          100",
        "thermo_style    custom step temp pe ke press vol lx ly lz",
        "",
        "minimize        1.0e-6 1.0e-8 1000 10000",
        'print "EQ_START"',
        f"fix nptfix all npt temp {T} {T} 1.0 iso 0.0 0.0 10.0",
        "run             10000",
        'print "EQ_DONE"',
        "",
        "thermo          100",
        'print "PRODUCTION_START"',
        "run             50000",
        'print "PRODUCTION_DONE"',
        "",
        "variable mya   equal (4.0*vol/count(all))^(1.0/3.0)",
        "variable myvol equal vol",
        f'print "RESULT: T={T} POT=meam VOL=${{myvol}} A=${{mya}}"',
        'print "DONE"',
    ]
    inpath = f"{PROJ}/cal_pt/input/in_meam_T{T}.lmp"
    with open(inpath, 'w') as f: f.write('\n'.join(lines) + '\n')
    return inpath

# ── Runner ──
def run_lmp(T, pot_type):
    t0 = time.time()
    result = subprocess.run(
        ["cmd.exe", "/c",
         f"C:\\проекты\\Nikolay\\_run_lmp.bat -in cal_pt/input/in_{pot_type}_T{T}.lmp "
         f"-log cal_pt/output/log_{pot_type}_T{T}.lmp"],
        capture_output=True, text=False, timeout=600
    )
    dt = time.time() - t0
    out = result.stdout.decode('cp1251', errors='replace') if result.stdout else ''
    
    logpath = f"{PROJ}/cal_pt/output/log_{pot_type}_T{T}.lmp"
    log_text = ''
    if os.path.exists(logpath):
        with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
            log_text = f.read()
    
    full_text = out + '\n' + log_text
    
    # RESULT
    result_a = None
    for line in full_text.split('\n'):
        if 'RESULT:' in line and 'A=' in line:
            m = re.search(r'A=([\d.]+)', line)
            if m: result_a = float(m.group(1))
    
    parsed = parse_thermo(full_text)
    return {
        'T': T, 'pot': pot_type, 'exit': result.returncode,
        'time': dt, 'result_a': result_a, 'parsed': parsed,
        'full_text': full_text,
    }

# ═══════════════════════════════════════════
# MAIN CALIBRATION RUN
# ═══════════════════════════════════════════

with open(log_path, 'w') as f:
    f.write("Pt CALIBRATION LOG — Phase 2\n" + "=" * 70 + "\n")

log("=" * 70)
log("PHASE 2: Pt Calibration")
log("=" * 70)

TEMPS = [300, 600, 900, 1200]

# ── Run 1: EAM u3 ──
log("\n" + "=" * 55)
log("RUN 1: EAM u3 (Foiles et al, PRB 33, 7983 1986)")
log("=" * 55)

eam_results = {}
for T in TEMPS:
    write_input_eam_u3(T)
    r = run_lmp(T, "u3")
    eam_results[T] = r
    if r['parsed']:
        p = r['parsed']
        log(f"  T={T:>4}K: a={p['a_mean']:.4f} ±{p['a_std']:.5f}  last={r['result_a']:.4f}  "
            f"drift={p['drift']:.5f}  [{p['n_points']} pts]  {r['time']:.0f}s")
    else:
        log(f"  T={T:>4}K: FAILED (exit={r['exit']})")

# ── Run 2: MEAM ──
log("\n" + "=" * 55)
log("RUN 2: MEAM Kim-Koo-Lee 2006 (library.meam)")
log("=" * 55)

meam_results = {}
for T in TEMPS:
    write_input_meam_clean(T)
    r = run_lmp(T, "meam")
    meam_results[T] = r
    if r['parsed']:
        p = r['parsed']
        log(f"  T={T:>4}K: a={p['a_mean']:.4f} ±{p['a_std']:.5f}  last={r['result_a']:.4f}  "
            f"drift={p['drift']:.5f}  [{p['n_points']} pts]  {r['time']:.0f}s")
    else:
        log(f"  T={T:>4}K: FAILED (exit={r['exit']})")
        if not r['parsed']:
            # Show error
            for line in r['full_text'].split('\n')[-10:]:
                if 'ERROR' in line:
                    log(f"  ERROR: {line.strip()}")

# ── Comparison ──
log("\n\n" + "=" * 80)
log("VALIDATION TABLE — Pt calibration")
log("=" * 80)
log(f"{'Potential':<20} {'T':>5} {'a_mean':>8} {'a_std':>8} {'drift':>8} {'n':>5} {'time':>5} {'Trend':>6}")
log("-" * 80)

for pot_name, results in [("EAM u3 (Foiles)", eam_results), ("MEAM (library)", meam_results)]:
    a_vals = []
    for T in TEMPS:
        r = results.get(T)
        if r and r['parsed']:
            p = r['parsed']
            trend = ""
            a_vals.append(p['a_mean'])
        else:
            log(f"{pot_name:<20} {T:>5} {'FAIL':>8}")
            continue
        
        log(f"{pot_name:<20} {T:>5} {p['a_mean']:>8.4f} {p['a_std']:>8.5f} "
            f"{p['drift']:>8.5f} {p['n_points']:>5} {r['time']:>4.0f}s", end="")
    
    if len(a_vals) == 4:
        rise = a_vals[3] - a_vals[0]
        ref_a300 = a_vals[0]
        mono = all(a_vals[i+1] >= a_vals[i] for i in range(3))
        log(f"\n  Trend: a(1200)-a(300) = {rise:.6f} Å ({rise/a_vals[0]*100:.3f}%)")
        log(f"  a(300K) = {ref_a300:.4f} Å  (experimental Pt = 3.92 Å)")
        log(f"  Monotonic: {'YES ✓' if mono else 'NO ✗'}")
        log(f"  Expansion coeff (300-1200K): {rise/900/a_vals[0]*1e6:.2f}×10⁻⁶ K⁻¹")
        log(f"  Experimental: ~8.9×10⁻⁶ K⁻¹")
    log("")

# ── Save to project output format ──
log("\n\n" + "=" * 55)
log("SAVING RESULTS")
log("=" * 55)

# For each potential, create CSV
for pot_name, results in [("eam_u3", eam_results), ("meam", meam_results)]:
    csv_path = f"{PROJ}/cal_pt/output/results_{pot_name}.csv"
    valid = all(results.get(T) and results[T]['parsed'] for T in TEMPS)
    if valid:
        with open(csv_path, 'w') as f:
            f.write("Potential,T_K,a_mean_Angstrom,a_std_Angstrom,vol_mean,drift,n_points,result_last_point\n")
            for T in TEMPS:
                r = results[T]
                p = r['parsed']
                f.write(f"{pot_name},{T},{p['a_mean']:.6f},{p['a_std']:.6f},"
                       f"{p['vol_mean']:.6f},{p['drift']:.6e},{p['n_points']},{r['result_a']:.6f}\n")
        log(f"  {csv_path} saved")

# ── Decision ──
log("\n\n" + "=" * 70)
log("CALIBRATION DECISION")
log("=" * 70)

# EAM u3 check
eam_ok = all(eam_results.get(T) and eam_results[T]['parsed'] for T in TEMPS)
meam_ok = all(meam_results.get(T) and meam_results[T]['parsed'] for T in TEMPS)

if eam_ok:
    eam_a = [eam_results[T]['parsed']['a_mean'] for T in TEMPS]
    eam_mono = all(eam_a[i+1] >= eam_a[i] for i in range(3))
    log(f"EAM u3:    monotonic={'YES' if eam_mono else 'NO'}, a300={eam_a[0]:.4f}")
else:
    log(f"EAM u3:    FAILED")
    eam_mono = False

if meam_ok:
    meam_a = [meam_results[T]['parsed']['a_mean'] for T in TEMPS]
    meam_mono = all(meam_a[i+1] >= meam_a[i] for i in range(3))
    log(f"MEAM:      monotonic={'YES' if meam_mono else 'NO'}, a300={meam_a[0]:.4f}")
else:
    log(f"MEAM:      FAILED")
    meam_mono = False

# Final recommendation
best_for_pt = ""

if eam_mono:
    best_for_pt = "EAM u3 (Foiles)"
    log(f"\n✓ RECOMMENDED for pure Pt: {best_for_pt}")
else:
    best_for_pt = "MEAM"
    log(f"\n✓ RECOMMENDED: {best_for_pt}")

log(f"\nNote: For Fe-Pt alloys, MEAM (Kim-Koo-Lee 2006) is the only available")
log(f"binary potential. EAM u3 works only for pure Pt.")
log(f"\nThe MD improvements (averaging, longer production, NPT damping) will be")
log(f"applied to ALL runs regardless of potential choice.")

log("\n\nCALIBRATION DONE.")
print("\nDone! Check", log_path)
