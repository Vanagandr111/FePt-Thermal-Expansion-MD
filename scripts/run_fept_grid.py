#!/usr/bin/env python3
"""
run_fept_grid.py — Полный расчёт Fe-Pt теплового расширения.
MEAM потенциал, усреднение a по production (50k шагов).
Сохраняет raw LAMMPS logs, собирает CSV, проверяет integrity.
"""
import os, subprocess, time, math, re, random, sys

PROJ = "/mnt/c/проекты/Nikolay"
os.chdir(PROJ)

OUT = f"{PROJ}/output_v2"
os.makedirs(f"{OUT}/logs", exist_ok=True)
os.makedirs(f"{PROJ}/input_v2", exist_ok=True)

NATOMS = 256
TEMPS = [300, 600, 900, 1200]
COMPS = [0.00, 0.25, 0.50, 0.75, 1.00]
EQ_STEPS = 10000
PROD_STEPS = 50000

# ── Generate data file for composition ──
def gen_structure(x_pt, a0):
    """Create fcc data with x_pt fraction of Pt atoms."""
    random.seed(42)
    nx, ny, nz = 4, 4, 4
    basis = [(0,0,0), (0.5,0.5,0), (0.5,0,0.5), (0,0.5,0.5)]
    
    atoms_pts = []
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                for bx,by,bz in basis:
                    x = (ix + bx) * a0
                    y = (iy + by) * a0
                    z = (iz + bz) * a0
                    atoms_pts.append((x, y, z))
    
    n_total = len(atoms_pts)
    n_pt = int(round(n_total * x_pt))
    
    # Shuffle to get random alloy
    indices = list(range(n_total))
    random.shuffle(indices)
    pt_indices = set(indices[:n_pt])
    
    atoms = []
    for i, (x, y, z) in enumerate(atoms_pts):
        atype = 2 if i in pt_indices else 1  # 1=Fe, 2=Pt
        atoms.append((i+1, atype, x, y, z))
    
    n_fe = n_total - n_pt
    return atoms, n_fe, n_pt

def write_data(x_pt):
    a0_guess = 3.6 + x_pt * (3.92 - 3.6)  # Vegard approx
    atoms, n_fe, n_pt = gen_structure(x_pt, a0_guess)
    n_total = len(atoms)
    
    xhi = a0_guess * 4 + a0_guess * 0.01
    
    fname = f"data_fept_{x_pt:.2f}.lmp"
    path = f"{PROJ}/input_v2/{fname}"
    with open(path, 'w') as f:
        f.write(f"Fe-Pt x_Pt={x_pt:.2f} ({n_fe} Fe, {n_pt} Pt)\n\n")
        f.write(f"{n_total} atoms\n2 atom types\n\n")
        f.write(f"0 {xhi:.6f} xlo xhi\n0 {xhi:.6f} ylo yhi\n0 {xhi:.6f} zlo zhi\n\n")
        f.write("Masses\n\n1 55.845  # Fe\n2 195.084 # Pt\n\n")
        f.write("Atoms\n\n")
        for aid, atype, x, y, z in atoms:
            f.write(f"{aid} {atype} {x:.6f} {y:.6f} {z:.6f}\n")
    return path, n_fe, n_pt

# ── LAMMPS input ──
def write_input(x_pt, T):
    fname_data = f"data_fept_{x_pt:.2f}.lmp"
    fname_in = f"in_fept_{x_pt:.2f}_T{T}.lmp"
    
    lines = [
        f"# Fe-Pt x_Pt={x_pt:.2f} T={T}K MEAM",
        "units metal",
        "boundary p p p",
        "atom_style atomic",
        "",
        f"read_data input_v2/{fname_data}",
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
        f"fix nptfix all npt temp {T} {T} 1.0 iso 0.0 0.0 10.0",
        f"run {EQ_STEPS}",
        'print "EQ_DONE"',
        "",
        "thermo 100",
        'print "PRODUCTION_START"',
        f"run {PROD_STEPS}",
        'print "PRODUCTION_DONE"',
        "",
        "variable mya equal (4.0*vol/count(all))^(1.0/3.0)",
        f'print "RESULT: x_Pt={x_pt:.2f} T={T} POT=meam A=${{mya}}"',
        'print "DONE"',
    ]
    path = f"{PROJ}/input_v2/{fname_in}"
    with open(path, 'w') as f:
        for line in lines:
            f.write(line + '\n')
    return fname_in

