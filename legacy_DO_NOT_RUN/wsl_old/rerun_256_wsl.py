#!/usr/bin/env python3
"""
rerun_256.py — Re-run comp=0.00, 0.50, 1.00 with 256-atom structures.
Windows-first. Использует lmp_helper.
"""
import sys, os, csv, time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
import lmp_helper as lmp

COMPOSITIONS = [0.0, 0.50, 1.0]
TEMPS = [300, 600, 900, 1200]
N_EQUIL = 5000
N_PROD = 10000

def make_infile(datafile, comp, T, outdir):
    infile = os.path.join(outdir, f"in_{T}.lmp")
    lines = [
        f"# LAMMPS FePt MEAM T={T}K comp={comp:.2f} 256atoms",
        "",
        "units           metal",
        "boundary        p p p",
        "atom_style      atomic",
        "",
        f"read_data       {datafile}",
        "",
        "# MEAM 2NN (Kim-Koo-Lee 2006), fixed: 1=Fe 2=Pt",
        "pair_style      meam",
        f"pair_coeff      * * {lmp.POT_DIR}/library.meam Fe Pt {lmp.POT_DIR}/PtFe.meam Fe Pt",
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
        f"run             {N_EQUIL}",
        "thermo          500",
        f"run             {N_PROD}",
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
    return infile

def run_one(datafile, comp, T, outdir):
    infile = make_infile(datafile, comp, T, outdir)
    logfile = os.path.join(outdir, f"log_{T}.lmp")
    result = lmp.run_lmp(infile, logfile=logfile, timeout=300)
    r = lmp.extract_result_from_stdout(result)
    if r:
        return r
    r = lmp.extract_result_from_log(logfile)
    if r:
        return r
    err = (result.stderr or "")[:300]
    out_last = ((result.stdout or "").split('\n')[-3:])
    print(f"  ERROR! {out_last}")
    print(f"  stderr: {err}")
    return None

def write_csv(results):
    comps_sorted = sorted(results.keys())
    for comp, res in results.items():
        if not res:
            continue
        csvfile = os.path.join(lmp.OUTPUT, f"a_T_comp_{comp:.2f}.csv")
        with open(csvfile, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['T_K', 'a_Angstrom', 'Volume_Ang3'])
            for r in sorted(res, key=lambda x: x['T']):
                w.writerow([r['T'], f"{r['a']:.4f}", f"{r['vol']:.4f}"])
        print(f"  Wrote {csvfile}")
    all_Ts = sorted(set(r['T'] for lst in results.values() for r in lst))
    csvfile = os.path.join(lmp.OUTPUT, "a_vs_comp_summary.csv")
    with open(csvfile, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['T_K'] + [f"Pt_{c:.2f}" for c in comps_sorted])
        for T in all_Ts:
            row = [T]
            for comp in comps_sorted:
                match = [r['a'] for r in results.get(comp, []) if r['T'] == T]
                row.append(f"{match[0]:.4f}" if match else '')
            w.writerow(row)
    print(f"  Wrote {csvfile}")
    csvfile = os.path.join(lmp.OUTPUT, "all_results.csv")
    with open(csvfile, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Composition_Pt', 'T_K', 'a_Angstrom', 'Volume_Ang3', 'Natoms'])
        for comp in comps_sorted:
            for r in sorted(results.get(comp, []), key=lambda x: x['T']):
                w.writerow([f"{comp:.2f}", r['T'], f"{r['a']:.4f}", f"{r['vol']:.4f}", r['natoms']])
    print(f"  Wrote {csvfile}")

def plot_results(results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    comps_sorted = sorted(results.keys())
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    markers = ['o', 's', '^', 'D', 'v']
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, comp in enumerate(comps_sorted):
        res = results[comp]
        if not res:
            continue
        Ts = sorted([r['T'] for r in res])
        av = [r['a'] for r in sorted(res, key=lambda x: x['T'])]
        ax.plot(Ts, av, marker=markers[i], color=colors[i],
                label=f"Pt = {comp:.2f}", linewidth=1.5, markersize=8)
    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('Lattice Parameter a (Å)')
    ax.set_title('Fe-Pt Thermal Expansion (MEAM Kim-Koo-Lee 2006)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(lmp.OUTPUT, "a_vs_T_all.png"), dpi=150)
    plt.close(fig)
    print("  Saved a_vs_T_all.png")
    fig, ax = plt.subplots(figsize=(10, 6))
    sel_Ts = [300, 600, 900, 1200]
    for i, T in enumerate(sel_Ts):
        pts = [(c, r['a']) for c in comps_sorted for r in results.get(c, []) if r['T'] == T]
        if not pts or len(pts) < 2:
            continue
        comps_p, a_p = zip(*pts)
        c_arr = np.linspace(min(comps_p), max(comps_p), 50)
        a_arr = np.interp(c_arr, list(comps_p), list(a_p))
        ax.plot(c_arr, a_arr, '-', color=colors[i], alpha=0.2)
        ax.plot(comps_p, a_p, marker=markers[i], color=colors[i],
                label=f"T = {T} K", linewidth=1.5, markersize=10)
    ax.set_xlabel('Pt Composition (fraction)')
    ax.set_ylabel('Lattice Parameter a (Å)')
    ax.set_title('Fe-Pt Lattice Parameter vs Composition')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(lmp.OUTPUT, "a_vs_comp.png"), dpi=150)
    plt.close(fig)
    print("  Saved a_vs_comp.png")
    fig, ax = plt.subplots(figsize=(8, 5))
    for comp in [0.0, 1.0]:
        res = results.get(comp, [])
        if not res:
            continue
        Ts = sorted([r['T'] for r in res])
        av = [r['a'] for r in sorted(res, key=lambda x: x['T'])]
        label = "Pure Fe" if comp == 0.0 else "Pure Pt"
        ax.plot(Ts, av, marker='o', color='#1f77b4' if comp==0.0 else '#d62728',
                label=label, linewidth=2, markersize=8)
    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('Lattice Parameter a (Å)')
    ax.set_title('Thermal Expansion: Pure Fe and Pure Pt')
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(lmp.OUTPUT, "a_vs_T_pure.png"), dpi=150)
    plt.close(fig)
    print("  Saved a_vs_T_pure.png")

def main():
    t0 = time.time()
    new_results = {}
    for comp in COMPOSITIONS:
        datafile = os.path.join(lmp.DATA_DIR, f"data.fept_c{comp:.2f}.lmp")
        if not os.path.exists(datafile):
            print(f"ERROR: {datafile} not found!")
            continue
        outdir = os.path.join(lmp.OUTPUT, f"comp_{comp:.2f}")
        os.makedirs(outdir, exist_ok=True)
        new_results[comp] = []
        print(f"\n--- Pt={comp:.2f} (256 atoms) ---")
        for T in TEMPS:
            print(f"  T={T}K...", end="", flush=True)
            r = run_one(datafile, comp, T, outdir)
            if r:
                print(f" a={r['a']:.4f}Å")
                new_results[comp].append(r)
            else:
                print(" FAILED")
    elapsed = (time.time() - t0) / 60
    print(f"\nRe-run time: {elapsed:.1f} min")
    # Read existing results for 0.25, 0.75
    all_results = {}
    for comp in [0.0, 0.25, 0.50, 0.75, 1.0]:
        for T in TEMPS:
            logfile = os.path.join(lmp.OUTPUT, f"comp_{comp:.2f}", f"log_{T}.lmp")
            if os.path.exists(logfile):
                r = lmp.extract_result_from_log(logfile)
                if r:
                    if comp not in all_results:
                        all_results[comp] = []
                    all_results[comp].append(r)
    for comp in COMPOSITIONS:
        if comp in new_results:
            all_results[comp] = new_results[comp]
    for comp in [0.0, 0.25, 0.50, 0.75, 1.0]:
        if comp not in all_results or not all_results[comp]:
            print(f"WARNING: No results for Pt={comp:.2f}")
    print(f"\nResults summary:")
    for comp in sorted(all_results.keys()):
        for r in sorted(all_results[comp], key=lambda x: x['T']):
            print(f"  Pt={comp:.2f} T={r['T']}K a={r['a']:.4f}Å natoms={r['natoms']}")
    write_csv(all_results)
    plot_results(all_results)
    print(f"\nDONE! Total: {elapsed:.1f} min")

if __name__ == "__main__":
    main()
