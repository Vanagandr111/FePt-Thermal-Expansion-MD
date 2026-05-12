#!/usr/bin/env python3
"""
run_all.py — Полный прогон Fe-Pt MD.
Windows-first. Использует lmp_helper для поиска LAMMPS и путей.
"""
import sys
import os
import csv
import time

# Добавляем scripts/ в sys.path для импорта lmp_helper
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import lmp_helper as lmp

COMPOSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
QUICK_TEMPS = [300, 600, 900, 1200]
FULL_TEMPS = list(range(300, 1301, 100))

def run_lammps(datafile, comp, T, outdir, quick=True):
    """Run LAMMPS at single T using lmp_helper."""
    os.makedirs(outdir, exist_ok=True)
    logfile = os.path.join(outdir, f"log_{T}.lmp")
    infile = os.path.join(outdir, f"in_{T}.lmp")
    steps = 5000 if quick else 20000

    # Generate LAMMPS input file with relative paths (we cd to PROJDIR in run_lmp)
    lines = [
        f"# LAMMPS FePt MEAM T={T}K comp={comp:.2f}",
        "",
        "units           metal",
        "boundary        p p p",
        "atom_style      atomic",
        "",
        f"read_data       data{os.sep}{os.path.basename(datafile)}",
        "",
        "pair_style      meam",
        f"pair_coeff      * * potentials{os.sep}library.meam Fe Pt potentials{os.sep}PtFe.meam Fe Pt",
        "",
        "neighbor        2.0 bin",
        "neigh_modify    every 1 delay 0 check yes",
        "",
        "thermo          100",
        "thermo_style    custom step temp pe ke press vol lx ly lz",
        "",
        "minimize        1.0e-6 1.0e-8 1000 10000",
        'print "MINIMIZATION_DONE"',
        "",
        f"fix             nptfix all npt temp {T} {T} 0.5 iso 0.0 0.0 1.0",
        "",
        "thermo          1000",
        f"run             {steps}",
        "thermo          500",
        f"run             {steps * 2}",
        "",
        "variable myvol equal vol",
        "variable mylx equal lx",
        "variable myly equal ly",
        "variable mylz equal lz",
        "variable mynat equal count(all)",
        "variable mya equal (4.0*vol/count(all))^(1.0/3.0)",
        "",
        f'print "RESULT: T={T} COMP={comp:.2f} VOL=${{myvol}} LX=${{mylx}} LY=${{myly}} LZ=${{mylz}} NATOMS=${{mynat}} A=${{mya}}"',
    ]
    with open(infile, 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')

    result = lmp.run_lmp(infile, logfile=logfile, timeout=180 if quick else 600)

    # Try stdout first
    r = lmp.extract_result_from_stdout(result)
    if r:
        return r

    # Fallback: parse log
    r = lmp.extract_result_from_log(logfile)
    if r:
        return r

    return None


def write_results(all_results, outdir):
    """Write CSV files."""
    os.makedirs(outdir, exist_ok=True)

    for comp, results in all_results.items():
        csv_file = os.path.join(outdir, f"a_T_comp_{comp:.2f}.csv")
        with open(csv_file, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['T_K', 'a_Angstrom', 'Volume_Ang3'])
            for r in results:
                w.writerow([r['T'], r['a'], r['vol']])

    comps_sorted = sorted(all_results.keys())
    all_Ts = sorted(set(r['T'] for comp in all_results.values() for r in comp))

    csv_file = os.path.join(outdir, "a_vs_comp_summary.csv")
    with open(csv_file, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['T_K'] + [f"Pt_{c:.2f}" for c in comps_sorted])
        for T in all_Ts:
            row = [T]
            for comp in comps_sorted:
                match = [r['a'] for r in all_results[comp] if r['T'] == T]
                row.append(f"{match[0]:.4f}" if match else '')
            w.writerow(row)

    print(f"\nResults saved to {outdir}")


def plot_results(all_results, outdir):
    """Generate plots."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "matplotlib", "-q"], timeout=60)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

    comps_sorted = sorted(all_results.keys())
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    markers = ['o', 's', '^', 'D', 'v']

    # a(T) plot
    plt.figure(figsize=(10, 6))
    for i, comp in enumerate(comps_sorted):
        results = all_results[comp]
        Ts = [r['T'] for r in results]
        as_ = [r['a'] for r in results]
        plt.plot(Ts, as_, marker=markers[i], color=colors[i],
                 label=f"Pt = {comp:.2f}", linewidth=1.5)
    plt.xlabel('Temperature (K)')
    plt.ylabel('Lattice Parameter a (Å)')
    plt.title('Fe-Pt Thermal Expansion (MEAM Kim-Koo-Lee 2006)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "a_vs_T.png"), dpi=150)
    plt.close()

    # a(comp) at select T
    if len(comps_sorted) >= 3:
        plt.figure(figsize=(10, 6))
        selected_Ts = [300, 600, 900, 1200]
        for i, T in enumerate(selected_Ts):
            comps, a_vals = [], []
            for comp in comps_sorted:
                match = [r for r in all_results[comp] if r['T'] == T]
                if match:
                    comps.append(comp)
                    a_vals.append(match[0]['a'])
            if len(comps) >= 2:
                import numpy as np
                c_s = np.linspace(min(comps), max(comps), 50)
                a_s = np.interp(c_s, comps, a_vals)
                plt.plot(c_s, a_s, '-', color=colors[i], alpha=0.2)
            plt.plot(comps, a_vals, marker=markers[i], color=colors[i],
                     label=f"T = {T} K", linewidth=1.5, markersize=8)
        plt.xlabel('Pt Composition (fraction)')
        plt.ylabel('Lattice Parameter a (Å)')
        plt.title('Fe-Pt Lattice Parameter vs Composition')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(outdir, "a_vs_comp.png"), dpi=150)
        plt.close()

    print(f"Plots saved to {outdir}")


def main():
    quick = '--full' not in sys.argv
    temps = QUICK_TEMPS if quick else FULL_TEMPS

    print(f"{'QUICK RUN' if quick else 'FULL RUN'}")
    print(f"LAMMPS: {lmp.find_lmp_display()}")
    print(f"Project: {lmp.PROJDIR}")
    print(f"Compositions: {COMPOSITIONS}")
    print(f"Temperatures: {temps}")

    all_results = {}

    for comp in COMPOSITIONS:
        print(f"\n--- Pt={comp:.2f} ---")
        datafile = lmp.gen_structure(comp)
        outdir = os.path.join(lmp.OUTPUT, f"comp_{comp:.2f}")

        all_results[comp] = []
        for T in temps:
            print(f"  T={T}K...", end="", flush=True)
            result = run_lammps(datafile, comp, T, outdir, quick=quick)
            if result:
                print(f" a={result['a']:.4f} A")
                all_results[comp].append(result)
            else:
                print(" FAILED")

    write_results(all_results, lmp.OUTPUT)
    plot_results(all_results, lmp.OUTPUT)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Total: {(time.time()-t0)/60:.1f} min")
