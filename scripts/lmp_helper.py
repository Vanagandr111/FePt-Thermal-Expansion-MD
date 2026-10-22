#!/usr/bin/env python
"""
lmp_helper.py — общий модуль для Fe-Pt MD проекта.
Windows-first, no hardcoded /mnt/c/ paths.
Автоопределение корня проекта, поиск lmp.exe, запуск LAMMPS.

All shared functions consolidated here per ai-native-coding-protocol.

# module-purpose: Shared LAMMPS helper for Fe-Pt MD simulation pipeline
# entry-points: run_lmp(), make_plots(), integrity_check(), write_csv()
# main-flows:
#   1. find_lmp -> run_lmp -> extract_result -> parse_production
#   2. write_input -> write_protocol_log -> write_csv -> integrity_check
#   3. print_trends -> calc_cte_report -> make_plots -> write_cte_csv
# related-modules: run_phase4.py, run_main.py, run_phase4_turbo.py,
#                  rebuild_phase4.py, seed_manager.py
# category: lammps-md fe-pt
"""

import csv
import math
import os
import re
import shutil
import subprocess
import sys
import time


# ── Auto-detect project root ──────────────────────────────────
# intent: Determine project root (parent of scripts/)
# allies: PROJDIR, DATA_DIR, POT_DIR (module-level derived vars)
# sidefx: none
# purity: pure
def get_projdir():
    """Корень проекта = родитель scripts/."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(this_dir)  # one level up from scripts/


PROJDIR = os.environ.get('FEPT_PROJECT_DIR') or get_projdir()
DATA_DIR = os.path.join(PROJDIR, 'data')
POT_DIR = os.path.join(PROJDIR, 'potentials')
SCRIPTS = os.path.join(PROJDIR, 'scripts')

# ── OpenMP auto-detection ──────────────────────────────────
CPU_COUNT = os.cpu_count() or 4  # fallback if detection fails


# ── LAMMPS search ────────────────────────────────────────────
# intent: Locate lmp.exe by priority: bin/, LMP_EXE, PATH, defaults
# allies: find_lmp_display (human-readable wrapper)
# sidefx: none (pure file/ENV search)
# purity: pure
# errors: returns None if not found
def find_lmp():
    """
    Search LAMMPS. Order:
      1. PROJDIR/lammps/lmp(.exe) (GUI download folder, kept outside the
         future single-file exe: third-party binary is fetched on demand)
      2. PROJDIR/bin/lmp.exe (portable build)
      3. env var LMP_EXE
      3. lmp.exe / lmp in PATH
      4. Typical Windows install paths
      5. lmp.exe in project root
    Returns command list for subprocess, or None.
    """
    # 1. lmp in lammps/ (GUI download folder; kept outside the future
    #    single-file exe, third-party licensed binary fetched on demand)
    lammps_lmp = os.path.join(PROJDIR, 'lammps',
                              'lmp.exe' if os.name == 'nt' else 'lmp')
    if os.path.isfile(lammps_lmp):
        return [lammps_lmp]

    # 2. lmp.exe in bin/ (portable build)
    bin_lmp = os.path.join(PROJDIR, 'bin', 'lmp.exe')
    if os.path.isfile(bin_lmp):
        return [bin_lmp]

    # 2. Environment variable
    env_lmp = os.environ.get('LMP_EXE')
    if env_lmp:
        if os.path.isfile(env_lmp) or shutil.which(env_lmp):
            return [env_lmp]

    # 3. which / shutil
    for name in ('lmp.exe', 'lmp'):
        path = shutil.which(name)
        if path:
            return [path]

    # 4. Typical Windows paths
    typical_paths = [
        r'C:\Program Files\LAMMPS 64-bit\bin\lmp.exe',
        r'C:\Program Files\LAMMPS 64-bit\lmp.exe',
        r'C:\Program Files\LAMMPS\lmp.exe',
        r'C:\Program Files (x86)\LAMMPS\lmp.exe',
        r'C:\LAMMPS\lmp.exe',
        os.path.join(PROJDIR, 'lmp.exe'),
    ]
    for p in typical_paths:
        if os.path.isfile(p):
            return [p]

    return None


# intent: Human-readable LAMMPS location string
# allies: find_lmp
# sidefx: none
# purity: pure
def find_lmp_display():
    """Human-readable LAMMPS location."""
    cmd = find_lmp()
    if cmd is None:
        return None
    if os.path.isfile(cmd[0]):
        return cmd[0]
    return 'PATH: ' + cmd[0]


# ── Run LAMMPS ────────────────────────────────────────────────
_RUN_LMP_BAT = os.path.join(PROJDIR, '_run_lmp.bat')

# intent: Execute LAMMPS via _run_lmp.bat with timeout and cp1251 decoding
# allies: find_lmp (used by callers), write_input (provides infile)
# sidefx: io (spawns subprocess, creates LAMMPS log)
# purity: impure
# errors: returns error dict with ok=False on all failure modes
def run_lmp(infile, logfile=None, timeout=900, lmp_label='', omp_threads=0,
            kokkos=False, **kwargs):
    """
    Run LAMMPS via _run_lmp.bat (helper with %~dp0).
    Paths relative from PROJDIR.

    Returns dict with keys:
        ok: bool
        stdout, stderr: str
        exit_code: int
        cmd: str
        timeout: bool
        elapsed: float
        label: str
    """
    if not os.path.isfile(_RUN_LMP_BAT):
        return {
            'ok': False, 'stdout': '', 'stderr': 'No _run_lmp.bat',
            'exit_code': -1, 'cmd': 'N/A', 'timeout': False,
        }

    infile_rel = os.path.relpath(infile, PROJDIR)
    bat_args = [_RUN_LMP_BAT, '-in', infile_rel]
    if logfile:
        logfile_rel = os.path.relpath(logfile, PROJDIR)
        bat_args += ['-log', logfile_rel]

    if omp_threads > 0:
        bat_args += ['-sf', 'omp', '-pk', 'omp', str(omp_threads)]
    if kokkos:
        bat_args += ['-sf', 'kokkos', '-pk', 'kokkos']

    shell_cmd = subprocess.list2cmdline(bat_args)

    proc_env = os.environ.copy()
    if omp_threads > 0:
        proc_env['OMP_NUM_THREADS'] = str(omp_threads)
    if 'env' in kwargs:
        proc_env.update(kwargs.pop('env'))
    # use_kokkos from caller → kokkos flag
    if kwargs.pop('use_kokkos', None):
        kokkos = True

    start = time.time()
    timed_out = False
    try:
        proc = subprocess.Popen(
            ['cmd.exe', '/c', shell_cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PROJDIR, env=proc_env, **kwargs
        )
        try:
            stdout_b, stderr_b = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_b, stderr_b = proc.communicate(timeout=5)
            timed_out = True
    except Exception as e:
        return {
            'ok': False, 'stdout': '', 'stderr': 'EXCEPTION: {}'.format(e),
            'exit_code': -1, 'cmd': shell_cmd, 'timeout': False,
        }

    elapsed = time.time() - start
    stdout_text = stdout_b.decode('cp1251', errors='replace') if stdout_b else ''
    stderr_text = stderr_b.decode('cp1251', errors='replace') if stderr_b else ''

    return {
        'ok': proc.returncode == 0 and not timed_out,
        'stdout': stdout_text,
        'stderr': stderr_text,
        'exit_code': proc.returncode,
        'cmd': shell_cmd,
        'timeout': timed_out,
        'elapsed': elapsed,
        'label': lmp_label,
    }


# ── Structure generation ────────────────────────────────────
# intent: Generate FCT lattice structure via gen_structure.py subprocess
# allies: gen_structure.py (external script)
# sidefx: io (writes data.fept_*.lmp)
# purity: impure
# errors: returns existing path if file already exists
# Module-global seed-lattice override: run_main_mace.main() sets it from
# --lc so every generation path (single-worker, parent pre-generation)
# shares one explicit value instead of a hardcoded one.
SEED_LC = None


def gen_structure(comp, nx=8, ny=8, nz=8, force=False, lc=None):
    """Generate structure via gen_structure.py. force=True = regenerate even if exists.
    lc = explicit seed lattice constant (Angstrom); None = SEED_LC, else LC_TABLE by system."""
    if lc is None:
        lc = SEED_LC
    gen_script = os.path.join(SCRIPTS, 'gen_structure.py')
    outfile = os.path.join(DATA_DIR, 'data.fept_c{:.2f}.lmp'.format(comp))
    if os.path.exists(outfile):
        if not force:
            return outfile
        os.remove(outfile)
    os.makedirs(DATA_DIR, exist_ok=True)
    cmd = [sys.executable, gen_script, str(nx), str(ny), str(nz), str(comp), outfile]
    if lc is not None:
        cmd.append(str(lc))
    proc = subprocess.run(
        cmd, capture_output=True, timeout=30
    )
    if proc.returncode != 0 or not os.path.exists(outfile):
        raise RuntimeError('gen_structure failed (rc={}): {}'.format(
            proc.returncode,
            proc.stderr.decode(errors='replace')[-400:]))
    # surface the generator's own log (seed lc + source note) into run logs
    if proc.stdout:
        sys.stdout.write(proc.stdout.decode(errors='replace'))
    return outfile


# ── Parse production phase from LAMMPS log ──────────────────
# intent: Extract mean a, std, drift, pressure from production block
# allies: write_csv, integrity_check, print_trends, make_plots (consumers)
# sidefx: io (reads .lmp log file)
# purity: impure
# errors: returns {"n_points": 0} on missing/incomplete file
def parse_production(logpath, natoms=2048):
    """Parse production phase for mean a(std)."""
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return {'n_points': 0}

    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Main: parse PRODUCTION_START to PRODUCTION_DONE
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
                    temp = float(parts[1])
                    press = float(parts[4])
                    vol = float(parts[5])
                    a = (vol * 4 / natoms) ** (1 / 3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                    press_vals.append(press)
                    temp_vals.append(temp)
                except Exception:
                    pass

    if not a_vals:
        # Fallback: parse after EQ_DONE until RESULT
        in_prod = False
        for line in text.split('\n'):
            s = line.strip()
            if 'EQ_DONE' in s:
                in_prod = True
                continue
            if in_prod and s and s[0].isdigit():
                parts = s.split()
                if len(parts) >= 9:
                    try:
                        vol = float(parts[5])
                        a = (vol * 4 / natoms) ** (1 / 3)
                        a_vals.append(a)
                    except Exception:
                        pass

    if not a_vals:
        # Fallback 2: single-run mode — RUN_START to RUN_DONE
        for line in text.split('\n'):
            s = line.strip()
            if 'RUN_START' in s:
                in_prod = True
                continue
            if 'RUN_DONE' in s:
                in_prod = False
                break
            if in_prod and s and s[0].isdigit():
                parts = s.split()
                if len(parts) >= 9:
                    try:
                        vol = float(parts[5])
                        a = (vol * 4 / natoms) ** (1 / 3)
                        a_vals.append(a)
                    except Exception:
                        pass

    if not a_vals:
        return {'n_points': 0}

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
        'mean_vol': mean_vol,
        'mean_press': mean_press,
        'std_press': std_press,
        'mean_temp': mean_temp,
    }


# ── Write LAMMPS input file ─────────────────────────────────
# intent: Generate parameterized LAMMPS input script for any mode
# allies: run_lmp (executes the generated file)
# sidefx: io (writes in/*.lmp input file)
# purity: impure
def write_input(datafile, comp, T, out, pot_line, eq_steps, prod_steps,
                tdamp=1.0, pdamp=10.0, seed=12345, neighbor_radius=None,
                omp_threads=0, pair_style_type='meam', use_kokkos=False,
                single_run=False, neigh_modify_every=1):
    """Generate a LAMMPS input file. Parameterized for all modes.

    When single_run=True: eq+prod combined into one continuous run
    (workaround for MEAM crash on pure Fe between two `run` commands with MinGW LAMMPS).

    neigh_modify_every: neighbour rebuild frequency (default 1, experimental = 5)
    """
    os.makedirs(os.path.join(out, 'in'), exist_ok=True)
    fname = 'in_phase4_{:.2f}_{}.lmp'.format(comp, T)
    infile = os.path.join(out, 'in', fname)

    data_rel = os.path.relpath(datafile, PROJDIR)
    neighbor_line = 'neighbor        {} bin'.format(neighbor_radius) if neighbor_radius else 'neighbor        2.0 bin'

    # package omp / kokkos handled by CLI flags (run_lmp passes -sf/-pk)
    # Do NOT add to input file to avoid "Package command after sim box" error
    # See: wsl-windows-utf8 troubleshooting section
    # omp_line = 'package omp {}'.format(omp_threads) if omp_threads > 0 else None
    kokkos_line = 'package kokkos' if use_kokkos else None

    lines = [
        '# Phase 4 Fe-Pt MEAM T={}K comp={:.2f} seed={}'.format(T, comp, seed),
        'units           metal',
        'boundary        p p p',
        'atom_style      atomic',
        '',
        'read_data       {}'.format(data_rel),
    ]
    if kokkos_line:
        lines += ['', kokkos_line]
    if pair_style_type == 'eam':
        # Single-element EAM (e.g. Pt_u3.eam for pure Pt)
        ps_name = 'eam'
        pc_line = pot_line  # pot_line should be just the file path
        ps_lines = [
            '',
            'pair_style      eam',
            'pair_coeff      * * {}'.format(pc_line),
        ]
    elif pair_style_type == 'eam_alloy':
        # Multi-element EAM alloy (Zhou04)
        ps_lines = [
            '',
            'pair_style      eam/alloy',
            'pair_coeff      * * {} Fe Pt'.format(pot_line),
        ]
    else:
        # MEAM: multi-element (default)
        ps_lines = [
            '',
            'pair_style      meam',
            pot_line,
        ]
    lines += ps_lines + [
        '',
        neighbor_line,
        'neigh_modify    every {} delay 0 check yes'.format(neigh_modify_every),
        '',
        'thermo          100',
        'thermo_style    custom step temp pe ke press vol lx ly lz',
        '',
        'minimize        1.0e-6 1.0e-8 1000 10000',
        'print           "MINIMIZATION_DONE"',
        '',
        'velocity        all create {} {}'.format(T, seed),
        '',
        'fix             nptfix all npt temp {} {} {} iso 0.0 0.0 {}'.format(T, T, tdamp, pdamp),
        '',
    ]

    if single_run:
        total_steps = eq_steps + prod_steps
        lines += [
            'thermo          500',
            'print           "RUN_START"',
            'run             {}'.format(total_steps),
            'print           "RUN_DONE"',
            'print           "DONE"',
        ]
    else:
        lines += [
            'thermo          1000',
            'print           "EQ_START"',
            'run             {}'.format(eq_steps),
            'print           "EQ_DONE"',
            '',
            'thermo          500',
            'print           "PRODUCTION_START"',
            'run             {}'.format(prod_steps),
            'print           "PRODUCTION_DONE"',
            'print           "DONE"',
        ]
    with open(infile, 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    return infile


# ── Write main results CSV ──────────────────────────────────
# intent: Write all_results.csv + per-composition a_T CSV files
# allies: parse_production (provides data), write_cte_csv (complement)
# sidefx: io (writes CSV files)
# purity: impure
# errors: creates empty CSV on no data
def write_csv(parsed_all, comps, temps, out, seed,
              csv_name='all_results.csv', mode_label=None,
              eq_steps=None, prod_steps=None):
    """Write results CSV for a phase4-style grid calculation."""
    os.makedirs(out, exist_ok=True)
    csv_path = os.path.join(out, csv_name)

    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f, delimiter=';')

        # Build header
        header = ['x_Pt', 'T_K', 'a_mean_Angstrom', 'a_std_Angstrom', 'drift', 'n_points',
                  'mean_press_bar', 'std_press_bar', 'runtime_s']
        if mode_label:
            header += ['mode']
        if eq_steps is not None:
            header += ['eq_steps']
        if prod_steps is not None:
            header += ['prod_steps']
        header += ['seed']
        w.writerow(header)

        for comp in comps:
            for T in temps:
                p = parsed_all.get((comp, T), {})
                if p and p.get('a_mean') is not None:
                    row = [
                        '{:.6f}'.format(comp), T,
                        '{:.6f}'.format(p['a_mean']),
                        '{:.6f}'.format(p.get('a_std', 0)),
                        '{:.6e}'.format(p.get('drift', 0)),
                        p.get('n_points', 0),
                        '{:.1f}'.format(p.get('mean_press', 0) or 0),
                        '{:.1f}'.format(p.get('std_press', 0) or 0),
                        p.get('runtime', 0),
                    ]
                    if mode_label:
                        row += [mode_label]
                    if eq_steps is not None:
                        row += [eq_steps]
                    if prod_steps is not None:
                        row += [prod_steps]
                    row += [seed]
                    w.writerow(row)

    print('  CSV: {}'.format(csv_path))

    # Also write .xlsx with explicit cell types (Excel won't auto-date)
    try:
        import openpyxl
    except ImportError:
        # Auto-install for the user (handles Windows venv)
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'openpyxl', '-q'],
                       timeout=60, capture_output=True)
        import openpyxl

    _write_xlsx(parsed_all, comps, temps, out, seed, csv_name,
                mode_label, eq_steps, prod_steps)

    # Per-composition CSVs
    for comp in comps:
        comp_csv = os.path.join(out, 'a_T_comp_{:.2f}.csv'.format(comp))
        suffix = '_turbo' if mode_label else ''
        comp_csv = os.path.join(out, 'a_T_comp_{:.2f}{}.csv'.format(comp, suffix))
        with open(comp_csv, 'w', newline='') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(['x_Pt', 'T_K', 'a_mean_Angstrom'])
            for T in temps:
                p = parsed_all.get((comp, T), {})
                if p and p.get('a_mean') is not None:
                    w.writerow(['{:.2f}'.format(comp), T, '{:.6f}'.format(p['a_mean'])])
    print('  Per-composition CSVs OK')

    return csv_path


# ── Write XLSX with explicit cell types ──────────────────────
# intent: Write .xlsx alongside CSV so Excel doesn't guess dates
# allies: write_csv (sole caller)
# sidefx: io (writes .xlsx file)
# purity: impure
# errors: if openpyxl not installed → prints warning and returns silently (CSV already written)
def _write_xlsx(parsed_all, comps, temps, out, seed,
                csv_name='all_results.csv', mode_label=None,
                eq_steps=None, prod_steps=None):
    """Write .xlsx with explicit number formats per column."""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment
    except ImportError:
        print('  XLSX: skipped (openpyxl not available)')
        return  # non-fatal — CSV already written

    xlsx_name = csv_name.replace('.csv', '.xlsx')
    xlsx_path = os.path.join(out, xlsx_name)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"

    # Build header
    header = ['x_Pt', 'T_K', 'a_mean_Angstrom', 'a_std_Angstrom', 'drift', 'n_points',
              'mean_press_bar', 'std_press_bar', 'runtime_s']
    if mode_label:
        header += ['mode']
    if eq_steps is not None:
        header += ['eq_steps']
    if prod_steps is not None:
        header += ['prod_steps']
    header += ['seed']

    # Number formats per column index (0-based)
    num_fmts = {
        0: '0.00',       # x_Pt
        1: '0',          # T_K
        2: '0.000000',   # a_mean
        3: '0.000000',   # a_std
        4: '0.00E+00',   # drift
        5: '0',          # n_points
        6: '0.0',        # mean_press
        7: '0.0',        # std_press
        8: '0.00',       # runtime
    }
    # mode = text, eq_steps/prod_steps = '0', seed = '0'

    # Write header
    for ci, h in enumerate(header):
        cell = ws.cell(row=1, column=ci + 1, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    # Write data
    row_idx = 2
    for comp in comps:
        for T in temps:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                vals = [
                    round(comp, 2), T,
                    round(p['a_mean'], 6),
                    round(p.get('a_std', 0), 6),
                    p.get('drift', 0),
                    p.get('n_points', 0),
                    round(p.get('mean_press', 0) or 0, 1),
                    round(p.get('std_press', 0) or 0, 1),
                    round(p.get('runtime', 0), 2),
                ]
                if mode_label:
                    vals += [mode_label]
                if eq_steps is not None:
                    vals += [eq_steps]
                if prod_steps is not None:
                    vals += [prod_steps]
                vals += [seed]

                for ci, val in enumerate(vals):
                    cell = ws.cell(row=row_idx, column=ci + 1, value=val)
                    # Apply number format for numeric columns
                    if ci in num_fmts and isinstance(val, (int, float)):
                        cell.number_format = num_fmts[ci]
                    # Align numbers right, text left
                    if isinstance(val, (int, float)):
                        cell.alignment = Alignment(horizontal='right')
                    else:
                        cell.alignment = Alignment(horizontal='left')
                row_idx += 1

    # Auto-fit column widths
    for ci in range(len(header)):
        max_len = len(str(header[ci]))
        for row in ws.iter_rows(min_col=ci + 1, max_col=ci + 1,
                                min_row=2, max_row=row_idx - 1):
            for cell in row:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
        col_letter = openpyxl.utils.get_column_letter(ci + 1)
        ws.column_dimensions[col_letter].width = max_len + 3

    wb.save(xlsx_path)
    print('  XLSX: {}'.format(xlsx_path))


# ── Write CTE report CSV ────────────────────────────────────
# intent: Write cte_report.csv with multiple CTE metrics per composition
# allies: calc_cte_report (computation), write_csv (complement)
# sidefx: io (writes CSV file)
# purity: impure
def write_cte_csv(parsed_all, comps, temps, out):
    """Write CTE report CSV per composition."""
    cte_csv_path = os.path.join(out, 'cte_report.csv')
    with open(cte_csv_path, 'w', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['x_Pt', 'R_squared', 'alpha_2pt', 'alpha_fit',
                     'alpha_min', 'alpha_max', 'alpha_range',
                     'seg_300_600', 'seg_600_900', 'seg_900_1200',
                     'delta_a_rise', 'delta_a_fit'])
        for comp in comps:
            a_vals = [(T, parsed_all[(comp, T)]['a_mean'])
                      for T in temps
                      if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
            _cte = calc_cte_report(a_vals) if len(a_vals) == 4 else None
            if _cte:
                seg = _cte['alpha_segmental']
                w.writerow(['{:.2f}'.format(comp),
                            '{:.4f}'.format(_cte['r_squared']),
                            '{:.3e}'.format(_cte['alpha_2pt']),
                            '{:.3e}'.format(_cte['alpha_fit']),
                            '{:.3e}'.format(_cte['alpha_min']),
                            '{:.3e}'.format(_cte['alpha_max']),
                            '{:.3e}'.format(_cte['alpha_range']),
                            '{:.3e}'.format(seg[0]) if len(seg) > 0 else '',
                            '{:.3e}'.format(seg[1]) if len(seg) > 1 else '',
                            '{:.3e}'.format(seg[2]) if len(seg) > 2 else '',
                            '{:.6f}'.format(_cte['delta_a_rise']),
                            '{:.6f}'.format(_cte['delta_a_fit'])])
    print('  CTE CSV: {}'.format(cte_csv_path))


# ── Write protocol log ─────────────────────────────────────
# intent: Write human-readable protocol log to output directory
# allies: find_lmp (used by callers), write_input (referenced in log)
# sidefx: io (writes .txt protocol file)
# purity: impure
def write_protocol_log(out, script_name, eq_steps, prod_steps, tdamp, pdamp,
                       comps, temps, seed, proto_name='run_protocol.txt',
                       mode_label=None, mode_extra=None,
                       potential_name='MEAM PtFe.meam'):
    """Write protocol log to output dir."""
    proto_path = os.path.join(out, proto_name)
    lines = [
        'Fe-Pt Phase 4 -- Protocol Log',
        '=' * 50,
        'Timestamp: {}'.format(time.strftime('%Y-%m-%d %H:%M:%S')),
        'Script: {}'.format(script_name),
        'Pipeline: Phase 4',
        'Potential: {}'.format(potential_name),
    ]
    if mode_label:
        lines.append('Mode: {}'.format(mode_label))
    lines += [
        'Equilibration steps: {}'.format(eq_steps),
        'Production steps: {}'.format(prod_steps),
        'Tdamp: {}, Pdamp: {}'.format(tdamp, pdamp),
    ]
    if mode_extra:
        for k, v in mode_extra.items():
            lines.append('{}: {}'.format(k, v))
    lines += [
        'Compositions: {}'.format(comps),
        'Temperatures: {}'.format(temps),
        'Output dir: {}'.format(os.path.basename(out) if not os.path.isabs(out) else out),
        'Seed: {}'.format(seed),
        '=' * 50,
    ]
    with open(proto_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('  Protocol log: {}'.format(proto_path))


# ── Print trends ────────────────────────────────────────────
# intent: Print a(T) trends per composition with CTE and segmental analysis
# allies: calc_cte_report (computation), print_trends, make_plots (callers)
# sidefx: io (stdout)
# purity: impure
def print_trends(parsed_all, comps, temps, seed=None):
    """Print a(T) trends per composition.

    Completion is judged against the PLANNED temperature list, never a
    hardcoded 4: a 2-point run that delivered both points is a SUCCESS
    (it used to print "INCOMPLETE (2/4)" - and a 1-point plan printed
    "INCOMPLETE (1/4)" even when everything the user asked for was
    computed, which reads like a failure).
    """
    seed_str = ' (seed={})'.format(seed) if seed else ''
    n_plan = len(temps)
    print('\n' + '=' * 60)
    print('TRENDS: a(T) per composition{}'.format(seed_str))
    print('=' * 60)
    for comp in comps:
        a_vals = []
        for T in temps:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                a_vals.append((T, p['a_mean']))
        if len(a_vals) == n_plan and n_plan >= 2:
            vals = [v[1] for v in a_vals]
            t_lo, t_hi = a_vals[0][0], a_vals[-1][0]
            rise = vals[-1] - vals[0]
            mono = all(vals[i + 1] >= vals[i] for i in range(len(vals) - 1))
            alpha_eff = rise / vals[0] / (t_hi - t_lo) if t_hi > t_lo else 0.0
            _cte = calc_cte_report(a_vals)
            if _cte:
                seg_map = _cte.get('facet_seg') or dict(
                    zip(_cte['seg_labels'], _cte['alpha_segmental']))
                seg_str = '[' + ','.join(
                    '{:.1e}'.format(v) for v in seg_map.values()) + ']'
                print('  x_Pt={:.2f}: a{:.0f}={:.6f} a{:.0f}={:.6f} '
                      'Da={:.6f}A a2pt={:.3e} a_fit={:.3e} R2={:.4f}'.format(
                          comp, t_lo, vals[0], t_hi, vals[-1], rise,
                          alpha_eff, _cte['alpha_fit'], _cte['r_squared']))
                print('           seg: {} range={:.1e} (min={:.3e} '
                      'max={:.3e}) {}'.format(
                          seg_str, _cte['alpha_range'], _cte['alpha_min'],
                          _cte['alpha_max'],
                          '\u2713' if mono else '\u2717'))
            else:
                print('  x_Pt={:.2f}: a{:.0f}={:.6f} a{:.0f}={:.6f} '
                      'Da={:.6f}A a_eff={:.3e} {}'.format(
                          comp, t_lo, vals[0], t_hi, vals[-1], rise,
                          alpha_eff, '\u2713' if mono else '\u2717'))
        elif len(a_vals) == n_plan and a_vals:
            print('  x_Pt={:.2f}: a{:.0f}={:.6f} (single planned point, '
                  'no CTE)'.format(comp, a_vals[0][0], a_vals[0][1]))
        else:
            missing = [T for T in temps
                       if not (parsed_all.get((comp, T), {})
                               .get('a_mean') is not None)]
            print('  x_Pt={:.2f}: INCOMPLETE ({}/{}) missing T={}'.format(
                comp, len(a_vals), n_plan, missing))



# ── Integrity check ─────────────────────────────────────────
# intent: Write comprehensive integrity check report with Pt benchmark and CTE
# allies: calc_cte_report, write_cte_csv, write_csv
# sidefx: io (writes .txt integrity file, writes CTE CSV)
# purity: impure
# errors: returns (ok_count, fail_count) — always tuples
def integrity_check(parsed_all, comps, temps, out, seed, eq_steps, prod_steps,
                    tdamp, pdamp, label='', parallel_workers=None):
    """Write integrity check report. Returns (ok_count, fail_count)."""
    label_text = ' ({})'.format(label) if label else ''
    integrity_path = os.path.join(out, 'integrity_check_v4{}.txt'.format(
        '_turbo' if label else ''))
    lines = [
        'Fe-Pt Phase 4 -- Integrity Check{}'.format(label_text),
        'Seed: {}'.format(seed),
        'Protocol: {} eq + {} prod, Tdamp={}, Pdamp={}'.format(eq_steps, prod_steps, tdamp, pdamp),
        'MEAM potential: PtFe.meam (Fe-Pt cross interaction)',
        'Grid: {} comps x {} temps = {} points'.format(
            len(comps), len(temps), len(comps) * len(temps)),
    ]
    if parallel_workers:
        lines.append('Parallel workers: {}'.format(parallel_workers))
    lines.append('=' * 60)

    ok_count = 0
    fail_count = 0
    for comp in comps:
        for T in temps:
            p = parsed_all.get((comp, T), {})
            if p and p.get('a_mean') is not None:
                ok_count += 1
                lines.append('  \u2713 x_Pt={:.2f} T={}: a={:.6f} n={} drift={:.2e}'.format(
                    comp, T, p['a_mean'], p.get('n_points', 0), p.get('drift', 0)))
            else:
                fail_count += 1
                lines.append('  \u2717 x_Pt={:.2f} T={}: NO DATA'.format(comp, T))

    lines.append('=' * 60)
    lines.append('\u2713 {} verified / Failures: {} / Total: {}'.format(
        ok_count, fail_count, ok_count + fail_count))

    # Pt benchmark
    pt_300 = parsed_all.get((1.0, 300), {})
    pt_1200 = parsed_all.get((1.0, 1200), {})
    if pt_300 and pt_1200 and pt_300.get('a_mean') and pt_1200.get('a_mean'):
        a300 = pt_300['a_mean']
        a1200 = pt_1200['a_mean']
        alpha = (a1200 - a300) / a300 / 900
        lines.append('')
        lines.append('Pt benchmark (seed={}):'.format(seed))
        lines.append('  a(300K) = {:.6f} A  (expected ~3.929)'.format(a300))
        lines.append('  a(1200K) = {:.6f} A  (expected ~3.956)'.format(a1200))
        lines.append('  a_eff = {:.3e}  (expected ~7.5e-6)'.format(alpha))
        delta_a300 = abs(a300 - 3.929)
        lines.append('  Da300 = {:.6f} A from expected'.format(delta_a300))

    # Append CTE data to lines buffer
    if pt_300.get('a_mean') and pt_1200.get('a_mean'):
        lines.append('')
        lines.append('Pt benchmark (seed={}):'.format(seed))
        lines.append('  a(300K) = {:.6f} A  (expected ~3.929)'.format(a300))
        lines.append('  a(1200K) = {:.6f} A  (expected ~3.956)'.format(a1200))
        lines.append('  a_eff = {:.3e}  (expected ~7.5e-6)'.format(alpha))
        lines.append('  Da300 = {:.6f} A from expected'.format(delta_a300))

    for comp in comps:
        a_vals = [(T, parsed_all[(comp, T)]['a_mean'])
                  for T in temps
                  if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
        _cte = calc_cte_report(a_vals) if len(a_vals) == 4 else None
        if _cte:
            lines.append('')
            lines.append('CTE: x_Pt={:.2f}'.format(comp))
            lines.append('  a2pt={:.3e} a_fit={:.3e} R2={:.4f}'.format(
                _cte['alpha_2pt'], _cte['alpha_fit'], _cte['r_squared']))
            seg_str = ' | '.join('{}: {:.3e}'.format(lbl, a)
                                  for lbl, a in zip(_cte['seg_labels'], _cte['alpha_segmental']))
            lines.append('  seg: ' + seg_str)
            lines.append('  range: {:.3e} (min={:.3e}, max={:.3e})'.format(
                _cte['alpha_range'], _cte['alpha_min'], _cte['alpha_max']))

    # One write only
    with open(integrity_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    # Print Pt benchmark
    if pt_300.get('a_mean') and pt_1200.get('a_mean'):
        print('\n  --- Pt Benchmark (seed={}) ---'.format(seed))
        print('  a(300K) = {:.6f} A (expected 3.923-3.924)'.format(a300))
        print('  a(1200K) = {:.6f} A'.format(a1200))
        # CTE comparison for Pt
        pt_a_vals = [(T, parsed_all[(1.0, T)]['a_mean'])
                     for T in temps
                     if (1.0, T) in parsed_all and parsed_all[(1.0, T)].get('a_mean')]
        pt_cte = calc_cte_report(pt_a_vals) if len(pt_a_vals) >= 2 else None
        if pt_cte:
            PT_CTE_REF = 9.0e-6
            dev_2pt = pt_cte['alpha_2pt'] - PT_CTE_REF
            dev_fit = pt_cte['alpha_fit'] - PT_CTE_REF
            print('  CTE(Pt) alpha_2pt={:.3e}  alpha_fit={:.3e}  (ref={:.1e})'.format(
                pt_cte['alpha_2pt'], pt_cte['alpha_fit'], PT_CTE_REF))
            print('  Deviation: d_2pt={:+.3e}  d_fit={:+.3e}'.format(dev_2pt, dev_fit))

    # Print CTE report
    print('\n  --- CTE Report (all methods) ---')
    print('  {:>6} {:>6} {:>10} {:>10} {:>10} {:>10} {:>10}'.format(
        'x_Pt', 'R2', 'a2pt', 'a_fit', 'a_min', 'a_max', 'range'))
    print('  ' + '-' * 72)
    for comp in comps:
        a_vals = [(T, parsed_all[(comp, T)]['a_mean'])
                  for T in temps
                  if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
        _cte = calc_cte_report(a_vals) if len(a_vals) == 4 else None
        if _cte:
            print('  {:>6.2f} {:>6.4f} {:>10.3e} {:>10.3e} {:>10.3e} {:>10.3e} {:>10.3e}'.format(
                comp, _cte['r_squared'], _cte['alpha_2pt'], _cte['alpha_fit'],
                _cte['alpha_min'], _cte['alpha_max'], _cte['alpha_range']))

    # Also save CTE CSV
    write_cte_csv(parsed_all, comps, temps, out)

    print('  Integrity: {}'.format(integrity_path))
    return ok_count, fail_count


# ── CTE calculation utilities ──────────────────────────────
# intent: Simple linear regression — returns (slope, intercept, r_squared)
# allies: calc_cte_report (sole caller)
# sidefx: none
# purity: pure
# errors: returns (0,0,0) for n < 2 or singular
def _linear_fit(xs, ys):
    """Simple linear regression. Returns (slope, intercept, r_squared)."""
    n = len(xs)
    if n < 2:
        return 0, 0, 0
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0, 0, 0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - sy / n) ** 2 for y in ys)
    r_sq = 1 - ss_res / ss_tot if ss_tot != 0 else 0
    return slope, intercept, r_sq


# intent: Calculate comprehensive CTE report — 2pt, linear fit, segmental, range
# allies: _linear_fit, write_cte_csv, integrity_check, print_trends, make_plots
# sidefx: none
# purity: pure
# errors: returns None for < 2 data points
def calc_cte_report(a_vals):
    """
    Calculate comprehensive CTE report for one composition.

    Parameters
    ----------
    a_vals : list of (T, a_mean)
        Sorted by T, e.g. [(300, 3.929), (600, 3.937), ...]

    Returns dict or None (if < 2 points).
    """
    if not a_vals or len(a_vals) < 2:
        return None

    pts = sorted(a_vals, key=lambda x: x[0])
    ts = [p[0] for p in pts]
    avs = [p[1] for p in pts]

    # 1. a_2pt
    rise = avs[-1] - avs[0]
    temp_range = ts[-1] - ts[0]
    alpha_2pt = rise / avs[0] / temp_range if temp_range > 0 else 0

    # 2. a_fit — linear regression through ALL points
    slope, intercept, r_sq = _linear_fit(ts, avs)
    alpha_fit = slope / avs[0]
    delta_a_fit = slope * temp_range

    # 3. Segmental CTE
    alphas_seg = []
    seg_labels = []
    for i in range(len(pts) - 1):
        dT = ts[i + 1] - ts[i]
        if dT > 0:
            a_seg = (avs[i + 1] - avs[i]) / avs[i] / dT
            alphas_seg.append(a_seg)
            seg_labels.append('{}-{}K'.format(ts[i], ts[i + 1]))

    # 4. Facet-interval CTE between the canonical grid nodes
    # (300/600/900/1200 K). The adjacent-pair labels above never match
    # '300-600K' lookups on dense grids (7-point sweeps give
    # '300-450K', ...), which is why the CSV segment columns came out
    # empty - fit every grid interval that the sweep spans.
    nodes = (300, 600, 900, 1200)
    facet_seg = {}
    for lo, hi in zip(nodes, nodes[1:]):
        if ts[0] > lo or ts[-1] < hi:
            continue
        inner = [(t, a) for t, a in zip(ts, avs) if lo <= t <= hi]
        if len(inner) < 2:
            continue
        tt = [x[0] for x in inner]
        aa = [x[1] for x in inner]
        sl, _ic, _r2f = _linear_fit(tt, aa)
        facet_seg['{}-{}K'.format(lo, hi)] = sl / aa[0]

    # 5. Uncertainty range
    all_alphas = [alpha_2pt, alpha_fit] + alphas_seg + \
        list(facet_seg.values())
    alpha_min = min(all_alphas)
    alpha_max = max(all_alphas)

    return {
        'n_points': len(pts),
        'T_min': ts[0],
        'T_max': ts[-1],
        'a_min': avs[0],
        'a_max': avs[-1],
        'delta_a_rise': rise,
        'delta_a_fit': delta_a_fit,
        'alpha_2pt': alpha_2pt,
        'alpha_fit': alpha_fit,
        'r_squared': r_sq,
        'alpha_segmental': alphas_seg,
        'seg_labels': seg_labels,
        # grid-node interval CTEs (300-600K / 600-900K / 900-1200K)
        'facet_seg': facet_seg,
        'alpha_min': alpha_min,
        'alpha_max': alpha_max,
        'alpha_range': alpha_max - alpha_min,
    }


# ── Shared plotting ──────────────────────────────────────────
# intent: Generate standard 3-panel Fe-Pt plots (a(T), a(comp), facets 2x3)
# allies: calc_cte_report (annotations), matplotlib
# sidefx: io (writes PNG files)
# purity: impure
# edges: auto-installs matplotlib if missing (via pip subprocess)
def make_plots(parsed_all, comps, temps, seed, out,
               colors=None,
               a_vs_T_fn='a_vs_T.png',
               a_vs_comp_fn='a_vs_comp.png',
               a_vs_T_facets_fn='a_vs_T_facets.png',
               title_prefix='Fe-Pt'):
    """
    Generate standard 3-panel plots for Fe-Pt MD data.
    Shared by run_main.py, run_phase4.py, run_phase4_turbo.py.

    Parameters
    ----------
    parsed_all : dict (comp, T) -> {a_mean, a_std, ...}
    comps, temps : lists
    seed : int
    out : str — output directory for PNGs
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        import subprocess
        import sys as _sys
        subprocess.run([_sys.executable, '-m', 'pip', 'install', 'matplotlib', '-q'], timeout=60)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 15,
        'axes.titlesize': 16,
        'legend.fontsize': 13,
        'xtick.labelsize': 13,
        'ytick.labelsize': 13,
    })

    if colors is None:
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    # 1. a(T) all comps
    fig, ax = plt.subplots(figsize=(12, 8))
    for ci, comp in enumerate(comps):
        pts = [(T, parsed_all[(comp, T)]) for T in temps
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean') is not None]
        if pts:
            pts.sort()
            ts, vs = [p[0] for p in pts], [p[1] for p in pts]
            avs = [v['a_mean'] for v in vs]
            errs = [v.get('a_std', 0) for v in vs]
            ax.plot(ts, avs, 'o-', color=colors[ci],
                    label='x_Pt={:.2f}'.format(comp), markersize=8, linewidth=2.5)
            ax.fill_between(ts, [a - s for a, s in zip(avs, errs)],
                            [a + s for a, s in zip(avs, errs)],
                            alpha=0.15, color=colors[ci])
            ax.annotate("{:.4f}".format(avs[0]),
                        xy=(ts[0], avs[0]), xytext=(ts[0]-40, avs[0]-0.008),
                        fontsize=11, color=colors[ci], fontweight='bold',
                        arrowprops=dict(arrowstyle='->', color=colors[ci], lw=1.0))
            ax.annotate("{:.4f}".format(avs[-1]),
                        xy=(ts[-1], avs[-1]), xytext=(ts[-1]+12, avs[-1]+0.004),
                        fontsize=11, color=colors[ci], fontweight='bold',
                        arrowprops=dict(arrowstyle='->', color=colors[ci], lw=1.0))
    cte_text_lines = []
    for ci, comp in enumerate(comps):
        pts = [(T, parsed_all[(comp, T)]) for T in temps
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
        if pts and len(pts) == 4:
            pts.sort()
            avs_int = [p[1]['a_mean'] for p in pts]
            _cte = calc_cte_report(list(zip([p[0] for p in pts], avs_int)))
            if _cte:
                da = avs_int[-1] - avs_int[0]
                cte_text_lines.append("x_Pt={:.2f}: Da={:.4f}A  a2pt={:.2e}  a_fit={:.2e}".format(
                    comp, da, _cte['alpha_2pt'], _cte['alpha_fit']))
    if cte_text_lines:
        # CTE box: BELOW the plot, with space reserved via subplots_adjust
        fig.text(0.12, -0.15, 'CTE Report:\n' + '\n'.join(cte_text_lines),
                 fontsize=11, fontfamily='monospace',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='wheat', alpha=0.9))
    ax.set_xlabel('Temperature (K)')
    ax.set_ylabel('Lattice parameter a (Angstrom)')
    ax.set_title('{} Thermal Expansion (seed={})'.format(title_prefix, seed),
                 fontsize=16, fontweight='bold')
    ax.legend(fontsize=12)
    ax.grid(alpha=0.3)
    plt.subplots_adjust(bottom=0.22)
    fig.savefig(os.path.join(out, a_vs_T_fn), dpi=150)
    plt.close(fig)
    print('  Plot: {}'.format(a_vs_T_fn))

    # 2. a(comp) at fixed T
    fig, ax = plt.subplots(figsize=(11, 7))
    for T in temps:
        pts = [(comp, parsed_all[(comp, T)]['a_mean'])
               for comp in comps
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
        if pts:
            pts.sort()
            xs = [p[0] for p in pts]
            avs = [p[1] for p in pts]
            ax.plot(xs, avs, 'o-', label='T={}K'.format(T), markersize=10, linewidth=2.5)
            for xi, yi in zip(xs, avs):
                ax.annotate("{:.4f}".format(yi), (xi, yi),
                            textcoords="offset points", xytext=(5, 5),
                            fontsize=10, rotation=45)
    comp_info = []
    for T in temps:
        pts = [(comp, parsed_all[(comp, T)]['a_mean'])
               for comp in comps
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
        if pts and len(pts) == 5:
            pts.sort()
            da_max = pts[-1][1] - pts[0][1]
            comp_info.append("T={}K: range={:.4f}A".format(T, da_max))
    if comp_info:
        props = dict(boxstyle='round,pad=0.4', facecolor='lightyellow', alpha=0.8,
                     edgecolor='#333333')
        ax.text(0.02, 0.98, '\n'.join(comp_info),
                transform=ax.transAxes, fontsize=10, verticalalignment='top',
                fontfamily='monospace', bbox=props)
    ax.set_xlabel('Pt fraction x_Pt')
    ax.set_ylabel('Lattice parameter a (Angstrom)')
    ax.set_title('{} a(comp) at fixed temperatures (seed={})'.format(title_prefix, seed),
                 fontsize=16, fontweight='bold')
    ax.legend(fontsize=12)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(out, a_vs_comp_fn), dpi=150)
    plt.close(fig)
    print('  Plot: {}'.format(a_vs_comp_fn))

    # 3. Facets 2x3
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle('{} Thermal Expansion (seed={})'.format(title_prefix, seed), fontsize=18, fontweight='bold')
    for ci, comp in enumerate(comps):
        ax = axes.flatten()[ci]
        pts = [(T, parsed_all[(comp, T)]) for T in temps
               if (comp, T) in parsed_all and parsed_all[(comp, T)].get('a_mean')]
        if pts:
            pts.sort()
            ts = [p[0] for p in pts]
            vs = [p[1] for p in pts]
            avs = [v['a_mean'] for v in vs]
            errs = [v.get('a_std', 0) for v in vs]
            ax.errorbar(ts, avs, yerr=errs, fmt='o-', color=colors[ci], capsize=4, markersize=8, linewidth=2)
            for idx, (ti, vi) in enumerate(zip(ts, avs)):
                std = errs[idx] if idx < len(errs) else 0
                ax.annotate("{:.4f}".format(vi),
                            (ti, vi), textcoords="offset points",
                            xytext=(0, -16), fontsize=10,
                            ha='center', color=colors[ci], fontweight='bold',
                            bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.8,
                                      edgecolor=colors[ci]))
                ax.annotate(u"\u00b1{:.1e}".format(std),
                            (ti, vi), textcoords="offset points",
                            xytext=(0, -24), fontsize=9,
                            ha='center', color='#222222')
            rise = avs[-1] - avs[0]
            _cte = calc_cte_report(list(zip(ts, avs)))
            if _cte:
                ax.set_title('x_Pt={:.2f}\na2pt={:.2e} a_fit={:.2e} range={:.1e}'.format(
                    comp, _cte['alpha_2pt'], _cte['alpha_fit'], _cte['alpha_range']), fontsize=12)
                drifts = [v.get('drift', 0) for v in vs]
                max_drift = max(abs(d) for d in drifts)
                ax.text(0.02, 0.85, "Da={:.4f}A\nmax|drift|={:.1e}".format(rise, max_drift),
                        transform=ax.transAxes, fontsize=10, verticalalignment='top',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='#d4edda',
                                  edgecolor='#155724', alpha=0.8))
            else:
                alpha = rise / avs[0] / 900 if avs[0] > 0 else 0
                ax.set_title('x_Pt={:.2f}\nDa={:.4f}A a={:.2e}'.format(comp, rise, alpha), fontsize=12)
            ax.set_xlabel('T (K)')
            ax.set_ylabel('a (Angstrom)')
            ax.grid(alpha=0.3)
    for i in range(len(comps), 6):
        axes.flatten()[i].set_visible(False)
    plt.tight_layout()
    fig.savefig(os.path.join(out, a_vs_T_facets_fn), dpi=150)
    plt.close(fig)
    print('  Plot: {}'.format(a_vs_T_facets_fn))


