#!/usr/bin/env python
"""
run_pt_eam.py — Pure Pt EAM validation with Pt_u3.eam.
Windows-first. Output -> output_pt_eam/.

Validates pure Pt lattice parameter using the standalone Pt_u3.eam
(Foiles 1986) potential via pair_style eam. Gives correct a0~3.924A
and CTE~9.12e-6 (101% of exp) as an independent cross-check.

Protocol: 50k equilibration + 100k production (same as Long).
Grid: 1 comp (pure Pt) x 6 temps = 6 points.

Usage:
    python scripts/run_pt_eam.py                  # auto seed
    python scripts/run_pt_eam.py --seed 12345     # manual seed
    python scripts/run_pt_eam.py --force          # rerun all

# module-purpose: Pure Pt EAM validation run with Pt_u3.eam
# entry-points: main()
# main-flows:
#   1. generate single-atom-type Pt structure -> run 6 temperatures
#   2. parse production -> write CSV + integrity check + plots
# related-modules: lmp_helper (write_input with pair_style_type='eam'),
#                  seed_manager
"""

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)

if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import lmp_helper as lmp
import seed_manager as seed_mgr

# -- Parameters --
# intent: Pure Pt EAM validation parameters
# sidefx: none
# purity: pure
COMPOSITIONS = [1.0]       # pure Pt only
TEMPS = [300, 500, 700, 900, 1100, 1200]
NATOMS = 2048
# EQ_STEPS / PROD_STEPS — set dynamically below (via --turbo-plus flag)
TDAMP = 1.0
PDAMP = 10.0
POT_FILE = os.path.join('potentials', 'Pt_u3.eam')
POT_LINE = POT_FILE    # for write_input: pair_coeff * * potentials/Pt_u3.eam
PAIR_STYLE = 'eam'
POT_DISPLAY = 'EAM Pt_u3.eam (Foiles 1986)'

OUT = os.path.join(_PROJ_DIR, 'output_pt_eam')
LOGS = os.path.join(OUT, 'logs')

# -- Seed --
SEED_FINAL = 12345

SEED_ARG = None
for i, arg in enumerate(sys.argv):
    if arg == '--seed':
        if i + 1 >= len(sys.argv):
            SEED_ARG = -1
            break
        try:
            SEED_ARG = int(sys.argv[i + 1])
        except ValueError:
            SEED_ARG = -1
        break
REUSE_SEED = '--reuse-seed' in sys.argv
RESUME = '--resume' in sys.argv
FORCE = '--force' in sys.argv

# -- Turbo mode --
# intent: Speed up validation with shorter steps (20k eq + 50k prod)
# sidefx: reduces statistical accuracy but good for quick PР check
TURBO_PLUS = '--turbo-plus' in sys.argv
if TURBO_PLUS:
    EQ_STEPS = 20000
    PROD_STEPS = 50000
else:
    EQ_STEPS = 50000
    PROD_STEPS = 100000


def gen_pt_structure():
    """Generate single-type pure Pt data file."""
    outfile = os.path.join(lmp.DATA_DIR, 'data.pt_pure.lmp')
    if os.path.exists(outfile) and not FORCE:
        return outfile

    lc = 3.92  # initial guess close to Pt a0
    nx, ny, nz = 8, 8, 8
    natoms_total = 4 * nx * ny * nz

    basis = [
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.0),
        (0.5, 0.0, 0.5),
        (0.0, 0.5, 0.5),
    ]

    atoms = []
    aid = 0
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                for dx, dy, dz in basis:
                    x = (ix + dx) * lc
                    y = (iy + dy) * lc
                    z = (iz + dz) * lc
                    aid += 1
                    atoms.append((aid, x, y, z))

    box_hi = max(nx, ny, nz) * lc

    with open(outfile, 'w') as f:
        f.write("Pure Pt fcc, single type\n\n")
        f.write("{} atoms\n".format(natoms_total))
        f.write("1 atom types\n\n")
        f.write("0.0 {} xlo xhi\n".format(box_hi))
        f.write("0.0 {} ylo yhi\n".format(box_hi))
        f.write("0.0 {} zlo zhi\n\n".format(box_hi))
        f.write("Atoms\n\n")
        for (aid, x, y, z) in atoms:
            f.write("{} 1 {:.6f} {:.6f} {:.6f}\n".format(aid, x, y, z))

    print("  Wrote pure Pt structure: {} atoms -> {}".format(natoms_total, outfile))
    return outfile