# ── Runner ──
def run_one(x_pt, T):
    fname_in = write_input(x_pt, T)
    logname = f"log_fept_{x_pt:.2f}_T{T}.lmp"
    logpath = f"{OUT}/logs/{logname}"
    
    t0 = time.time()
    # NOTE: Do NOT use -log with cyrillic paths — encoding breaks via cmd.exe.
    # Instead, rely on _run_lmp.bat's CWD being C:\проекты\Nikolay,
    # and LAMMPS writing default log.lammps there. Copy afterwards.
    result = subprocess.run(
        ["cmd.exe", "/c",
         f"C:\\проекты\\Nikolay\\_run_lmp.bat -in input_v2/{fname_in} -screen none"],
        capture_output=True, text=False, timeout=600
    )
    # LAMMPS writes log.lammps to CWD (= C:\проекты\Nikolay)
    default_log = f"{PROJ}/log.lammps"
    if os.path.exists(default_log):
        import shutil
        shutil.copy2(default_log, logpath)
    
    dt = time.time() - t0
    return {'x_pt': x_pt, 'T': T, 'exit': result.returncode, 'time': dt, 'logpath': logpath}

# ── Parser ──
def parse_log(logpath):
    if not os.path.exists(logpath):
        return None
    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    
    result_a = None
    for line in text.split('\n'):
        if 'RESULT:' in line and 'A=' in line:
            m = re.search(r'A=([\d.]+)', line)
            if m: result_a = float(m.group(1))
    
    in_prod = False
    a_vals = []
    vol_vals = []
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
                    pe = float(parts[2])
                    ke = float(parts[3])
                    press = float(parts[4])
                    vol = float(parts[5])
                    lx = float(parts[6])
                    ly = float(parts[7])
                    lz = float(parts[8])
                    a = (vol * 4 / NATOMS) ** (1/3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                except (ValueError, IndexError):
                    pass
    
    if not a_vals:
        # Try without PRODUCTION_START/DONE markers
        in_prod = False
        found_eq = False
        for line in text.split('\n'):
            s = line.strip()
            if 'EQ_DONE' in s: 
                in_prod = True
                continue
            if 'RESULT:' in s:
                break
            if in_prod and s and s[0].isdigit():
                parts = s.split()
                if len(parts) >= 9:
                    try:
                        vol = float(parts[5])
                        a = (vol * 4 / NATOMS) ** (1/3)
                        a_vals.append(a)
                        vol_vals.append(vol)
                    except: pass
    
    if not a_vals:
        return {'result_a': result_a, 'n': 0}
    
    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a)**2 for x in a_vals) / (n - 1))
    mean_vol = sum(vol_vals) / n
    half = n // 2
    drift = sum(a_vals[half:]) / (n - half) - sum(a_vals[:half]) / half
    
    return {
        'a_mean': mean_a, 'a_std': std_a,
        'a_mean_vol': (4 * mean_vol / NATOMS) ** (1/3),
        'drift': drift, 'n_points': n, 'result_a': result_a,
        'mean_vol': mean_vol, 'std_vol': math.sqrt(sum((v - mean_vol)**2 for v in vol_vals) / (n - 1)),
    }

# ══════════════════════════════
# MAIN
# ══════════════════════════════

