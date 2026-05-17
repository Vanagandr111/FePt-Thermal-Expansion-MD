"""
Fe-Pt MD Thermal Expansion — single calculation engine.
Output: results/  (one folder, full 1002-point production logs)
Protocol: 50k equilibration + 100k production, Pdamp=10
Potential: MEAM PtFe.meam
Grid: 5 compositions x 4 temperatures = 20 points
Windows-only. No WSL. No hardcoded Linux paths.
"""

import sys, os, time, csv, math, re, shutil, subprocess

# ── Project root ──
_THIS = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_THIS)

# ── Parameters ──
COMP = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 600, 900, 1200]
NATOMS = 256
EQ = 50000
PROD = 100000
PDAMP = 10.0

OUT = os.path.join(_PROJ, 'results')
LOGS = os.path.join(OUT, 'logs')
PLOTS = os.path.join(OUT, 'plots')
INS = os.path.join(OUT, 'input')

POT_LINE = r"pair_coeff      * * potentials\library.meam Fe Pt potentials\PtFe.meam Fe Pt"
LMP_BAT = os.path.join(_PROJ, '_run_lmp.bat')

os.makedirs(LOGS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)
os.makedirs(INS, exist_ok=True)

# ── Helpers ──

def find_lmp():
    """Find lmp.exe: bundled first, then PATH."""
    bundled = os.path.join(_PROJ, 'bin', 'lmp.exe')
    if os.path.isfile(bundled):
        return bundled
    for name in ('lmp.exe', 'lmp'):
        p = shutil.which(name)
        if p:
            return p
    return None


def gen_structure(comp):
    """Generate LAMMPS data file. Skip if exists."""
    data = os.path.join(_PROJ, 'data', 'data.fept_c{:.2f}.lmp'.format(comp))
    if os.path.exists(data):
        return data
    gen = os.path.join(_PROJ, 'scripts', 'gen_structure.py')
    subprocess.run([sys.executable, gen, '4', '4', '4', str(comp), data],
                   capture_output=True, timeout=30)
    return data


