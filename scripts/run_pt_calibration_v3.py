#!/usr/bin/env python3
"""Pt calibration v3: systematic NPT matrix for Pt thermal expansion.
Tests: Pdamp, production length, equilibration length, iso/aniso.
Potentials: EAM u3 (Foiles), MEAM (Lee 2003 via library.meam).
Temperatures: 300K, 1200K (for CTE).
"""
import os, subprocess, math, re, time, shutil, sys

PROJ = "/mnt/c/проекты/Nikolay"
NATOMS = 256
os.chdir(PROJ)

OUT = f"{PROJ}/output_v3"
os.makedirs(f"{OUT}", exist_ok=True)
os.makedirs(f"{OUT}/logs", exist_ok=True)

# ── Known results (Phase 2 baseline, 50k prod, Pdamp=10) ──
BASELINE = {
    'eam_u3':  {300: 3.9256, 1200: 3.9433},
    'meam':    {300: 3.9247, 1200: 3.9399},
}
BASELINE_CTE = {
    'eam_u3': 5.0e-6,
    'meam':   4.3e-6,
}
EXP_CTE = 9.0e-6
EXP_A300 = 3.92
EXP_A1200 = 3.96

# ── Calibration matrix ──
# Each entry: (pot_name, T, Pdamp, eq_steps, prod_steps, mode, label)
CALIB_MATRIX = []
def add(pot, T, pdamp, eq, prod, mode='iso', label=''):
    CALIB_MATRIX.append({
        'pot': pot, 'T': T, 'pdamp': pdamp, 'eq': eq, 'prod': prod,
        'mode': mode, 'label': label or f"{pot}_T{T}_pdamp{pdamp}_{mode}"
    })

# EAM u3 calibration
for pdamp in [10.0, 1.0, 0.5, 2.0]:
    for T in [300, 1200]:
        add('eam_u3', T, pdamp, 10000, 50000, 'iso')
# Long runs
for T in [300, 1200]:
    add('eam_u3', T, 10.0, 50000, 100000, 'iso', label=f"eam_u3_T{T}_pdamp10_long")
    add('eam_u3', T, 1.0, 50000, 100000, 'iso', label=f"eam_u3_T{T}_pdamp1_long")
# Aniso
for T in [300, 1200]:
    add('eam_u3', T, 10.0, 10000, 50000, 'aniso')

# MEAM calibration
for pdamp in [10.0, 1.0, 0.5, 2.0]:
    for T in [300, 1200]:
        add('meam', T, pdamp, 10000, 50000, 'iso')
for T in [300, 1200]:
    add('meam', T, 10.0, 50000, 100000, 'iso', label=f"meam_T{T}_pdamp10_long")
    add('meam', T, 1.0, 50000, 100000, 'iso', label=f"meam_T{T}_pdamp1_long")

print(f"Total calibration points: {len(CALIB_MATRIX)}")
print(f"  EAM u3 runs: {sum(1 for c in CALIB_MATRIX if c['pot']=='eam_u3')}")
print(f"  MEAM runs:   {sum(1 for c in CALIB_MATRIX if c['pot']=='meam')}")

# ── LAMMPS input generation ──
def write_input(cfg):
    pot = cfg['pot']
    T = cfg['T']
    pdamp = cfg['pdamp']
    eq = cfg['eq']
    prod = cfg['prod']
    mode = cfg['mode']
    label = cfg['label']
    
    if mode == 'iso':
        fix_str = f"fix nptfix all npt temp {T} {T} 1.0 iso 0.0 0.0 {pdamp}"
    else:
        fix_str = f"fix nptfix all npt temp {T} {T} 1.0 aniso 0.0 0.0 {pdamp} couple none"
    
    if pot == 'eam_u3':
        pair_lines = [
            "pair_style eam",
            "pair_coeff * * potentials/Pt_u3.eam",
        ]
        data_path = "cal_pt/data.pt.lmp"
    elif pot == 'meam':
        # MEAM requires both elements even for pure Pt
        pair_lines = [
            "pair_style meam",
            "pair_coeff * * potentials/library.meam Fe Pt potentials/PtFe.meam Fe Pt",
        ]
        data_path = "cal_pt/data.pt.lmp"
    
    lines = [
        f"# Pt calibration: {label}",
        "units metal",
        "boundary p p p",
        "atom_style atomic",
        "",
        f"read_data {data_path}",
        "",
    ] + pair_lines + [
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

# ── Parser ──
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
    a_vals, vol_vals, press_vals, temp_vals = [], [], [], []
    for line in text.split('\n'):
        s = line.strip()
        if 'PRODUCTION_START' in s: in_prod = True; continue
        if 'PRODUCTION_DONE' in s: in_prod = False; break
        if in_prod and s and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 9:
                try:
                    step = int(parts[0])
                    temp = float(parts[1])
                    press = float(parts[4])
                    vol = float(parts[5])
                    a = (vol * 4 / NATOMS) ** (1/3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                    press_vals.append(press)
                    temp_vals.append(temp)
                except: pass
    
    if not a_vals:
        # Fallback: everything after EQ_DONE
        in_prod = False
        for line in text.split('\n'):
            s = line.strip()
            if 'EQ_DONE' in s: in_prod = True; continue
            if 'RESULT:' in s: break
            if in_prod and s and s[0].isdigit():
                parts = s.split()
                if len(parts) >= 9:
                    try:
                        vol = float(parts[5])
                        a = (vol * 4 / NATOMS) ** (1/3)
                        a_vals.append(a)
                    except: pass
    
    if not a_vals:
        return {'n_points': 0, 'a_mean': None, 'a_std': None, 'drift': None,
                'mean_press': None, 'std_press': None, 'result_a': result_a}
    
    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a)**2 for x in a_vals) / (n - 1))
    mean_vol = sum(vol_vals) / n
    mean_press = sum(press_vals) / n
    std_press = math.sqrt(sum((p - mean_press)**2 for p in press_vals) / (n - 1))
    half = n // 2
    drift = sum(a_vals[half:]) / (n - half) - sum(a_vals[:half]) / half
    
    return {
        'a_mean': mean_a, 'a_std': std_a, 'drift': drift,
        'n_points': n, 'result_a': result_a,
        'mean_vol': mean_vol,
        'mean_press': mean_press, 'std_press': std_press,
    }