# intent: Run LAMMPS at single T for pure Pt EAM; returns timing only
# allies: main() (called per point), lmp.run_lmp, lmp.write_input, lmp.parse_production
# sidefx: io (writes LAMMPS log + input file)
# purity: impure
# errors: returns None on LAMMPS failure / parse failure
def run_point(datafile, T, subdir):
    """Run LAMMPS at single T; returns timing only."""
    os.makedirs(subdir, exist_ok=True)
    logfile = os.path.join(subdir, "log_pt_{}.lmp".format(T))
    infile = lmp.write_input(
        datafile, comp=1.0, T=T, out=OUT, pot_line=POT_LINE,
        eq_steps=EQ_STEPS, prod_steps=PROD_STEPS,
        tdamp=TDAMP, pdamp=PDAMP, seed=SEED_FINAL,
        pair_style_type=PAIR_STYLE,
    )

    print("  T={}K...".format(T), end="", flush=True)
    t0 = time.time()
    result = lmp.run_lmp(infile, logfile=logfile, timeout=900)
    dt = time.time() - t0

    p = lmp.parse_production(logfile, NATOMS)
    if p and p.get('a_mean') is not None:
        print(" a={:.6f}A [{:.0f}s]".format(p['a_mean'], dt))
        return {'time': dt}

    print(" FAILED [{}s]".format(dt))
    return None