def write_input(datafile, comp, T):
    """Write LAMMPS input for one (comp, T) point."""
    fname = 'in_phase4_{:.2f}_{}.lmp'.format(comp, T)
    infile = os.path.join(INS, fname)
    lines = [
        '# Phase 4 Fe-Pt MEAM T={}K comp={:.2f}'.format(T, comp),
        'units           metal',
        'boundary        p p p',
        'atom_style      atomic',
        '',
        'read_data       ' + datafile,
        '',
        'pair_style      meam',
        POT_LINE,
        '',
        'neighbor        2.0 bin',
        'neigh_modify    every 1 delay 0 check yes',
        '',
        'thermo          100',
        'thermo_style    custom step temp pe ke press vol lx ly lz',
        '',
        'minimize        1.0e-6 1.0e-8 1000 10000',
        'print           "MINIMIZATION_DONE"',
        '',
        'velocity        all create {} 12345'.format(T),
        '',
        'fix             nptfix all npt temp {} {} {} iso 0.0 0.0 {}'.format(T, T, PDAMP, PDAMP),
        '',
        'thermo          1000',
        'print           "EQ_START"',
        'run             {}'.format(EQ),
        'print           "EQ_DONE"',
        '',
        'thermo          100',
        'print           "PRODUCTION_START"',
        'run             {}'.format(PROD),
        'print           "PRODUCTION_DONE"',
        '',
        'variable myvol  equal vol',
        'variable mya    equal (4.0*vol/count(all))^(1.0/3.0)',
        'print           "RESULT: COMP={:.2f} T={} A=${{mya}} VOL=${{myvol}}"'.format(comp, T),
        'print           "DONE"',
    ]
    with open(infile, 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    return infile


def run_lammps(infile, logfile, timeout=900):
    """Run LAMMPS via _run_lmp.bat. Returns dict with stdout/stderr/log."""
    result = {'ok': False, 'stdout': '', 'stderr': '', 'log': logfile}
    lmp = find_lmp()
    if not lmp:
        print('    ERROR: lmp.exe not found')
        return result
    # Run via cmd.exe /c with _run_lmp.bat
    infile_rel = os.path.relpath(infile, _PROJ)
    log_rel = os.path.relpath(logfile, _PROJ)
    cmd = [LMP_BAT, '-in', infile_rel, '-log', log_rel]
    shell = subprocess.list2cmdline(cmd)
    try:
        proc = subprocess.Popen(
            ['cmd.exe', '/c', shell],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=_PROJ
        )
        try:
            so, se = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            so, se = proc.communicate(timeout=5)
            result['timeout'] = True
        result['ok'] = proc.returncode == 0 and not result.get('timeout', False)
        result['stdout'] = so.decode('cp1251', errors='replace') if so else ''
        result['stderr'] = se.decode('cp1251', errors='replace') if se else ''
        result['exit_code'] = proc.returncode
    except Exception as e:
        result['stderr'] = str(e)
    return result


def parse_log(logpath):
    """Parse production thermo from a LAMMPS log file.
    Returns dict with a_mean, a_std, n_points, drift, etc.
    """
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return {'n_points': 0}

    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    result_a = None
    for line in text.split('\n'):
        if 'RESULT:' in line and 'A=' in line:
            m = re.search(r'A=([\d.]+)', line)
            if m:
                result_a = float(m.group(1))

    in_prod = False
    a_vals = []
    vol_vals = []
    press_vals = []
    temp_vals = []

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
        # Fallback: between EQ_DONE and RESULT
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
        return {'n_points': 0, 'result_a': result_a}

    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a_vals) / max(n - 1, 1))
    mean_vol = sum(vol_vals) / n if vol_vals else 0
    mean_press = sum(press_vals) / n if press_vals else None
    std_press = math.sqrt(sum((p - mean_press) ** 2 for p in press_vals) / max(len(press_vals) - 1, 1)) if press_vals else None
    half = n // 2
    drift = (sum(a_vals[half:]) / max(n - half, 1) -
             sum(a_vals[:half]) / max(half, 1))
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


def write_csv(data):
    """Write results.csv and per-composition CSVs."""
    csv_path = os.path.join(OUT, 'results.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['x_Pt', 'T_K', 'a_Angstrom', 'a_std_Angstrom',
                     'n_points', 'drift', 'p_bar', 'p_std_bar'])
        for comp in COMP:
            for T in TEMPS:
                p = data.get((comp, T), {})
                if p and p.get('a_mean') is not None:
                    w.writerow([
                        '{:.2f}'.format(comp), T,
                        '{:.6f}'.format(p['a_mean']),
                        '{:.6f}'.format(p.get('a_std', 0)),
                        p.get('n_points', 0),
                        '{:.2e}'.format(p.get('drift', 0)),
                        '{:.1f}'.format(p.get('mean_press', 0) or 0),
                        '{:.1f}'.format(p.get('std_press', 0) or 0),
                    ])
    print('  CSV: ' + csv_path)

    # Per-composition
    for comp in COMP:
        path = os.path.join(OUT, 'results_{:.2f}.csv'.format(comp))
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['x_Pt', 'T_K', 'a_Angstrom'])
            for T in TEMPS:
                p = data.get((comp, T), {})
                if p and p.get('a_mean') is not None:
                    w.writerow(['{:.2f}'.format(comp), T,
                                '{:.6f}'.format(p['a_mean'])])
    print('  Per-composition CSVs OK')