# ── Runner ──
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
    
    # Copy default log
    default_log = f"{PROJ}/log.lammps"
    if os.path.exists(default_log):
        shutil.copy2(default_log, logpath)
    
    parsed = parse_log(logpath)
    return {'cfg': cfg, 'exit': result.returncode, 'time': dt, 'parsed': parsed, 'logpath': logpath}

# ══════════════════════════════════
# MAIN
# ══════════════════════════════════
def main():
    print("=" * 80)
    print("Pt CALIBRATION v3 — Thermal Expansion Matrix")
    print("=" * 80)
    print(f"  Potentials: EAM u3 (Foiles 1986), MEAM (Lee 2003)")
    print(f"  Temperatures: 300K, 1200K")
    print(f"  Total runs: {len(CALIB_MATRIX)}")
    print("=" * 80)
    
    results = {}
    
    # ── Resume mode: check existing logs ──
    logdir = f"{OUT}/logs"
    resumed = 0
    pending  = 0
    for i, cfg in enumerate(CALIB_MATRIX):
        label = cfg['label']
        logpath = f"{logdir}/log_{label}.lmp"
        if os.path.exists(logpath):
            parsed = parse_log(logpath)
            if parsed and parsed.get('n_points', 0) > 0:
                # Skip — already completed
                r = {'cfg': cfg, 'exit': 0, 'time': 0, 'parsed': parsed, 'logpath': logpath}
                results[label] = r
                resumed += 1
                continue
        pending += 1
    
    if resumed:
        print(f"\n  Resume: {resumed} runs already completed, {pending} remaining\n")
    else:
        print(f"\n  No completed runs found. {pending} runs to execute.\n")
    
    for i, cfg in enumerate(CALIB_MATRIX):
        label = cfg['label']
        if label in results:
            # Already loaded from resume
            continue
        
        print(f"\n[{i+1}/{len(CALIB_MATRIX)}] {label}...", end="", flush=True)
        
        r = run_one(cfg)
        results[label] = r
        
        parsed = r.get('parsed') or {}
        if parsed.get('n_points', 0) > 0:
            print(f"  a={parsed['a_mean']:.4f} ±{parsed['a_std']:.5f}  "
                  f"P={parsed['mean_press']:.1f}±{parsed['std_press']:.1f}  "
                  f"drift={parsed['drift']:.5f}  "
                  f"[{parsed['n_points']}pts]  {r['time']:.0f}s  ✓")
        else:
            err = parsed.get('error') or ''
            print(f"  FAILED (exit={r['exit']}){' '+err if err else ''}")
    
    # ── Analysis ──
    print("\n\n" + "=" * 120)
    print("CALIBRATION RESULTS — Pt thermal expansion")
    print("=" * 120)
    
    header = f"{'Label':<45} {'T':>5} {'a_mean':>8} {'a_std':>8} {'drift':>8} {'P_mean':>8} {'n':>6} {'time':>5}"
    print(header)
    print("-" * 120)
    
    # Group by potential and temperature
    by_pot_T = {}
    for r in results.values():
        parsed = r.get('parsed') or {}
        if parsed.get('n_points', 0) > 0:
            print(f"{r['cfg']['label']:<45} {r['cfg']['T']:>5} {parsed['a_mean']:>8.4f} "
                  f"{parsed['a_std']:>8.5f} {parsed['drift']:>8.5f} {parsed['mean_press']:>8.1f} "
                  f"{parsed['n_points']:>6} {r['time']:>4.0f}s")
            key = (r['cfg']['pot'], r['cfg']['T'])
            if key not in by_pot_T: by_pot_T[key] = []
            by_pot_T[key].append((r['cfg']['label'], parsed))
    
    # ── CTE analysis ──
    print("\n\n" + "=" * 120)
    print("CTE ANALYSIS (Δa / (a300 * 900K))")
    print("=" * 120)
    
    # Find runs with both 300K and 1200K
    runs_by_label = {}
    for r in results.values():
        if r.get('parsed') and (r.get('parsed') or {}).get('n_points', 0) > 0:
            # Create a key from the label without temperature
            base = r['cfg']['label'].replace('_T300', '_TX').replace('_T1200', '_TX')
            if base not in runs_by_label:
                runs_by_label[base] = {}
            runs_by_label[base][r['cfg']['T']] = r['parsed']['a_mean']
    
    header2 = f"{'Setting':<45} {'a300':>8} {'a1200':>8} {'Δa':>8} {'CTE':>10} {'vs_exp':>7}"
    print(header2)
    print("-" * 120)
    
    for base, temps in sorted(runs_by_label.items()):
        if 300 in temps and 1200 in temps:
            a300 = temps[300]
            a1200 = temps[1200]
            delta = a1200 - a300
            cte = delta / (a300 * 900)
            ratio = cte / EXP_CTE
            setting = base.replace('_TX', '_T').replace('eam_u3_', 'EAM ').replace('meam_', 'MEAM ')
            print(f"{setting:<45} {a300:>8.4f} {a1200:>8.4f} {delta:>8.4f} "
                  f"{cte*1e6:>8.2f}e-6 {ratio:>6.2f}x")
    
    # ── Comparison with baseline ──
    print("\n\n" + "=" * 120)
    print("COMPARISON WITH BASELINE (Pdamp=10.0, 10k/50k, iso)")
    print("=" * 120)
    
    for pot_name in ['eam_u3', 'meam']:
        print(f"\n  {pot_name.upper()}:")
        # Find baseline run
        base_300 = None
        base_1200 = None
        for base, temps in runs_by_label.items():
            if f"{pot_name}_T" in base and 'pdamp10' in base and 'long' not in base and 'aniso' not in base:
                if 300 in temps: base_300 = temps[300]
                if 1200 in temps: base_1200 = temps[1200]
        
        for base, temps in sorted(runs_by_label.items()):
            if pot_name not in base: continue
            if 300 in temps and 1200 in temps:
                a300 = temps[300]
                a1200 = temps[1200]
                delta = a1200 - a300
                cte = delta / (a300 * 900)
                diff_300 = (a300 - (base_300 or 0)) * 1000
                diff_1200 = (a1200 - (base_1200 or 0)) * 1000
                label_short = base.replace(f'{pot_name}_', '').replace('_TX', '')
                print(f"    {label_short:<30}  a300={a300:.4f} ({diff_300:+.2f}mÅ)  "
                      f"a1200={a1200:.4f} ({diff_1200:+.2f}mÅ)  "
                      f"Δa={delta:.4f}  CTE={cte*1e6:.2f}e-6")
    
    # ── Best result ──
    print("\n\n" + "=" * 120)
    print("BEST CTE for each potential")
    print("=" * 120)
    
    for pot_name in ['eam_u3', 'meam']:
        best_cte = 0
        best_label = ""
        for base, temps in runs_by_label.items():
            if pot_name not in base: continue
            if 300 in temps and 1200 in temps:
                a300 = temps[300]
                a1200 = temps[1200]
                delta = a1200 - a300
                cte = delta / (a300 * 900)
                if cte > best_cte:
                    best_cte = cte
                    best_label = base.replace(f'{pot_name}_', '')
        
        print(f"  {pot_name.upper()}: best CTE = {best_cte*1e6:.2f}×10⁻⁶ ({best_label})")
        print(f"    vs EAM baseline: {BASELINE_CTE.get(pot_name, 0)*1e6:.2f}×10⁻⁶")
        print(f"    vs experimental: {EXP_CTE*1e6:.1f}×10⁻⁶")
    
    # ── Save CSV ──
    csv_path = f"{OUT}/pt_calibration_matrix.csv"
    with open(csv_path, 'w') as f:
        f.write("label,pot,T_K,pdamp,eq,prod,mode,a_mean_Angstrom,a_std_Angstrom,drift,mean_press_bar,std_press_bar,n_points,time_s,exit_code\n")
        for label, r in sorted(results.items()):
            cfg = r['cfg']
            parsed = r.get('parsed') or {}
            if parsed.get('n_points', 0) > 0:
                f.write(f"{label},{cfg['pot']},{cfg['T']},{cfg['pdamp']},{cfg['eq']},{cfg['prod']},"
                       f"{cfg['mode']},{parsed['a_mean']:.6f},{parsed['a_std']:.6f},{parsed['drift']:.6e},"
                       f"{parsed['mean_press']:.2f},{parsed['std_press']:.2f},{parsed['n_points']},{r['time']:.1f},{r['exit']}\n")
            else:
                f.write(f"{label},{cfg['pot']},{cfg['T']},{cfg['pdamp']},{cfg['eq']},{cfg['prod']},"
                       f"{cfg['mode']},,,,,,,{r['time']:.1f},{r['exit']}\n")
    print(f"\n✓ CSV: {csv_path}")
    
    print("\n\nCALIBRATION DONE.")

if __name__ == '__main__':
    t0 = time.time()
    main()
    print(f"\nTotal time: {(time.time()-t0)/60:.1f} min")