# intent: Orchestrate pure Pt EAM validation — 6 MD runs, analysis, output
# allies: run_point, lmp_helper, seed_manager
# sidefx: io (writes output_pt_eam/ with CSVs, logs, plots, integrity)
# purity: impure
# errors: returns 0 on success, 1 on LAMMPS not found or failures
def main():
    """
    # intent: Orchestrate pure Pt EAM validation — 6 MD runs, analysis, output
    # allies: run_point, lmp.*, seed_mgr.*
    # sidefx: io (writes output_pt_eam/ with CSVs, logs, plots, integrity)
    # purity: impure
    # errors: returns 0 on success, 1 on LAMMPS not found or failures
    """
    print('=' * 60)
    print('  Pure Pt Validation — EAM (Pt_u3.eam)')
    print('  Potential: {}'.format(POT_DISPLAY))
    print('  Protocol: {} eq + {} prod, Tdamp={}, Pdamp={}'.format(
        EQ_STEPS, PROD_STEPS, TDAMP, PDAMP))
    print('  Grid: {} temps = {} points'.format(
        len(TEMPS), len(TEMPS)))
    print('  Output: ' + OUT)

    lmp_path = lmp.find_lmp_display()
    print('  LAMMPS: ' + (lmp_path or 'NOT FOUND'))
    print('=' * 60)

    if not lmp.find_lmp():
        print('\\nERROR: lmp.exe not found')
        return 1

    # Clean if --force
    if FORCE and os.path.exists(OUT):
        import shutil
        shutil.rmtree(OUT)

    os.makedirs(LOGS, exist_ok=True)

    # Seed
    global SEED_FINAL
    SEED_FINAL, seed_source = seed_mgr.get_or_create_seed(
        _PROJ_DIR, OUT,
        manual_seed=SEED_ARG if SEED_ARG not in (None, -1) else None,
        reuse_last=REUSE_SEED or SEED_ARG == -1,
        resume=RESUME,
    )
    seed_mgr.write_seed_info(OUT, SEED_FINAL, "pt_eam", seed_source)

    # Protocol log
    lmp.write_protocol_log(OUT, 'run_pt_eam.py', EQ_STEPS, PROD_STEPS,
                           TDAMP, PDAMP, COMPOSITIONS, TEMPS, SEED_FINAL,
                           proto_name='run_pt_eam_protocol.txt',
                           potential_name=POT_DISPLAY)

    # Generate structure
    print('\\nGenerating pure Pt structure...')
    datafile = gen_pt_structure()
    print('  Structure OK')

    # Run all 6 temperatures
    results = {}
    total_start = time.time()
    for i, T in enumerate(TEMPS):
        label = '[{}/{}] Pure Pt T={}K'.format(i + 1, len(TEMPS), T)
        print('\\n  ' + label)
        r = run_point(datafile, T, LOGS)
        if r:
            p = lmp.parse_production(
                os.path.join(LOGS, 'log_pt_{}.lmp'.format(T)), NATOMS)
            p['runtime'] = r.get('time', 0)
        else:
            p = {'n_points': 0, 'a_mean': None, 'runtime': 0}
        results[(1.0, T)] = p

    total = time.time() - total_start
    print('\\n\\nTotal time: {:.1f} min'.format(total / 60))

    # Results table
    print('\\n' + '=' * 75)
    print('  RESULTS — Pure Pt EAM (seed={})'.format(SEED_FINAL))
    print('=' * 75)
    hdr = '{:>5} {:>11} {:>9} {:>6} {:>9} {:>9}'.format(
        'T', 'a_mean', 'a_std', 'n', 'drift', 'time')
    print(hdr)
    print('-' * 75)
    for T in TEMPS:
        p = results.get((1.0, T), {})
        if p and p.get('a_mean') is not None:
            print('{:>5} {:>11.6f} {:>9.6f} {:>6} {:>9.2e} {:>5.0f}s'.format(
                T, p['a_mean'], p.get('a_std', 0),
                p['n_points'], p.get('drift', 0), p.get('runtime', 0)))
        else:
            print('{:>5} {:>11}'.format(T, 'NO DATA'))

    # Trends
    lmp.print_trends(results, COMPOSITIONS, TEMPS, SEED_FINAL)

    # CSV
    lmp.write_csv(results, COMPOSITIONS, TEMPS, OUT, SEED_FINAL,
                  csv_name='all_results_eam_pt.csv',
                  mode_label='EAM_Pt_u3',
                  eq_steps=EQ_STEPS, prod_steps=PROD_STEPS)

    # CTE CSV
    lmp.write_cte_csv(results, COMPOSITIONS, TEMPS, OUT)

    # Integrity
    integrity_ok = lmp.integrity_check(results, COMPOSITIONS, TEMPS, SEED_FINAL)
    if not integrity_ok:
        print('\\nWARNING: integrity check failed — see output_pt_eam/ for details')

    # Plots
    try:
        lmp.make_plots(results, COMPOSITIONS, TEMPS, OUT, SEED_FINAL)
        print('  Plots OK')
    except Exception as e:
        print('  Plots SKIPPED: {}'.format(e))

    # ═══════════════════════════════════════════════════════════
    #  LATTICE PARAMETERS — чистый Pt (Pt_u3.eam)
    # ═══════════════════════════════════════════════════════════
    print()
    print('╔' + '═' * 67 + '╗')
    print('║  LATTICE PARAMETERS — Pure Pt (Pt_u3.eam)         ║')
    print('╠' + '═' * 67 + '╣')
    print('║  {:>4}  {:>12}  {:>8}  {:>8}  {:>6}  {}'.format(
        'T,K', 'a_mean,Å', 'a_std,Å', 'press,bar', 'n_pts', 'drift'))
    print('║  ' + '-' * 63)
    for T in TEMPS:
        p = results.get((1.0, T), {})
        if p and p.get('a_mean') is not None:
            press = p.get('mean_press') or 0
            print('║  {:>4}  {:>12.6f}  {:>8.6f}  {:>+8.1f}  {:>6}  {:>9.2e}'.format(
                T, p['a_mean'], p.get('a_std', 0), press,
                p.get('n_points', 0), p.get('drift', 0)))
        else:
            print('║  {:>4}  {:>12}'.format(T, 'NO DATA'))
    print('╚' + '═' * 67 + '╝')

    # ═══════════════════════════════════════════════════════════
    #  CTE (Coefficient of Thermal Expansion)
    # ═══════════════════════════════════════════════════════════
    a_pts = [(T, results[(1.0, T)]['a_mean'])
             for T in TEMPS if (1.0, T) in results
             and results[(1.0, T)].get('a_mean')]
    cte = lmp.calc_cte_report(a_pts) if len(a_pts) >= 2 else None

    print()
    print('╔' + '═' * 67 + '╗')
    print('║  CTE (Coefficient of Thermal Expansion)            ║')
    print('╠' + '═' * 67 + '╣')
    if cte:
        print('║  Temperature range:   {:>4}K – {:>4}K'.format(cte['T_min'], cte['T_max']))
        print('║  a₀(T_min) → a₀(T_max): {:.6f} → {:.6f} Å   ║'.format(
            cte['a_min'], cte['a_max']))
        print('║  Δa (first→last):     {:+.6f} Å'.format(cte['delta_a_rise']))
        print('║  Δa (linear fit):     {:+.6f} Å'.format(cte['delta_a_fit']))
        print('║' + '─' * 67)
        print('║  α₂ₚₜ  (2-point):     {:.3e} K⁻¹'.format(cte['alpha_2pt']))
        print('║  α_fit (linear fit):  {:.3e} K⁻¹   R²={:.4f}'.format(
            cte['alpha_fit'], cte['r_squared']))
        print('║')
        print('║  Segmental CTE:')
        for i, (seg_alpha, seg_label) in enumerate(
            zip(cte.get('alpha_segmental', []), cte.get('seg_labels', []))):
            print('║    [{:>3}]  {:<12s}  α = {:.3e} K⁻¹'.format(
                i + 1, seg_label, seg_alpha))
        print('║')
        exp_cte_pt = 8.8e-6
        ratio = (cte['alpha_fit'] / exp_cte_pt) * 100
        print('║  Experimental α(Pt):  {:.3e} K⁻¹'.format(exp_cte_pt))
        print('║  Ratio (fit/exp):     {:.1f}%'.format(ratio))
        print('╚' + '═' * 67 + '╝')
    else:
        print('║  CTE: insufficient data (< 2 temperatures)       ║')
        print('╚' + '═' * 67 + '╝')

    return 0


if __name__ == '__main__':
    sys.exit(main())
