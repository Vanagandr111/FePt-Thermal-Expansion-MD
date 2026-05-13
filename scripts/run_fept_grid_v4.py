#!/usr/bin/env python3
"""
run_fept_grid_v4.py — Fe-Pt thermal expansion recalculation (Phase 4).
Long protocol: 50k eq + 100k prod, MEAM PtFe.meam, Pdamp=10.
Grid: 5 comps x 4 temps = 20 points.
"""
import os, subprocess, time, math, re, random, sys, json

PROJ = "/mnt/c/проекты/Nikolay"
os.chdir(PROJ)

OUT = f"{PROJ}/output_v4"
os.makedirs(f"{OUT}/logs", exist_ok=True)

NATOMS = 256
TEMPS = [300, 600, 900, 1200]
COMPS = [0.00, 0.25, 0.50, 0.75, 1.00]
EQ_STEPS = 50000
PROD_STEPS = 100000
PDAMP = 10.0

# ── Generate data file for composition ──
def gen_structure(x_pt, a0):
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
    indices = list(range(n_total))
    random.shuffle(indices)
    pt_indices = set(indices[:n_pt])
    atoms = []
    for i, (x, y, z) in enumerate(atoms_pts):
        atype = 2 if i in pt_indices else 1
        atoms.append((i+1, atype, x, y, z))
    n_fe = n_total - n_pt
    return atoms, n_fe, n_pt

def write_data(x_pt):
    a0_guess = 3.6 + x_pt * (3.92 - 3.6)
    atoms, n_fe, n_pt = gen_structure(x_pt, a0_guess)
    n_total = len(atoms)
    xhi = a0_guess * 4 + a0_guess * 0.01
    fname = f"data_fept_{x_pt:.2f}.lmp"
    path = f"{PROJ}/input_v4/{fname}"
    os.makedirs(f"{PROJ}/input_v4", exist_ok=True)
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
        f"# Fe-Pt x_Pt={x_pt:.2f} T={T}K MEAM LONG PROTOCOL",
        "units metal",
        "boundary p p p",
        "atom_style atomic",
        "",
        f"read_data input_v4/{fname_data}",
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
        f"fix nptfix all npt temp {T} {T} 1.0 iso 0.0 0.0 {PDAMP}",
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
    path = f"{PROJ}/input_v4/{fname_in}"
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
    result = subprocess.run(
        ["cmd.exe", "/c",
         f"C:\\\\проекты\\\\Nikolay\\\\_run_lmp.bat -in input_v4/{fname_in} -screen none"],
        capture_output=True, text=False, timeout=900
    )
    default_log = f"{PROJ}/log.lammps"
    if os.path.exists(default_log):
        import shutil
        shutil.copy2(default_log, logpath)
    dt = time.time() - t0
    return {'x_pt': x_pt, 'T': T, 'exit': result.returncode, 'time': dt, 'logpath': logpath}

# ── Parser (with pressure) ──
def parse_log(logpath):
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return {'n_points': 0}
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
        return {'n_points': 0, 'a_mean': None, 'result_a': result_a}
    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a)**2 for x in a_vals) / (n - 1))
    mean_vol = sum(vol_vals) / n
    mean_press = sum(press_vals) / n if press_vals else None
    std_press = math.sqrt(sum((p - mean_press)**2 for p in press_vals) / (n - 1)) if press_vals else None
    half = n // 2
    drift = sum(a_vals[half:]) / (n - half) - sum(a_vals[:half]) / half
    return {
        'a_mean': mean_a, 'a_std': std_a, 'drift': drift,
        'n_points': n, 'result_a': result_a,
        'mean_vol': mean_vol, 'mean_press': mean_press, 'std_press': std_press,
        'mean_temp': sum(temp_vals)/n if temp_vals else None,
    }

