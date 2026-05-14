#!/usr/bin/env python
"""
run_phase4.py — Phase 4 Long Protocol main run.
Windows-first. Output → output_v4/.

Protocol: 50k equilibration + 100k production, Pdamp=10.
Potential: MEAM PtFe.meam.
Grid: 5 comps × 4 temps = 20 points.
Production averaging for final a(T).

Usage:
    python scripts/run_phase4.py               # run missing points only
    python scripts/run_phase4.py --force        # clean 20/20 rerun all
    python scripts/run_phase4.py --help         # show this help
"""
import sys
import os
import time
import csv
import math
import re

# ── Project root from scripts/ ──
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)

if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import lmp_helper as lmp

# ── Phase 4 Parameters ──
COMPOSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 600, 900, 1200]
NATOMS = 256
EQ_STEPS = 50000
PROD_STEPS = 100000
PDAMP = 10.0
OUT = os.path.join(_PROJ_DIR, 'output_v4')
LOGS = os.path.join(OUT, 'logs')

# ── LAMMPS input generation ──
POT_LINE = "pair_coeff      * * potentials{0}library.meam Fe Pt potentials{0}PtFe.meam Fe Pt".format(os.sep)

def write_input(datafile, comp, T):
    """Generate LAMMPS input for Phase 4 protocol."""
    os.makedirs(os.path.join(OUT, 'in'), exist_ok=True)
    fname = "in_phase4_{:.2f}_{}.lmp".format(comp, T)
    infile = os.path.join(OUT, 'in', fname)

    data_rel = os.path.relpath(datafile, _PROJ_DIR)

    lines = [
        "# Phase 4 Fe-Pt MEAM T={}K comp={:.2f}".format(T, comp),
        "units           metal",
        "boundary        p p p",
        "atom_style      atomic",
        "",
        "read_data       {}".format(data_rel),
        "",
        "pair_style      meam",
        POT_LINE,
        "",
        "neighbor        2.0 bin",
        "neigh_modify    every 1 delay 0 check yes",
        "",
        "thermo          100",
        "thermo_style    custom step temp pe ke press vol lx ly lz",
        "",
        "minimize        1.0e-6 1.0e-8 1000 10000",
        'print           "MINIMIZATION_DONE"',
        "",
        # Velocity initialization: CRITICAL — without this the NPT thermostat
        # has to heat the system from 0K, which takes forever and diverges at high T
        "velocity        all create {} 12345".format(T),
        "",
        "fix             nptfix all npt temp {} {} {} iso 0.0 0.0 {}".format(T, T, PDAMP, PDAMP),
        "",
        "thermo          1000",
        'print           "EQ_START"',
        "run             {}".format(EQ_STEPS),
        'print           "EQ_DONE"',
        "",
        "thermo          100",
        'print           "PRODUCTION_START"',
        "run             {}".format(PROD_STEPS),
        'print           "PRODUCTION_DONE"',
        "",
        "variable myvol  equal vol",
        "variable mya    equal (4.0*vol/count(all))^(1.0/3.0)",
        'print           "RESULT: COMP={:.2f} T={} A=${{mya}} VOL=${{myvol}}"'.format(comp, T),
        'print           "DONE"',
    ]
    with open(infile, 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    return infile


def run_point(datafile, comp, T, subdir):
    """Run LAMMPS at single T using lmp_helper."""
    os.makedirs(subdir, exist_ok=True)
    logfile = os.path.join(subdir, "log_{:.2f}_{}.lmp".format(comp, T))
    infile = write_input(datafile, comp, T)

    print("  T={}K...".format(T), end="", flush=True)
    t0 = time.time()
    result = lmp.run_lmp(infile, logfile=logfile, timeout=900)
    dt = time.time() - t0

    # Try stdout first
    r = lmp.extract_result_from_stdout(result)
    if r:
        print(" a={:.6f}A [{:.0f}s]".format(r['a'], dt))
        r['time'] = dt
        return r

    # Fallback: parse log
    r = lmp.extract_result_from_log(logfile)
    if r:
        print(" a={:.6f}A (log) [{:.0f}s]".format(r['a'], dt))
        r['time'] = dt
        return r

    print(" FAILED [{}s]".format(dt))
    return None


def parse_production(logpath):
    """Parse production phase for mean a(std), same as original run_fept_grid_v4."""
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return {'n_points': 0}

    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Extract RESULT line
    result_a = None
    for line in text.split('\n'):
        if 'RESULT:' in line and 'A=' in line:
            m = re.search(r'A=([\d.]+)', line)
            if m:
                result_a = float(m.group(1))

    # Parse production thermo
    in_prod = False
    a_vals, vol_vals, press_vals, temp_vals = [], [], [], []
    for line in text.split('\n'):
        s = line.strip()
        if 'PRODUCTION_START' in s:
            in_prod = True
            continue
        if 'PRODUCTION_DONE' in s:
            in_prod = False
            break
        if in_prod and s and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 9:
                try:
                    step = int(parts[0])
                    temp = float(parts[1])
                    press = float(parts[4])
                    vol = float(parts[5])
                    a = (vol * 4 / NATOMS) ** (1 / 3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                    press_vals.append(press)
                    temp_vals.append(temp)
                except Exception:
                    pass

    if not a_vals:
        # Fallback: parse after EQ_DONE
        in_prod = False
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
                        a = (vol * 4 / NATOMS) ** (1 / 3)
                        a_vals.append(a)
                    except Exception:
                        pass

    if not a_vals:
        return {'n_points': 0, 'a_mean': None, 'result_a': result_a}

    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a_vals) / max(n - 1, 1))
    mean_vol = sum(vol_vals) / n if vol_vals else 0
    mean_press = sum(press_vals) / n if press_vals else None
    std_press = math.sqrt(sum((p - mean_press) ** 2 for p in press_vals) / max(len(press_vals) - 1, 1)) if press_vals else None
    half = n // 2
    drift = sum(a_vals[half:]) / max(n - half, 1) - sum(a_vals[:half]) / max(half, 1)
    mean_temp = sum(temp_vals) / n if temp_vals else None

    return {
        'a_mean': mean_a,
        'a_std': std_a,
        'drift': drift,
        'n_points': n,
        'result_a': result_a,
        'mean_vol': mean_vol,
        'mean_press': mean_press,
        'std_press': std_press,
        'mean_temp': mean_temp,
    }


