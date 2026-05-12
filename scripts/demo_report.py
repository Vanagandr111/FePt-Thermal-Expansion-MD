#!/usr/bin/env python3
"""
demo_report.py — парсит логи run_demo.bat и создаёт CSV + графики.
Запускается после LAMMPS в run_demo.bat.
Не требует ручных правок путей.
"""
import os, re, csv, sys

PROJDIR = os.environ.get('PROJECT_DIR', '')
if not PROJDIR:
    # Auto-detect: WSL (/mnt/c/...) or Windows (C:\...)
    if os.path.exists('/mnt/c/проекты/Nikolay'):
        PROJDIR = '/mnt/c/проекты/Nikolay'
    elif os.path.exists('C:\\проекты\\Nikolay'):
        PROJDIR = 'C:\\проекты\\Nikolay'
    else:
        # Fallback: assume we're already in project dir
        PROJDIR = os.getcwd()
OUTPUT = os.path.join(PROJDIR, 'output')

def extract_demo_log(logfile):
    """Извлекает RESULT из демо-лога."""
    if not os.path.exists(logfile):
        return None
    with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    for line in content.split('\n'):
        if line.startswith('RESULT:'):
            m = re.search(r'A=([\d.]+)', line)
            v = re.search(r'VOL=([\d.]+)', line)
            t = re.search(r'T=(\d+)', line)
            if m and v and t:
                return {'T': int(t.group(1)), 'a': float(m.group(1)), 'vol': float(v.group(1))}
    # Fallback: ищем в расширенной строке
    for line in content.split('\n'):
        if 'RESULT_' in line and 'A=' in line:
            m = re.search(r'A=([\d.]+)', line)
            v = re.search(r'VOL=([\d.]+)', line)
            t = re.search(r'T=(\d+)', line)
            if m and v and t:
                return {'T': int(t.group(1)), 'a': float(m.group(1)), 'vol': float(v.group(1))}
    return None

def main():
    print("\n[demo_report] Reading LAMMPS logs...")
    
    results = []
    for T in [300, 600]:
        logfile = os.path.join(OUTPUT, f"log_demo_{T}.lmp")
        r = extract_demo_log(logfile)
        if r:
            print(f"  T={T}K: a={r['a']:.4f}A, V={r['vol']:.4f}")
            results.append(r)
        else:
            print(f"  T={T}K: NOT FOUND in {logfile}")
    
    if not results:
        print("[demo_report] ERROR: No results extracted. LAMMPS may have failed.")
        return
    
    # Write CSV
    csvfile = os.path.join(OUTPUT, "demo_results.csv")
    with open(csvfile, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['T_K', 'a_Angstrom', 'Volume_Ang3'])
        for r in sorted(results, key=lambda x: x['T']):
            w.writerow([r['T'], f"{r['a']:.4f}", f"{r['vol']:.4f}"])
    print(f"  Saved: {csvfile}")
    
    # Generate plot
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        Ts = sorted([r['T'] for r in results])
        av = [r['a'] for r in sorted(results, key=lambda x: x['T'])]
        
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(Ts, av, marker='o', color='#d62728', label="Pt = 1.00 (demo)",
                linewidth=2, markersize=10)
        ax.set_xlabel('Temperature (K)')
        ax.set_ylabel('Lattice Parameter a (A)')
        ax.set_title('Fe-Pt DEMO: Pure Pt Thermal Expansion\n(raw LAMMPS MD, no manual values)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fp = os.path.join(OUTPUT, "demo_a_vs_T.png")
        fig.savefig(fp, dpi=150)
        plt.close(fig)
        print(f"  Saved: {fp}")
    except ImportError:
        print("  [SKIP] matplotlib not installed — skipping plot. Run: pip install matplotlib")
    except Exception as e:
        print(f"  [SKIP] Plot error: {e}")
    
    print("[demo_report] Done!")

if __name__ == "__main__":
    main()
