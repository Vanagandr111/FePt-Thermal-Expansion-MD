#!/usr/bin/env python3
"""Run only MEAM calibration for Pt (EAM u3 already done)."""
import os, subprocess, math, re, time, shutil, sys

PROJ = "/mnt/c/проекты/Nikolay"
NATOMS = 256
os.chdir(PROJ)

OUT = f"{PROJ}/output_v3"
os.makedirs(f"{OUT}", exist_ok=True)
os.makedirs(f"{OUT}/logs", exist_ok=True)

# ── MEAM calibration matrix ──
calib = []
def add(T, pdamp, eq, prod, mode='iso', label=''):
    calib.append({
        'T': T, 'pdamp': pdamp, 'eq': eq, 'prod': prod,
        'mode': mode, 'label': label or f"meam_T{T}_pdamp{pdamp}_{mode}"
    })

for pdamp in [10.0, 1.0, 0.5, 2.0]:
    for T in [300, 1200]:
        add(T, pdamp, 10000, 50000, 'iso')
for T in [300, 1200]:
    add(T, 10.0, 50000, 100000, 'iso', label=f"meam_T{T}_pdamp10_long")
    add(T, 1.0, 50000, 100000, 'iso', label=f"meam_T{T}_pdamp1_long")
for T in [300, 1200]:
    add(T, 10.0, 10000, 50000, 'aniso')

print(f"MEAM calibration: {len(calib)} points")

def write_input(cfg):
    T = cfg['T']; pdamp = cfg['pdamp']
    eq = cfg['eq']; prod = cfg['prod']; mode = cfg['mode']; label = cfg['label']
    
    fix_str = f"fix nptfix all npt temp {T} {T} 1.0 iso 0.0 0.0 {pdamp}"
    if mode == 'aniso':
        fix_str = f"fix nptfix all npt temp {T} {T} 1.0 aniso 0.0 0.0 {pdamp} couple none"
    
    lines = [
        f"# Pt MEAM calibration: {label}",
        "units metal",
        "boundary p p p",
        "atom_style atomic",
        "",
        "read_data cal_pt/data.pt.lmp",
        "",
        "pair_style meam",
        "pair_coeff * * potentials/library.meam Fe Pt potentials/PtFe.meam Fe Pt",
        "",
        "neighbor 2.0 bin",
        "neigh_modify every 1 delay 0 check yes",
        "",
        "thermo 100",
        "thermo_style custom step temp pe ke press vol lx ly lz",
        "",
        "minimize 1.0e-6 1.0e-8 1000 10000",
        'print "EQ_START"',
        fix_str,
        f"run {eq}",
        'print "EQ_DONE"',
        "",
        "thermo 100",
        'print "PRODUCTION_START"',
        f"run {prod}",
        'print "PRODUCTION_DONE"',
        "",
        "variable mya equal (4.0*vol/count(all))^(1.0/3.0)",
        f'print "RESULT: {label} A=${{mya}}"',
        'print "DONE"',
    ]
    
    inpath = f"{OUT}/in_{label}.lmp"
    with open(inpath, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return inpath

def parse_log(logpath):
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return None
    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    
    result_a = None
    for line in text.split('\n'):
        if 'RESULT:' in line and 'A=' in line:
            m = re.search(r'A=([\d.]+)', line)
            if m: result_a = float(m.group(1))
    
    in_prod = False
    a_vals, vol_vals, press_vals = [], [], []
    for line in text.split('\n'):
        s = line.strip()
        if 'PRODUCTION_START' in s: in_prod = True; continue
        if 'PRODUCTION_DONE' in s: in_prod = False; break
        if in_prod and s and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 9:
                try:
                    vol = float(parts[5])
                    press = float(parts[4])
                    a = (vol * 4 / NATOMS) ** (1/3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                    press_vals.append(press)
                except: pass
    
    if not a_vals:
        return {'result_a': result_a, 'n_points': 0}
    
    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a)**2 for x in a_vals) / (n - 1))
    mean_press = sum(press_vals) / n
    std_press = math.sqrt(sum((p - mean_press)**2 for p in press_vals) / (n - 1))
    half = n // 2
    drift = sum(a_vals[half:]) / (n - half) - sum(a_vals[:half]) / half
    
    return {
        'a_mean': mean_a, 'a_std': std_a, 'drift': drift,
        'n_points': n, 'result_a': result_a,
        'mean_press': mean_press, 'std_press': std_press,
    }

def run_one(cfg):
    label = cfg['label']
    inpath = write_input(cfg)
    logname = f"log_{label}.lmp"
    logpath = f"{OUT}/logs/{logname}"
    
    t0 = time.time()
    result = subprocess.run(
        ["cmd.exe", "/c",
         f"C:\\\\проекты\\\\Nikolay\\\\_run_lmp.bat -in output_v3/in_{label}.lmp -screen none"],
        capture_output=True, text=False, timeout=600
    )
    dt = time.time() - t0
    
    default_log = f"{PROJ}/log.lammps"
    if os.path.exists(default_log):
        shutil.copy2(default_log, logpath)
    
    parsed = parse_log(logpath)
    return {'cfg': cfg, 'exit': result.returncode, 'time': dt, 'parsed': parsed, 'logpath': logpath}

# ════════════════ MAIN ════════════════
print("=" * 80)
print("MEAM CALIBRATION for Pt")
print("=" * 80)