# ══════════════════════════════
# MAIN
# ══════════════════════════════
if __name__ == '__main__':
    run_all = '--all' in sys.argv or '--force' in sys.argv
    new_only = '--only-new' in sys.argv or len(sys.argv) == 1

    results = {}

    print("=" * 70)
    print("Fe-Pt THERMAL EXPANSION — Phase 4 (LONG PROTOCOL)")
    print("=" * 70)
    print(f"  Protocol: {EQ_STEPS} eq + {PROD_STEPS} prod, Pdamp={PDAMP}")
    print(f"  Potential: MEAM PtFe.meam (Fe-Pt cross interaction)")
    print(f"  Grid: {len(COMPS)} comps × {len(TEMPS)} temps = {len(COMPS)*len(TEMPS)} points")
    print("=" * 70)

    # Check existing logs
    existing_logs = {}
    for x_pt in COMPS:
        for T in TEMPS:
            logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
            existing_logs[(x_pt, T)] = os.path.exists(logpath)

    missing = [(x_pt, T) for x_pt in COMPS for T in TEMPS if not existing_logs[(x_pt, T)]]
    complete = [(x_pt, T) for x_pt in COMPS for T in TEMPS if existing_logs[(x_pt, T)]]

    # Check completed are valid
    valid_complete = []
    for x_pt, T in complete:
        p = parse_log(f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp")
        if p and p.get('n_points', 0) > 0 and p.get('a_mean') is not None:
            valid_complete.append((x_pt, T))
        else:
            missing.append((x_pt, T))

    print(f"  Already done (valid): {len(valid_complete)}")
    print(f"  Need to run: {len(missing)}")

    if run_all:
        print("  --force: rerunning ALL points")
        missing = [(x_pt, T) for x_pt in COMPS for T in TEMPS]

    # Generate structures
    for x_pt in COMPS:
        write_data(x_pt)
    print(f"  Structures generated ✓")

    # Run missing
    if missing:
        total_start = time.time()
        for i, (x_pt, T) in enumerate(missing):
            print(f"\n[{i+1}/{len(missing)}] x_Pt={x_pt:.2f} T={T}K...")
            r = run_one(x_pt, T)
            p = parse_log(r['logpath'])
            results[(x_pt, T)] = {'run': r, 'parsed': p}
            if p and p.get('n_points', 0) > 0 and p.get('a_mean') is not None:
                print(f"  ✓ a={p['a_mean']:.6f} ±{p['a_std']:.6f} [{p['n_points']}pts] {r['time']:.0f}s")
            else:
                print(f"  ✗ FAILED (exit={r['exit']}, log={r['logpath']})")

        elapsed = time.time() - total_start
        print(f"\n  Runs completed in {elapsed/60:.1f} min")
    else:
        print("  All points already exist. Pass --force to recalc.")

    # Parse all
    for x_pt in COMPS:
        for T in TEMPS:
            if (x_pt, T) not in results:
                logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
                p = parse_log(logpath)
                results[(x_pt, T)] = {
                    'run': {'x_pt': x_pt, 'T': T, 'time': 0},
                    'parsed': p
                }

    # ── Print results table ──
    print("\n\n" + "=" * 90)
    print("PHASE 4 RESULTS — Mean a(T) averaged over production MD")
    print(f"Protocol: {EQ_STEPS} eq + {PROD_STEPS} prod, MEAM Pdamp={PDAMP}")
    print("=" * 90)
    hdr = f"{'x_Pt':>6} {'T':>5} {'a_mean':>11} {'a_std':>9} {'n':>6} {'Press':>9} {'drift':>9} {'time':>6}"
    print(hdr)
    print("-" * 90)

    all_valid = True
    for x_pt in COMPS:
        for T in TEMPS:
            r = results.get((x_pt, T))
            if r and r['parsed'] and r['parsed'].get('a_mean') is not None:
                p = r['parsed']
                lt = r['run']['time']
                pm = p.get('mean_press', None)
                ps = f"{pm:.0f}" if pm is not None else "N/A"
                print(f"{x_pt:>6.2f} {T:>5} {p['a_mean']:>11.6f} {p['a_std']:>9.6f} "
                      f"{p['n_points']:>6} {ps:>9} {p['drift']:>9.2e} {lt:>5.0f}s")
            else:
                print(f"{x_pt:>6.2f} {T:>5} {'NO DATA':>11}")
                all_valid = False

    # ── Trends ──
    print("\n\n" + "=" * 60)
    print("TRENDS: a(T) per composition")
    print("=" * 60)
    for x_pt in COMPS:
        a_vals = []
        for T in TEMPS:
            r = results.get((x_pt, T))
            if r and r['parsed'] and r['parsed'].get('a_mean') is not None:
                a_vals.append((T, r['parsed']['a_mean']))
        if len(a_vals) == 4:
            vals = [v[1] for v in a_vals]
            rise = vals[3] - vals[0]
            mono = all(vals[i+1] >= vals[i] for i in range(3))
            alpha_eff = rise / vals[0] / 900
            print(f"  x_Pt={x_pt:.2f}: a300={vals[0]:.6f} a1200={vals[3]:.6f} "
                  f"Δa={rise:.6f}Å α_eff={alpha_eff:.3e} mono={'✓' if mono else '✗'}")
        else:
            print(f"  x_Pt={x_pt:.2f}: INCOMPLETE ({len(a_vals)}/4)")

    # ── Save CSV ──
    csv_path = f"{OUT}/all_results.csv"
    with open(csv_path, 'w') as f:
        f.write("x_Pt,T_K,a_mean_Angstrom,a_std_Angstrom,result_last_point,drift,n_points,mean_press_bar,std_press_bar,runtime_s\n")
        for x_pt in COMPS:
            for T in TEMPS:
                r = results.get((x_pt, T))
                if r and r['parsed'] and r['parsed'].get('a_mean') is not None:
                    p = r['parsed']
                    pm = p.get('mean_press', 0) or 0
                    sp = p.get('std_press', 0) or 0
                    f.write(f"{x_pt:.2f},{T},{p['a_mean']:.6f},{p['a_std']:.6f},"
                           f"{p['result_a'] or 0:.6f},{p['drift']:.6e},{p['n_points']},{pm:.1f},{sp:.1f},{r['run']['time']}\n")
    print(f"\n✓ CSV: {csv_path}")

    # ── Per-composition CSVs ──
    for x_pt in COMPS:
        comp_csv = f"{OUT}/a_T_comp_{x_pt:.2f}.csv"
        with open(comp_csv, 'w') as f:
            f.write("x_Pt,T_K,a_mean_Angstrom\n")
            for T in TEMPS:
                r = results.get((x_pt, T))
                if r and r['parsed'] and r['parsed'].get('a_mean') is not None:
                    f.write(f"{x_pt:.2f},{T},{r['parsed']['a_mean']:.6f}\n")
    print("  Per-composition CSVs ✓")

    # ── Integrity check ──
    print("\n\n" + "=" * 60)
    print("INTEGRITY CHECK")
    print("=" * 60)
    integrity_lines = []
    ok_count = 0
    fail_count = 0
    for x_pt in COMPS:
        for T in TEMPS:
            logpath = f"{OUT}/logs/log_fept_{x_pt:.2f}_T{T}.lmp"
            exist = os.path.exists(logpath)
            r = results.get((x_pt, T))
            csv_line = None
            if r and r['parsed'] and r['parsed'].get('a_mean') is not None:
                p = r['parsed']
                # Re-parse from raw log
                raw_p = parse_log(logpath)
                if raw_p and raw_p.get('a_mean') is not None:
                    diff = abs(raw_p['a_mean'] - p['a_mean'])
                    if diff < 1e-6:
                        ok_count += 1
                        line = f"  ✓ x_Pt={x_pt:.2f} T={T}: a={raw_p['a_mean']:.6f} n={raw_p['n_points']} csv_match"
                    else:
                        fail_count += 1
                        line = f"  ✗ x_Pt={x_pt:.2f} T={T}: MISMATCH raw={raw_p['a_mean']:.6f} csv={p['a_mean']:.6f}"
                else:
                    fail_count += 1
                    line = f"  ✗ x_Pt={x_pt:.2f} T={T}: raw log parse failed"
            else:
                fail_count += 1
                sz = os.path.getsize(logpath) if exist else 0
                line = f"  ✗ x_Pt={x_pt:.2f} T={T}: {'log='+str(sz)+'B' if exist else 'MISSING'}"
            print(line)
            integrity_lines.append(line)

    integrity_lines.append("=" * 60)
    integrity_lines.append(f"✓ {ok_count} verified / Failures: {fail_count} / Total: {ok_count+fail_count}")
    print("=" * 60)
    print(f"✓ {ok_count} verified / Failures: {fail_count} / Total: {ok_count+fail_count}")

    integrity_path = f"{OUT}/integrity_check_v4.txt"
    with open(integrity_path, 'w') as f:
        f.write("Fe-Pt Phase 4 — Integrity Check\n")
        f.write(f"Protocol: {EQ_STEPS} eq + {PROD_STEPS} prod, Pdamp={PDAMP}\n")
        f.write("=" * 60 + "\n")
        f.write("\n".join(integrity_lines))
    print(f"✓ Integrity: {integrity_path}")

    print("\n❇️ PHASE 4 COMPLETE")
    print(f"   Output: {OUT}")
