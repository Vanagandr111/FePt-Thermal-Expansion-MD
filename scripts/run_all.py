#!/usr/bin/env python3
"""
Fe-Pt thermal expansion simulation runner.
Generates structures, runs LAMMPS MEAM at each T, extracts a(T), plots.
"""
import sys
import os
import subprocess
import re
import csv
import time
import json

# Absolute paths (no Cyrillic!) via /tmp symlinks
PROJDIR = "/mnt/c/проекты/Nikolay"
DATA_DIR = os.path.join(PROJDIR, "data")
POT_DIR = os.path.join(PROJDIR, "potentials")
OUTPUT = os.path.join(PROJDIR, "output")
DATA_DIR = os.path.join(PROJDIR, "data")
SCRIPTS = os.path.join(PROJDIR, "scripts")

COMPOSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
# Single T first for quick test, then loop
QUICK_TEMPS = [300, 600, 900, 1200]
FULL_TEMPS = list(range(300, 1301, 100))

def gen_structure(comp, nx=4, ny=4, nz=4):
    """Generate LAMMPS data file for given composition."""
    outfile = os.path.join(DATA_DIR, f"data.fept_c{comp:.2f}.lmp")
    if os.path.exists(outfile):
        return outfile
    
    gen_script = os.path.join(SCRIPTS, "gen_structure.py")
    subprocess.run(
        ["python3", gen_script, str(nx), str(ny), str(nz), str(comp), outfile],
        capture_output=True, timeout=30
    )
    return outfile

def run_lammps(datafile, comp, T, outdir, quick=True):
    """Run LAMMPS at single T."""
    in_script = os.path.join(SCRIPTS, "in.thermal")
    os.makedirs(outdir, exist_ok=True)
    logfile = os.path.join(outdir, f"log_{T}.lmp")
    steps = "run 20000"  # reduced for quick
    
    # Copy in.thermal with proper values
    with open(in_script, 'r') as f:
        content = f.read()
    
    content = re.sub(r'variable datafile index .*', 
                     f'variable datafile index {datafile}', content)
    content = re.sub(r'variable T index .*', 
                     f'variable T index {T}', content)
    content = re.sub(r'variable comp index .*', 
                     f'variable comp index {comp:.2f}', content)
    
    # Reduce steps if quick
    if quick:
        content = re.sub(r'run\s+\d+', 'run 5000', content, count=2)
    
    with open(logfile.replace('.lmp', '.in'), 'w') as f:
        f.write(content)
    
    result = subprocess.run(
        ["lmp", "-in", logfile.replace('.lmp', '.in'), "-log", logfile],
        capture_output=True, text=True, timeout=180 if quick else 600
    )
    
    # Find RESULT line
    for line in (result.stdout or "").split('\n'):
        if 'RESULT:' in line:
            return parse_result(line)
    
    # Fallback: parse log
    if os.path.exists(logfile):
        with open(logfile) as f:
            for line in f:
                if 'RESULT:' in line:
                    return parse_result(line)
    
    return None

def parse_result(line):
    """Parse RESULT: T=... A=... line."""
    m = re.search(r'RESULT:\s+T=(\d+)', line)
    if not m:
        return None
    return {
        'T': int(m.group(1)),
        'comp': float(re.search(r'COMP=([\d.]+)', line).group(1)),
        'vol': float(re.search(r'VOL=([\d.]+)', line).group(1)),
        'lx': float(re.search(r'LX=([\d.]+)', line).group(1)),
        'a': float(re.search(r'A=([\d.]+)', line).group(1)),
        'natoms': int(re.search(r'NATOMS=(\d+)', line).group(1)),
    }

def main():
    quick = '--full' not in sys.argv
    temps = QUICK_TEMPS if quick else FULL_TEMPS
    
    print(f"{'QUICK RUN' if quick else 'FULL RUN'}")
    print(f"Compositions: {COMPOSITIONS}")
    print(f"Temperatures: {temps}")
    
    all_results = {}
    
    for comp in COMPOSITIONS:
        print(f"\n--- Pt={comp:.2f} ---")
        
        # Generate structure
        datafile = gen_structure(comp)
        outdir = os.path.join(OUTPUT, f"comp_{comp:.2f}")
        
        all_results[comp] = []
        
        for T in temps:
            print(f"  T={T}K...", end="", flush=True)
            result = run_lammps(datafile, comp, T, outdir, quick=quick)
            if result:
                print(f" a={result['a']:.4f}Å")
                all_results[comp].append(result)
            else:
                print(" FAILED")
    
    # Write output
    write_results(all_results, OUTPUT)
    plot_results(all_results, OUTPUT)

def write_results(all_results, outdir):
    """Write CSV files."""
    # Individual CSVs
    for comp, results in all_results.items():
        csv_file = os.path.join(outdir, f"a_T_comp_{comp:.2f}.csv")
        with open(csv_file, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['T_K', 'a_Angstrom', 'Volume_Ang3'])
            for r in results:
                w.writerow([r['T'], r['a'], r['vol']])
    
    # Summary
    csv_file = os.path.join(outdir, "a_vs_comp_summary.csv")
    all_Ts = sorted(set(r['T'] for comp in all_results.values() for r in comp))
    comps_sorted = sorted(all_results.keys())
    
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
        subprocess.run(["pip3", "install", "matplotlib", "-q"], timeout=60)
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

if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Total: {(time.time()-t0)/60:.1f} min")