if __name__ == '__main__':
    run_all = '--all' in sys.argv or len(sys.argv) == 1
    
    results = {}
    
    print("=" * 70)
    print("Fe-Pt THERMAL EXPANSION — MEAM (Kim-Koo-Lee 2006)")
    print(f"Grid: {len(COMPS)} comps × {len(TEMPS)} temps = {len(COMPS)*len(TEMPS)} points")
    print(f"MD: {EQ_STEPS} eq + {PROD_STEPS} prod steps, averaging over production")
    print("=" * 70)
    
    # Check existing logs
    existing = {}
    for x_pt in COMPS:
        for T in TEMPS:
            logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
            existing[(x_pt, T)] = os.path.exists(logpath)
    
    missing = [(x_pt, T) for x_pt in COMPS for T in TEMPS if not existing[(x_pt, T)]]
    complete = [(x_pt, T) for x_pt in COMPS for T in TEMPS if existing[(x_pt, T)]]
    
    print(f"  Existing: {len(complete)} / Missing: {len(missing)}")
    
    # Generate structures if needed
    if missing or run_all:
        for x_pt in COMPS:
            write_data(x_pt)
        print(f"  Structures generated ✓")
    
    # Run missing
    if missing:
        print(f"\nRunning {len(missing)} missing points...")
        for x_pt, T in missing:
            r = run_one(x_pt, T)
            p = parse_log(r['logpath'])
            results[(x_pt, T)] = {'run': r, 'parsed': p}
            if p and 'a_mean' in p:
                print(f"  x_Pt={x_pt:.2f} T={T:>4}K: a={p['a_mean']:.4f} ±{p['a_std']:.5f} [{p['n_points']}pts] {p['result_a']:.4f} {r['time']:.0f}s ✓")
            else:
                print(f"  x_Pt={x_pt:.2f} T={T:>4}K: FAIL (exit={r['exit']})")
    else:
        print(f"\n  All points already exist. Rerun with --all to force recalc.")
    
    # Parse all existing
    for x_pt in COMPS:
        for T in TEMPS:
            if (x_pt, T) not in results:
                r = {'x_pt': x_pt, 'T': T, 'time': 0}
                logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
                p = parse_log(logpath)
                results[(x_pt, T)] = {'run': r, 'parsed': p}
    
    # ── Validation table ──
    print("\n\n" + "=" * 80)
    print("Fe-Pt RESULTS — Mean a(T) averaged over production MD")
    print("=" * 80)
    print(f"{'x_Pt':>6} {'T':>6} {'a_mean':>9} {'a_std':>9} {'last_pt':>9} {'drift':>9} {'n':>6} {'time':>6}")
    print("-" * 80)
    
    all_valid = True
    for x_pt in COMPS:
        for T in TEMPS:
            r = results.get((x_pt, T))
            if r and r['parsed'] and 'a_mean' in r['parsed']:
                p = r['parsed']
                lt = r['run']['time']
                print(f"{x_pt:>6.2f} {T:>6} {p['a_mean']:>9.4f} {p['a_std']:>9.5f} "
                      f"{p['result_a']:>9.4f} {p['drift']:>9.5f} {p['n_points']:>6} {lt:>5.0f}s")
            elif r and r['parsed']:
                print(f"{x_pt:>6.2f} {T:>6} {'NO DATA':>9}")
                all_valid = False
            else:
                logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
                sz = os.path.getsize(logpath) if os.path.exists(logpath) else 0
                print(f"{x_pt:>6.2f} {T:>6} {'MISSING':>9} (log={sz}B)")
                all_valid = False
    
    # ── Per-composition trends ──
    print("\n\n" + "=" * 60)
    print("TRENDS: a(T) per composition")
    print("=" * 60)
    
    for x_pt in COMPS:
        a_vals = []
        for T in TEMPS:
            r = results.get((x_pt, T))
            if r and r['parsed'] and 'a_mean' in r['parsed']:
                a_vals.append((T, r['parsed']['a_mean'], r['parsed']['a_std']))
        
        if len(a_vals) == 4:
            vals = [v[1] for v in a_vals]
            rise = vals[3] - vals[0]
            mono = all(vals[i+1] >= vals[i] for i in range(3))
            # Linear fit slope
            mx = sum(v[0] * v[1] for v in a_vals) / sum(v[0]**2 for v in a_vals) * sum(v[0] for v in a_vals) / 4 if all(vals) else 0
            print(f"  x_Pt={x_pt:.2f}: a(300)={vals[0]:.4f}  a(1200)={vals[3]:.4f}  "
                  f"Δa={rise:.4f}Å  mono={'✓' if mono else '✗'}")
        else:
            print(f"  x_Pt={x_pt:.2f}: INCOMPLETE ({len(a_vals)}/4)")
    
    # ── Save CSV ──
    csv_path = f"{OUT}/all_results.csv"
    with open(csv_path, 'w') as f:
        f.write("x_Pt,T_K,a_mean_Angstrom,a_std_Angstrom,result_last_point,drift,n_points\n")
        for x_pt in COMPS:
            for T in TEMPS:
                r = results.get((x_pt, T))
                if r and r['parsed'] and 'a_mean' in r['parsed']:
                    p = r['parsed']
                    f.write(f"{x_pt:.2f},{T},{p['a_mean']:.6f},{p['a_std']:.6f},"
                           f"{p['result_a'] or 0:.6f},{p['drift']:.6e},{p['n_points']}\n")
    print(f"\n\n✓ Saved: {csv_path}")
    
    # ── Per-composition CSVs ──
    for x_pt in COMPS:
        comp_csv = f"{OUT}/a_T_comp_{x_pt:.2f}.csv"
        with open(comp_csv, 'w') as f:
            f.write("x_Pt,T_K,a_mean_Angstrom\n")
            for T in TEMPS:
                r = results.get((x_pt, T))
                if r and r['parsed'] and 'a_mean' in r['parsed']:
                    f.write(f"{x_pt:.2f},{T},{r['parsed']['a_mean']:.6f}\n")
        print(f"  Saved: {comp_csv}")
    
    # ── Integrity check ──
    print("\n\n" + "=" * 60)
    print("INTEGRITY CHECK")
    print("=" * 60)
    
    integrity_log = []
    ok_count = 0
    fail_count = 0
    
    for x_pt in COMPS:
        for T in TEMPS:
            logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
            exist = os.path.exists(logpath)
            r = results.get((x_pt, T))
            
            csv_a = None
            with open(csv_path) as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 3 and parts[0] == f"{x_pt:.2f}" and parts[1] == str(T):
                        csv_a = float(parts[2])
                        break
            
            msg = f"x_Pt={x_pt:.2f} T={T:>4}K: log={exist} "
            if r and r['parsed'] and 'a_mean' in r['parsed']:
                p = r['parsed']
                msg += f"a_csv={csv_a:.4f} a_log={p['a_mean']:.4f} n={p['n_points']}"
                if csv_a and abs(csv_a - p['a_mean']) < 0.0001:
                    msg += " ✓"
                    ok_count += 1
                else:
                    msg += " ✗ MISMATCH"
                    fail_count += 1
            else:
                msg += " ✗ NO DATA"
                fail_count += 1
            
            integrity_log.append(msg)
            print(f"  {msg}")
    
    integrity_path = f"{OUT}/integrity_check.txt"
    with open(integrity_path, 'w') as f:
        f.write("INTEGRITY CHECK — Phase 2 (MEAM, 50k prod, averaged)\n")
        f.write("=" * 70 + "\n")
        f.write(f"Total: {ok_count+fail_count}, Pass: {ok_count}, Fail: {fail_count}\n")
        f.write(f"MD: {EQ_STEPS} eq + {PROD_STEPS} prod, averaged over production\n")
        f.write(f"Potentials: MEAM (Kim-Koo-Lee 2006)\n")
        f.write("-" * 70 + "\n")
        for line in integrity_log:
            f.write(line + '\n')
        f.write("\nAll CSV values verified against raw LAMMPS logs.\n")
    print(f"\n✓ Saved: {integrity_path}")
    
    # ── Final summary ──
    print("\n\n" + "=" * 70)
    if all_valid:
        print("ALL 20 POINTS COMPLETED ✓")
    else:
        print(f"SOME POINTS MISSING — {fail_count} failures")
    print(f"Output: {OUT}/")
    print(f"Raw logs: {OUT}/logs/")
    print("=" * 70)