def write_csv(all_results, parsed_all):
    """Write Phase 4 CSVs."""
    os.makedirs(OUT, exist_ok=True)

    # Main results CSV
    csv_path = os.path.join(OUT, "all_results.csv")
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['x_Pt', 'T_K', 'a_mean_Angstrom', 'a_std_Angstrom',
                     'result_last_point', 'drift', 'n_points',
                     'mean_press_bar', 'std_press_bar', 'runtime_s'])
        for comp in COMPOSITIONS:
            for T in TEMPS:
                p = parsed_all.get((comp, T), {})
                if p and p.get('a_mean') is not None:
                    w.writerow([
                        "{:.2f}".format(comp), T,
                        "{:.6f}".format(p['a_mean']),
                        "{:.6f}".format(p.get('a_std', 0)),
                        "{:.6f}".format(p.get('result_a', 0) or 0),
                        "{:.6e}".format(p.get('drift', 0)),
                        p.get('n_points', 0),
                        "{:.1f}".format(p.get('mean_press', 0) or 0),
                        "{:.1f}".format(p.get('std_press', 0) or 0),
                        p.get('runtime', 0),
                    ])
    print("  CSV: {}".format(csv_path))

    # Per-composition CSVs
    for comp in COMPOSITIONS:
        comp_csv = os.path.join(OUT, "a_T_comp_{:.2f}.csv".format(comp))
        with open(comp_csv, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['x_Pt', 'T_K', 'a_mean_Angstrom'])
            for T in TEMPS:
                p = parsed_all.get((comp, T), {})
                if p and p.get('a_mean') is not None:
                    w.writerow(["{:.2f}".format(comp), T, "{:.6f}".format(p['a_mean'])])
    print("  Per-composition CSVs ✓")

    return csv_path