# ── Potential helper ──
def get_potential(comp, potential_type='meam'):
    """Return (pot_line, pair_style_type) for given Fe-Pt composition.

    potential_type: 'meam' (default) or 'zhou04'.
    """
    if potential_type == 'zhou04':
        return 'potentials/Zhou04.eam.alloy', 'eam_alloy'
    if comp >= 0.99:
        return 'potentials/Pt_u3.eam', 'eam'
    meam_lib = 'potentials/library.meam'
    meam_params = 'potentials/PtFe.meam'
    return 'pair_coeff * * {} Fe Pt {} Fe Pt'.format(meam_lib, meam_params), 'meam'


# ── Stale process handler ──
def check_stale_lammps():
    """Kill stale lmp.exe processes before starting a new run."""
    import subprocess as _sp
    try:
        out = _sp.check_output('tasklist /fo csv /nh /fi "imagename eq lmp.exe"',
                               shell=True, timeout=30, text=True, stderr=_sp.DEVNULL)
        if 'lmp.exe' in out:
            print('  Found stale lmp.exe — killing...')
            _sp.run('taskkill /f /im lmp.exe', shell=True, timeout=15,
                    stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            import time as _t
            for _ in range(3):
                _t.sleep(1)
                check = _sp.run('tasklist /nh /fi "imagename eq lmp.exe"',
                                shell=True, timeout=10, capture_output=True, text=True)
                if 'lmp.exe' not in check.stdout:
                    print('  All stale lmp.exe killed.')
                    return
            print('  WARNING: some stale lmp.exe may remain.')
    except Exception:
        pass


# ── Write protocol log ──
def write_protocol_log(outdir, script_name, eq_steps, prod_steps, tdamp, pdamp,
                       comps, temps, seed,
                       proto_name='protocol.txt',
                       mode_label=None, mode_extra=None):
    """Write run protocol log with parameters and points list."""
    proto_path = os.path.join(outdir, proto_name)
    with open(proto_path, 'w', encoding='utf-8') as f:
        f.write('Fe-Pt MD Protocol\n')
        f.write('Script: {}\n'.format(script_name))
        f.write('Mode: {}\n'.format(mode_label or 'N/A'))
        if mode_extra:
            for k, v in mode_extra.items():
                f.write('  {}: {}\n'.format(k, v))
        f.write('Eq steps: {}\n'.format(eq_steps))
        f.write('Prod steps: {}\n'.format(prod_steps))
        f.write('Tdamp: {}  Pdamp: {}\n'.format(tdamp, pdamp))
        f.write('Seed: {}\n'.format(seed))
        f.write('Temperatures: {}\n'.format(', '.join(str(T) for T in temps)))
        f.write('Compositions: {}\n'.format(', '.join('{:.2f}'.format(c) for c in comps)))
        f.write('Points:\n')
        for comp in comps:
            for T in temps:
                f.write('  x_Pt={:.2f} T={}K\n'.format(comp, T))
    print('  Protocol: {}'.format(proto_path))
    return proto_path


