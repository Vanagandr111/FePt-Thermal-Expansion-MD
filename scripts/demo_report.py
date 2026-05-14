#!/usr/bin/env python
"""
demo_report.py — парсит логи run_demo.bat и создаёт CSV + графики.
Windows-first. Использует lmp_helper для путей.
"""
import os, csv, sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
import lmp_helper as lmp

OUTPUT = lmp.OUTPUT


def main():
    print("\n[demo_report] Reading LAMMPS logs...")

    results = []
    for T in [300, 600]:
        logfile = os.path.join(OUTPUT, f"log_demo_{T}.lmp")
        r = lmp.extract_result_from_log(logfile)
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
        print("  [SKIP] matplotlib not installed — skipping plot.")
    except Exception as e:
        print(f"  [SKIP] Plot error: {e}")

    print("[demo_report] Done!")


if __name__ == "__main__":
    main()