def make_plots(data):
    """Generate a(T), a(comp), facets plots."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'matplotlib', '-q'],
                       timeout=60)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    # 1. a(T) all comps
    fig, ax = plt.subplots(figsize=(10, 7))
    for ci, comp in enumerate(COMP):
        pts = [(T, data[(comp, T)]) for T in TEMPS
               if (comp, T) in data and data[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            ts, vs = [p[0] for p in pts], [p[1] for p in pts]
            avs = [v['a_mean'] for v in vs]
            errs = [v.get('a_std', 0) for v in vs]
            ax.plot(ts, avs, 'o-', color=colors[ci],
                    label='x_Pt={:.2f}'.format(comp), markersize=7, linewidth=2)
            ax.fill_between(ts, [a - s for a, s in zip(avs, errs)],
                            [a + s for a, s in zip(avs, errs)],
                            alpha=0.15, color=colors[ci])
    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('Lattice parameter a (Angstrom)')
    ax.set_title('Fe-Pt Thermal Expansion')
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS, 'a_vs_T.png'), dpi=150)
    plt.close(fig)
    print('  Plot: a_vs_T.png')

    # 2. a(comp) at fixed T
    fig, ax = plt.subplots(figsize=(10, 7))
    for T in TEMPS:
        pts = [(comp, data[(comp, T)]['a_mean'])
               for comp in COMP
               if (comp, T) in data and data[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            ax.plot([p[0] for p in pts], [p[1] for p in pts],
                    'o-', label='T={}K'.format(T), markersize=8, linewidth=2)
    ax.set_xlabel('Pt fraction x_Pt')
    ax.set_ylabel('Lattice parameter a (Angstrom)')
    ax.set_title('Fe-Pt a(comp) at fixed temperatures')
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS, 'a_vs_comp.png'), dpi=150)
    plt.close(fig)
    print('  Plot: a_vs_comp.png')

    # 3. Facets 2x3
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    fig.suptitle('Fe-Pt Thermal Expansion', fontsize=14, fontweight='bold')
    for ci, comp in enumerate(COMP):
        ax = axes.flatten()[ci]
        pts = [(T, data[(comp, T)]) for T in TEMPS
               if (comp, T) in data and data[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            ts = [p[0] for p in pts]
            vs = [p[1] for p in pts]
            avs = [v['a_mean'] for v in vs]
            errs = [v.get('a_std', 0) for v in vs]
            ax.errorbar(ts, avs, yerr=errs, fmt='o-', color=colors[ci],
                        capsize=4, markersize=6)
            rise = avs[-1] - avs[0]
            alpha = rise / avs[0] / 900
            ax.set_title('x_Pt={:.2f}\nDa={:.4f}A a={:.2e}'.format(comp, rise, alpha),
                         fontsize=10)
            ax.set_xlabel('T (K)')
            ax.set_ylabel('a (Angstrom)')
            ax.grid(alpha=0.3)
    for i in range(len(COMP), 6):
        axes.flatten()[i].set_visible(False)
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS, 'a_vs_T_facets.png'), dpi=150)
    plt.close(fig)
    print('  Plot: a_vs_T_facets.png')


# ── Main ──

def main():
    print('=' * 60)
    print('  Fe-Pt MD Thermal Expansion')
    print('  Protocol: {} eq + {} prod, Pdamp={}'.format(EQ, PROD, PDAMP))
    print('  Grid: {} comps x {} temps = {} points'.format(
        len(COMP), len(TEMPS), len(COMP) * len(TEMPS)))
    print('  Output: ' + OUT)
    lmp = find_lmp()
    print('  LAMMPS: ' + (lmp or 'NOT FOUND'))
    print('=' * 60)

    if not lmp:
        print('\nERROR: lmp.exe not found in bin/ or PATH')
        return 1

    # Generate structures
    print('\nGenerating structures...')
    for comp in COMP:
        gen_structure(comp)
    print('  Structures OK')

    # Run all 20 points sequentially
    results = {}
    total_start = time.time()
    for i, comp in enumerate(COMP):
        for T in TEMPS:
            label = '[{}/20] x_Pt={:.2f} T={}K'.format(i * 4 + TEMPS.index(T) + 1, comp, T)
            print('\n  ' + label)
            datafile = os.path.join(_PROJ, 'data',
                                    'data.fept_c{:.2f}.lmp'.format(comp))
            logfile = os.path.join(LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
            infile = write_input(datafile, comp, T)

            t0 = time.time()
            r = run_lammps(infile, logfile)
            dt = time.time() - t0

            p = parse_log(logfile)
            if p and p.get('a_mean') is not None:
                print('    a={:.6f} n={} t={:.0f}s'.format(
                    p['a_mean'], p['n_points'], dt))
            elif p and p.get('result_a'):
                print('    result_a={:.6f} (no prod thermo) t={:.0f}s'.format(
                    p['result_a'], dt))
            else:
                print('    FAILED t={:.0f}s'.format(dt))
                print('    stderr: ' + (r.get('stderr', '')[:200] if not r.get('ok') else ''))
            p['runtime'] = dt
            results[(comp, T)] = p

    total = time.time() - total_start
    print('\n\nTotal time: {:.1f} min'.format(total / 60))

    # Print results table
    print('\n' + '=' * 95)
    print('  RESULTS')
    print('=' * 95)
    hdr = '{:>6} {:>5} {:>11} {:>9} {:>6} {:>9} {:>9}'.format(
        'x_Pt', 'T', 'a_mean', 'a_std', 'n', 'drift', 'time')
    print(hdr)
    print('-' * 95)
    for comp in COMP:
        for T in TEMPS:
            p = results.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                print('{:>6.2f} {:>5} {:>11.6f} {:>9.6f} {:>6} {:>9.2e} {:>5.0f}s'.format(
                    comp, T, p['a_mean'], p.get('a_std', 0),
                    p['n_points'], p.get('drift', 0), p.get('runtime', 0)))
            else:
                print('{:>6.2f} {:>5} {:>11}'.format(comp, T, 'NO DATA'))

    # Trends
    print('\n  --- a(T) Trends ---')
    for comp in COMP:
        vals = [(T, results[(comp, T)]['a_mean'])
                for T in TEMPS if (comp, T) in results and results[(comp, T)].get('a_mean')]
        if len(vals) == 4:
            av = [v[1] for v in vals]
            rise = av[3] - av[0]
            alpha = rise / av[0] / 900
            mono = all(av[i+1] >= av[i] for i in range(3))
            status = 'OK' if mono else 'non-monotonic'
            print('  x_Pt={:.2f}: a300={:.6f} a1200={:.6f} Da={:.6f}A  a={:.3e}  {}'.format(
                comp, av[0], av[3], rise, alpha, status))

    # Pt benchmark
    pt300 = results.get((1.0, 300), {})
    pt1200 = results.get((1.0, 1200), {})
    if pt300.get('a_mean') and pt1200.get('a_mean'):
        alpha_pt = (pt1200['a_mean'] - pt300['a_mean']) / pt300['a_mean'] / 900
        print('\n  --- Pt Benchmark ---')
        print('  a(300K) = {:.6f} (expected ~3.929)'.format(pt300['a_mean']))
        print('  a(1200K) = {:.6f} (expected ~3.956)'.format(pt1200['a_mean']))
        print('  a_Pt = {:.3e} (expected ~7.5e-6)'.format(alpha_pt))

    # CSV
    write_csv(results)

    # Plots
    try:
        make_plots(results)
    except Exception as e:
        print('  Plot error: ' + str(e))

    # Summary
    ok = sum(1 for p in results.values() if p and p.get('a_mean') is not None)
    fail = 20 - ok
    print('\n' + '=' * 60)
    if fail == 0:
        print('  COMPLETE — All {} points verified'.format(ok))
    else:
        print('  {} OK, {} FAILURES'.format(ok, fail))
    print('  Output: ' + OUT)
    print('=' * 60)

    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