def plot_v4(parsed_all):
    """Generate Phase 4 plots: a(T), a(comp), facets."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "matplotlib", "-q"],
                       timeout=60)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    # 1. a(T) all comps
    fig, ax = plt.subplots(figsize=(10, 7))
    for ci, comp in enumerate(COMPOSITIONS):
        pts = [(T, parsed_all[(comp, T)]) for T in TEMPS
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            ts = [p[0] for p in pts]
            avs = [p[1]['a_mean'] for p in pts]
            errs = [p[1].get('a_std', 0) for p in pts]
            ax.plot(ts, avs, 'o-', color=colors[ci],
                    label="x_Pt={:.2f}".format(comp), markersize=7, linewidth=2)
            ax.fill_between(ts,
                            [a - s for a, s in zip(avs, errs)],
                            [a + s for a, s in zip(avs, errs)],
                            alpha=0.15, color=colors[ci])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Lattice parameter a (Å)")
    ax.set_title("Fe-Pt Thermal Expansion — Phase 4 (Long Protocol)")
    ax.legend(fontsize=10, loc='upper left')
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "a_vs_T_all_v4.png"), dpi=150)
    plt.close(fig)
    print("  Plot: a_vs_T_all_v4.png")

    # 2. a(comp) at fixed T
    fig, ax = plt.subplots(figsize=(10, 7))
    for Ti, T in enumerate(TEMPS):
        pts = [(comp, parsed_all[(comp, T)]['a_mean'])
               for comp in COMPOSITIONS
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            xs = [p[0] for p in pts]
            avs = [p[1] for p in pts]
            ax.plot(xs, avs, 'o-', label="T={}K".format(T), markersize=8, linewidth=2)
    ax.set_xlabel("Pt fraction x_Pt")
    ax.set_ylabel("Lattice parameter a (Å)")
    ax.set_title("Fe-Pt a(comp) at fixed temperatures — Phase 4")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "a_vs_comp_v4.png"), dpi=150)
    plt.close(fig)
    print("  Plot: a_vs_comp_v4.png")

    # 3. Facets 2x3
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    fig.suptitle("Fe-Pt Thermal Expansion — Phase 4 (Long Protocol)", fontsize=14, fontweight='bold')
    axes_flat = axes.flatten()
    for ci, comp in enumerate(COMPOSITIONS):
        ax = axes_flat[ci]
        pts = [(T, parsed_all[(comp, T)]) for T in TEMPS
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            ts = [p[0] for p in pts]
            vs = [p[1] for p in pts]
            avs = [v['a_mean'] for v in vs]
            errs = [v.get('a_std', 0) for v in vs]
            ax.errorbar(ts, avs, yerr=errs, fmt='o-', color=colors[ci],
                        capsize=4, markersize=6)
            rise = avs[-1] - avs[0]
            alpha_eff = rise / avs[0] / 900
            ax.set_title("x_Pt={:.2f}\nΔa={:.4f}Å α={:.2e}".format(comp, rise, alpha_eff), fontsize=10)
            ax.set_xlabel("T (K)")
            ax.set_ylabel("a (Å)")
            ax.grid(alpha=0.3)
    for i in range(len(COMPOSITIONS), len(axes_flat)):
        axes_flat[i].set_visible(False)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "a_vs_T_facets_v4.png"), dpi=150)
    plt.close(fig)
    print("  Plot: a_vs_T_facets_v4.png")


def integrity_check(parsed_all, csv_path):
    """Write integrity check report."""
    integrity_path = os.path.join(OUT, "integrity_check_v4.txt")
    lines = [
        "Fe-Pt Phase 4 — Integrity Check",
        "Protocol: {} eq + {} prod, Pdamp={}".format(EQ_STEPS, PROD_STEPS, PDAMP),
        "MEAM potential: PtFe.meam (Fe-Pt cross interaction)",
        "Grid: {} comps × {} temps = {} points".format(
            len(COMPOSITIONS), len(TEMPS), len(COMPOSITIONS) * len(TEMPS)),
        "=" * 60,
    ]
    ok_count = 0
    fail_count = 0

    for comp in COMPOSITIONS:
        for T in TEMPS:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                ok_count += 1
                lines.append("  ✓ x_Pt={:.2f} T={}: a={:.6f} n={} drift={:.2e}".format(
                    comp, T, p['a_mean'], p.get('n_points', 0), p.get('drift', 0)))
            else:
                fail_count += 1
                lines.append("  ✗ x_Pt={:.2f} T={}: NO DATA".format(comp, T))

    lines.append("=" * 60)
    lines.append("✓ {} verified / Failures: {} / Total: {}".format(
        ok_count, fail_count, ok_count + fail_count))

    # Pt benchmark
    pt_300 = parsed_all.get((1.0, 300), {})
    pt_1200 = parsed_all.get((1.0, 1200), {})
    if pt_300 and pt_1200 and pt_300.get('a_mean') and pt_1200.get('a_mean'):
        a300 = pt_300['a_mean']
        a1200 = pt_1200['a_mean']
        alpha = (a1200 - a300) / a300 / 900
        lines.append("")
        lines.append("Pt benchmark:")
        lines.append("  a(300K) = {:.6f} Å  (expected ~3.929)".format(a300))
        lines.append("  a(1200K) = {:.6f} Å  (expected ~3.956)".format(a1200))
        lines.append("  α_eff = {:.3e}  (expected ~7.5e-6)".format(alpha))
        delta_a300 = abs(a300 - 3.929)
        lines.append("  Δa300 = {:.6f} Å from expected".format(delta_a300))

    with open(integrity_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print("  Integrity: {}".format(integrity_path))

    # Also print Pt benchmark
    print("\n  --- Pt Benchmark ---")
    print("  a(300K) = {:.6f} Å (expected ~3.929)".format(a300 if pt_300.get('a_mean') else 0))
    print("  a(1200K) = {:.6f} Å (expected ~3.956)".format(a1200 if pt_1200.get('a_mean') else 0))

    return ok_count, fail_count


def write_protocol_log():
    """Write protocol log to output_v4/."""
    proto_path = os.path.join(OUT, "run_main_protocol.txt")
    lines = [
        "Fe-Pt Phase 4 — run_main Protocol Log",
        "=" * 50,
        "Timestamp: {}".format(time.strftime('%Y-%m-%d %H:%M:%S')),
        "Script: run_phase4.py",
        "Pipeline: Phase 4 (Long Protocol)",
        "Potential: MEAM PtFe.meam",
        "Equilibration steps: {}".format(EQ_STEPS),
        "Production steps: {}".format(PROD_STEPS),
        "Pdamp: {}".format(PDAMP),
        "Compositions: {}".format(COMPOSITIONS),
        "Temperatures: {}".format(TEMPS),
        "Output dir: output_v4",
        "=" * 50,
    ]
    with open(proto_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print("  Protocol log: {}".format(proto_path))


def print_trends(parsed_all):
    """Print a(T) trends."""
    print("\n" + "=" * 60)
    print("TRENDS: a(T) per composition")
    print("=" * 60)
    for comp in COMPOSITIONS:
        a_vals = []
        for T in TEMPS:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                a_vals.append((T, p['a_mean']))
        if len(a_vals) == 4:
            vals = [v[1] for v in a_vals]
            rise = vals[3] - vals[0]
            mono = all(vals[i + 1] >= vals[i] for i in range(3))
            alpha_eff = rise / vals[0] / 900
            print("  x_Pt={:.2f}: a300={:.6f} a1200={:.6f} Δa={:.6f}Å α_eff={:.3e} {}".format(
                comp, vals[0], vals[3], rise, alpha_eff, '✓' if mono else '✗'))
        else:
            print("  x_Pt={:.2f}: INCOMPLETE ({}/4)".format(comp, len(a_vals)))


def main():
    force = '--force' in sys.argv

    print("=" * 70)
    print("Fe-Pt THERMAL EXPANSION — Phase 4 (LONG PROTOCOL)")
    print("=" * 70)
    print("  Protocol: {} eq + {} prod, Pdamp={}".format(EQ_STEPS, PROD_STEPS, PDAMP))
    print("  Potential: MEAM PtFe.meam (Fe-Pt cross interaction)")
    print("  Grid: {} comps × {} temps = {} points".format(
        len(COMPOSITIONS), len(TEMPS), len(COMPOSITIONS) * len(TEMPS)))
    print("  Output: {}".format(OUT))
    print("  LAMMPS: {}".format(lmp.find_lmp_display() or "NOT FOUND"))
    print("=" * 70)

    os.makedirs(LOGS, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)

    # Check existing logs
    existing = {}
    for comp in COMPOSITIONS:
        for T in TEMPS:
            logpath = os.path.join(LOGS, "log_{:.2f}_{}.lmp".format(comp, T))
            existing[(comp, T)] = os.path.exists(logpath)

    missing = [(comp, T) for comp in COMPOSITIONS for T in TEMPS
               if not existing[(comp, T)]]
    complete = [(comp, T) for comp in COMPOSITIONS for T in TEMPS
                if existing[(comp, T)]]

    # Validate completed
    valid_complete = []
    for comp, T in complete:
        logpath = os.path.join(LOGS, "log_{:.2f}_{}.lmp".format(comp, T))
        p = parse_production(logpath)
        if p and p.get('n_points', 0) > 0 and p.get('a_mean') is not None:
            valid_complete.append((comp, T))
        else:
            missing.append((comp, T))

    if force:
        print("  --force: rerunning ALL 20 points")
        missing = [(comp, T) for comp in COMPOSITIONS for T in TEMPS]
        valid_complete = []
    else:
        print("  Already done (valid): {}".format(len(valid_complete)))
        print("  Need to run: {}".format(len(missing)))

    # Generate structures for missing points
    if missing:
        print("\n  Generating structures...")
        for comp in COMPOSITIONS:
            lmp.gen_structure(comp)
        print("  Structures ready ✓")

    # Run missing points
    run_results = {}
    if missing:
        total_start = time.time()
        for i, (comp, T) in enumerate(missing):
            print("\n  [{}/{}] x_Pt={:.2f} T={}K".format(
                i + 1, len(missing), comp, T))
            subdir = os.path.join(LOGS, "comp_{:.2f}".format(comp))
            datafile = os.path.join(
                lmp.DATA_DIR,
                "data.fept_c{:.2f}.lmp".format(comp))
            r = run_point(datafile, comp, T, subdir)
            if r:
                # Copy log to LOGS
                log_src = os.path.join(subdir, "log_{:.2f}_{}.lmp".format(comp, T))
                log_dst = os.path.join(LOGS, "log_{:.2f}_{}.lmp".format(comp, T))
                if os.path.exists(log_src) and log_src != log_dst:
                    import shutil
                    shutil.copy2(log_src, log_dst)
                # Also check default log.lammps
                default_log = os.path.join(_PROJ_DIR, "log.lammps")
                if os.path.exists(default_log) and not os.path.exists(log_dst):
                    import shutil
                    shutil.copy2(default_log, log_dst)
            run_results[(comp, T)] = r

        elapsed = time.time() - total_start
        print("\n  Runs completed in {:.1f} min".format(elapsed / 60))

    # Parse all points
    parsed_all = {}
    for comp in COMPOSITIONS:
        for T in TEMPS:
            logpath = os.path.join(LOGS, "log_{:.2f}_{}.lmp".format(comp, T))
            p = parse_production(logpath)
            if (comp, T) in run_results and run_results[(comp, T)]:
                p['runtime'] = run_results[(comp, T)].get('time', 0)
            else:
                p['runtime'] = 0
            parsed_all[(comp, T)] = p

    # ── Print results table ──
    print("\n\n" + "=" * 100)
    print("PHASE 4 RESULTS — Mean a(T) averaged over production MD")
    print("Protocol: {} eq + {} prod, MEAM Pdamp={}".format(EQ_STEPS, PROD_STEPS, PDAMP))
    print("=" * 100)
    hdr = "{:>6} {:>5} {:>11} {:>9} {:>6} {:>9} {:>9} {:>6}".format(
        'x_Pt', 'T', 'a_mean', 'a_std', 'n', 'Press', 'drift', 'time')
    print(hdr)
    print("-" * 100)

    all_valid = True
    for comp in COMPOSITIONS:
        for T in TEMPS:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                pm = p.get('mean_press', None)
                ps = "{:.0f}".format(pm) if pm is not None else "N/A"
                print("{:>6.2f} {:>5} {:>11.6f} {:>9.6f} {:>6} {:>9} {:>9.2e} {:>5.0f}s".format(
                    comp, T, p['a_mean'], p.get('a_std', 0),
                    p.get('n_points', 0), ps, p.get('drift', 0),
                    p.get('runtime', 0)))
            else:
                print("{:>6.2f} {:>5} {:>11}".format(comp, T, 'NO DATA'))
                all_valid = False

    # ── Trends ──
    print_trends(parsed_all)

    # ── CSV ──
    csv_path = write_csv({}, parsed_all)

    # ── Plots ──
    try:
        plot_v4(parsed_all)
    except Exception as e:
        print("  Plotting error: {}".format(e))

    # ── Protocol log ──
    write_protocol_log()

    # ── Integrity check ──
    ok_count, fail_count = integrity_check(parsed_all, csv_path)

    print("\n" + "=" * 60)
    if fail_count == 0:
        print("✅ PHASE 4 COMPLETE — All {} points verified".format(ok_count))
    else:
        print("⚠️  PHASE 4 COMPLETE — {} verified, {} failures".format(ok_count, fail_count))
    print("   Output: {}".format(OUT))

    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