results = {}
for i, cfg in enumerate(calib):
    label = cfg['label']
    print(f"\n[{i+1}/{len(calib)}] {label}...", end="", flush=True)
    
    r = run_one(cfg)
    results[label] = r
    
    if r['parsed'] and r['parsed']['n_points'] > 0:
        p = r['parsed']
        print(f"  a={p['a_mean']:.4f} ±{p['a_std']:.5f}  "
              f"P={p['mean_press']:.1f}  drift={p['drift']:.5f}  "
              f"[{p['n_points']}pts]  {r['time']:.0f}s  ✓")
    else:
        print(f"  FAILED (exit={r['exit']})")

# ── Collect all results (EAM + MEAM) ──
all_results = {}

# EAM logs
import glob
for fname in glob.glob(f"{OUT}/logs/log_eam_*.lmp"):
    label = os.path.basename(fname)[4:-4]
    parsed = parse_log(fname)
    if parsed and parsed['n_points'] > 0:
        all_results[label] = {
            'parsed': parsed,
            'T': int(label.split('_T')[1].split('_')[0]) if '_T' in label else 0,
            'pot': label.split('_')[0],
        }

# MEAM results
for label, r in results.items():
    if r['parsed'] and r['parsed']['n_points'] > 0:
        all_results[label] = {
            'parsed': r['parsed'],
            'T': cfg['T'],
            'pot': 'meam',
        }

# ── CTE table ──
print("\n\n" + "=" * 120)
print("COMPLETE CALIBRATION — CTE ANALYSIS")
print("=" * 120)

EXP_CTE = 9.0e-6

# Build pairs
pairs = {}
for label, data in all_results.items():
    pot = data['pot']
    T = data['T']
    if T == 0: continue
    # Normalize label for pairing
    base = label
    base = base.replace(f'_T300', '_T').replace(f'_T1200', '_T')
    if base not in pairs: pairs[base] = {}
    pairs[base][T] = data['parsed']['a_mean']

header = f"{'Setting':<50} {'a300':>8} {'a1200':>8} {'Δa':>8} {'CTE×10⁶':>10} {'vs_exp':>7} {'n300':>5}"
print(header)
print("-" * 120)

for base in sorted(pairs.keys()):
    pair = pairs[base]
    if 300 in pair and 1200 in pair:
        a300 = pair[300]; a1200 = pair[1200]
        delta = a1200 - a300
        cte = delta / (a300 * 900)
        ratio = cte / EXP_CTE
        # Count points
        n300 = 0
        for label, data in all_results.items():
            if data['T'] == 300 and label.replace('_T300', '_T').replace('_T1200', '_T') == base:
                n300 = data['parsed']['n_points']
        print(f"{base.replace('_T',''):<50} {a300:>8.4f} {a1200:>8.4f} {delta:>8.5f} "
              f"{cte*1e6:>8.2f}    {ratio:>5.2f}x {n300:>5}")

# ── Long-run comparison only ──
print("\n\n" + "=" * 120)
print("LONG RUN COMPARISON (50k eq + 100k prod)")
print("=" * 120)

for pot_prefix in ['eam_u3', 'meam']:
    print(f"\n  {pot_prefix}:")
    for pd in ['pdamp10', 'pdamp1']:
        # Find long runs for this pot + pdamp
        a300 = a1200 = None
        for label, data in all_results.items():
            if data['pot'] != pot_prefix: continue
            if f'_{pd}_long' not in label: continue
            T = data['T']
            if T == 300: a300 = data['parsed']['a_mean']
            elif T == 1200: a1200 = data['parsed']['a_mean']
        if a300 and a1200:
            delta = a1200 - a300
            cte = delta / (a300 * 900)
            print(f"    {pd}: a300={a300:.4f}  a1200={a1200:.4f}  Δa={delta:.5f}  CTE={cte*1e6:.2f}×10⁻⁶")

# ── Baseline vs experiment ──
print("\n\n" + "=" * 80)
print("FINAL COMPARISON — Phase 2 baseline vs long-run vs experiment")
print("=" * 80)

baseline_cte = {'eam_u3': 5.0, 'meam': 4.3}  # ×1e-6

for pot in ['eam_u3', 'meam']:
    # Find short (baseline) and long run CTE
    short_cte = baseline_cte.get(pot, 0)
    long_cte = 0
    long_label = ""
    for label, data in all_results.items():
        if data['pot'] != pot: continue
        if 'long' not in label: continue
        T = data['T']
    # Find pair
    a300_pd10 = None
    a1200_pd10 = None
    for label, data in all_results.items():
        if data['pot'] != pot: continue
        if 'pdamp10_long' in label:
            if data['T'] == 300: a300_pd10 = data['parsed']['a_mean']
            if data['T'] == 1200: a1200_pd10 = data['parsed']['a_mean']
    if a300_pd10 and a1200_pd10:
        long_cte = (a1200_pd10 - a300_pd10) / (a300_pd10 * 900) * 1e6
        print(f"\n  {pot.upper()}:")
        print(f"    Phase 2 (10k/50k): CTE = {short_cte:.1f}×10⁻⁶")
        print(f"    Phase 3 (50k/100k): CTE = {long_cte:.2f}×10⁻⁶")
        print(f"    Experimental: CTE = 9.0×10⁻⁶")

print("\n\nMEAM CALIBRATION COMPLETE.")
