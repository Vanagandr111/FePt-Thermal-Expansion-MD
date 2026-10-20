#!/usr/bin/env python3
"""
run_main_mace.py — Fe-Pt thermal expansion via MACE neural potential (ASE-MD).
Cross-platform (Windows/Linux) with CPU/GPU selection. No Windows-only code.

Part of the main project D:/projects/Nikolay (LAMMPS pipeline is untouched:
this runner is an independent alternative to scripts/run_main.py).

Differences vs client's run_main_mace.py:
  1. device: auto cuda->cpu (client hardcoded device='cuda' -> crash w/o GPU)
  2. model search: --model, scripts/, potentials/, project root
     (client looked only in project root -> FileNotFoundError)
  3. NPT: Langevin thermostat + MTKBarostat (client had pure Langevin NVT ->
     frozen cell -> zero CTE: no thermal expansion at all)
  4. full temperature grid by default (client had TEMPS=[300] test stub)
  5. reads LAMMPS data file itself (client's ase.io.read with 'atomic' style
     and no Masses section produces wrong/undefined elements)

Usage (Windows / .venv-mace, Linux / venv — same flags):
  python scripts/run_main_mace.py --quick                 # smoke test
  python scripts/run_main_mace.py --device cuda           # GPU (auto->cpu)
  python scripts/run_main_mace.py --device cpu            # CPU only
  python scripts/run_main_mace.py                         # full 6x6 grid, 256 atoms
  python scripts/run_main_mace.py --grid 4 --eq 50000 --prod 100000 \
      --device cuda --out results_mace_gpu   # production, GPU
  python scripts/run_main_mace.py --model potentials/FePt_potential.pt

Device: --device auto (default) picks cuda when available, else cpu;
explicit --device cuda on a machine without CUDA falls back to CPU
with a warning instead of crashing.
"""
import argparse
import math
import os
import subprocess
import sys
import time

import numpy as np

from mace.calculators import MACECalculator  # noqa: E402 (needs torch env)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp_helper as lmp                      # noqa: E402
from gen_structure import generate_structure  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import ase.units as units                     # noqa: E402
from ase import Atoms                         # noqa: E402
from ase.md.velocitydistribution import (     # noqa: E402
    MaxwellBoltzmannDistribution,
)
from ase.optimize import BFGS                 # noqa: E402

# NPT engine differs across ASE versions:
#   ASE >= 3.29  -> ase.md.nose_hoover_chain.IsotropicMTKNPT (all-in-one)
#   ASE 3.23-3.28 -> Langevin + ase.md.npt.MTKBarostat
#   ASE < 3.23   -> Langevin + ase.md.npt.NPT barostat hook
try:
    from ase.md.nose_hoover_chain import IsotropicMTKNPT
    _NPT_MODE = 'nhc'
except ImportError:
    IsotropicMTKNPT = None
    _NPT_MODE = 'langevin'
    from ase.md.langevin import Langevin
    try:
        from ase.md.npt import MTKBarostat
        _NPT_MODE = 'langevin+mtk'
    except ImportError:
        MTKBarostat = None

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(_PROJ, 'data')
_OUT = os.path.join(_PROJ, 'results_mace')
_PLOTS = os.path.join(_PROJ, 'plots')
_LAT = 3.615


# ── LAMMPS data reader (atomic style, types 1=Fe 2=Pt) ─────────────
def read_lammps_data(path):
    """Parse atomic-style LAMMPS data file written by gen_structure.py.

    Returns ase.Atoms with correct Fe/Pt symbols and orthorhombic cell.
    (ase.io.read with style='atomic' cannot infer elements without a
    Masses section — that was one of the client's crash sources.)
    """
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    natoms = None
    box = [None] * 6
    atom_rows = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.endswith('atoms'):
            natoms = int(ln.split()[0])
        elif 'atom types' in ln:
            pass
        elif ln.endswith('xlo xhi'):
            box[0], box[1] = map(float, ln.split()[:2])
        elif ln.endswith('ylo yhi'):
            box[2], box[3] = map(float, ln.split()[:2])
        elif ln.endswith('zlo zhi'):
            box[4], box[5] = map(float, ln.split()[:2])
        elif ln == 'Atoms':
            # blank lines are already stripped from `lines` above
            i += 1
            while i < len(lines) and len(lines[i].split()) >= 5:
                p = lines[i].split()
                atom_rows.append((int(p[0]), int(p[1]),
                                  float(p[2]), float(p[3]), float(p[4])))
                i += 1
            break
        i += 1

    if natoms is None or len(atom_rows) != natoms:
        raise RuntimeError('bad LAMMPS data file: {}'.format(path))

    atom_rows.sort(key=lambda r: r[0])
    zmap = {1: 26, 2: 78}          # Fe, Pt
    symbols = [zmap[r[1]] for r in atom_rows]
    positions = np.array([[r[2], r[3], r[4]] for r in atom_rows])
    cell = [[box[1] - box[0], 0, 0],
            [0, box[3] - box[2], 0],
            [0, 0, box[5] - box[4]]]
    atoms = Atoms(numbers=symbols, positions=positions, cell=cell, pbc=True)
    return atoms


# ── model search ───────────────────────────────────────────────────
def find_model(cli_model):
    cands = []
    if cli_model:
        cands.append(cli_model)
    cands += [
        os.path.join(_PROJ, 'scripts', 'FePt-potential.pt'),
        os.path.join(_PROJ, 'scripts', 'FePt_potential.pt'),
        os.path.join(_PROJ, 'potentials', 'FePt-potential.pt'),
        os.path.join(_PROJ, 'potentials', 'FePt_potential.pt'),
        os.path.join(_PROJ, 'FePt-potential.pt'),
        os.path.join(_PROJ, 'FePt_potential.pt'),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    # any .model/.pt under potentials/ as last resort
    pot = os.path.join(_PROJ, 'potentials')
    if os.path.isdir(pot):
        for fn in sorted(os.listdir(pot)):
            if fn.endswith(('.model', '.pt', '.ckpt')):
                return os.path.abspath(os.path.join(pot, fn))
    return None


# ── per-point MD ───────────────────────────────────────────────────
def _make_dynamics(atoms, T, timestep_fs):
    """Build NPT integrator for the installed ASE version."""
    if _NPT_MODE == 'nhc':
        # ASE >= 3.29: all-in-one isothermal-isobaric integrator
        return IsotropicMTKNPT(
            atoms, timestep_fs * units.fs,
            temperature_K=float(T), pressure_au=0.0,
            tdamp=100.0 * units.fs, pdamp=1000.0 * units.fs)
    # older ASE: Langevin thermostat, barostat attached separately
    dyn = Langevin(atoms, timestep_fs * units.fs,
                   temperature_K=T, friction=0.01 / units.fs)
    if _NPT_MODE == 'langevin+mtk':
        barostat = MTKBarostat(atoms, temperature_K=T, externalstress=0.0,
                               pressure_10to10Pa=0.0)
        dyn.attach(barostat, interval=10)
    else:
        raise RuntimeError(
            'This ASE has no barostat (need >= 3.23 for MTKBarostat, '
            'or >= 3.29 for IsotropicMTKNPT). NPT is mandatory: without '
            'it the cell is frozen and CTE = 0.')
    return dyn


def run_point(calc, comp, T, eq_steps, prod_steps, thermo_interval,
              timestep_fs=1.0, seed=42, grid=4):
    """NPT run for one (composition, T) point.

    Client's version ran pure Langevin (NVT): cell frozen, CTE = 0.
    Here: NPT integrator at 0 bar -> volume expands with T.
    `grid`: supercell replication (4 -> 256 atoms, 2 -> 32 atoms).
    Returns dict in lmp_helper.parse_production() format.
    """
    t0 = time.time()
    datafile = lmp.gen_structure(comp, nx=grid, ny=grid, nz=grid, force=True)
    atoms = read_lammps_data(datafile)
    atoms.calc = calc

    # 1. relax internal coordinates (client had this, but cell was frozen).
    #    MACE force call on CPU is ~4s for 256 atoms -> hard cap the steps.
    dyn_opt = BFGS(atoms, logfile=None)
    dyn_opt.run(fmax=0.1, steps=100)

    # 2. thermal velocities
    MaxwellBoltzmannDistribution(
        atoms, temperature_K=T, rng=np.random.default_rng(seed))

    # 3. NPT — THE fix: cell is free to expand
    dyn_md = _make_dynamics(atoms, T, timestep_fs)

    records = []

    def collect():
        # get_stress(voigt=True) already returns the 6-component voigt vector
        stress = atoms.get_stress(voigt=True)
        p_bar = float(np.mean(stress[:3])) / units.GPa * 1.0e5  # GPa->bar
        vol = atoms.get_volume()
        a_lat = (4.0 * vol / len(atoms)) ** (1.0 / 3.0)
        records.append((a_lat, p_bar, vol))

    collect()  # t=0 point too
    dyn_md.attach(collect, interval=thermo_interval)
    dyn_md.run(eq_steps)
    n_eq = len(records)
    dyn_md.run(prod_steps)

    # parse production window
    a_vals = [r[0] for r in records[n_eq:]]
    p_vals = [r[1] for r in records[n_eq:]]
    a_arr = np.array(a_vals)
    drift = float(a_arr[-1] - a_arr[0]) if len(a_arr) > 1 else 0.0
    wall = time.time() - t0

    print('  comp={:.2f} T={:4d}K  a={:.5f} A  n={:d}  wall={:.0f}s'
          .format(comp, T, float(a_arr.mean()), len(a_arr), wall))

    return {
        'a_mean': float(a_arr.mean()),
        'a_std': float(a_arr.std()),
        'a_min': float(a_arr.min()),
        'a_max': float(a_arr.max()),
        'drift': drift,
        'n_points': len(a_vals),
        'mean_press': float(np.mean(p_vals)) if p_vals else 0.0,
        'std_press': float(np.std(p_vals)) if p_vals else 0.0,
        'runtime': int(round(wall)),
        't_eq': 0, 't_prod': 0, 'wall_s': wall,
        'max_t': T, 'final_step': 0,
        'drift_pct': 100.0 * drift / float(a_arr.mean()) if len(a_arr) else 0.0,
        'log': datafile,
    }


def write_cte_full(parsed_all, comps, temps, out):
    """CTE report for ANY number of temperature points.

    lmp_helper.write_cte_csv only handles exactly 4 points (==4 magic);
    full grid has 6 -> client's CTE report was silently empty.
    """
    import csv as _csv
    path = os.path.join(out, 'cte_report.csv')
    with open(path, 'w', newline='') as f:
        w = _csv.writer(f, delimiter=';')
        w.writerow(['x_Pt', 'a_300K', 'a_maxT', 'dA', 'CTE_fit',
                    'CTE_chordal', 'CTE_300_1200', 'R2', 'n_points'])
        for comp in comps:
            pts = [(T, parsed_all[(comp, T)]['a_mean'])
                   for T in temps if (comp, T) in parsed_all
                   and parsed_all[(comp, T)].get('a_mean') is not None]
            if len(pts) < 2:
                continue
            pts.sort(key=lambda p: p[0])
            rep = lmp.calc_cte_report(pts)
            if rep is None:
                continue
            a_lo, a_hi = rep['a_min'], rep['a_max']
            T_lo, T_hi = rep['T_min'], rep['T_max']
            chord = ((a_hi - a_lo) / (a_lo * (T_hi - T_lo))
                     if T_hi > T_lo else 0.0)
            w.writerow([
                '{:.2f}'.format(comp),
                '{:.6f}'.format(a_lo),
                '{:.6f}'.format(a_hi),
                '{:.6f}'.format(rep['delta_a_rise']),
                '{:.6e}'.format(rep['alpha_fit']),
                '{:.6e}'.format(chord),
                '{:.6e}'.format(rep['alpha_2pt']),
                '{:.6f}'.format(rep['r_squared']),
                rep['n_points'],
            ])
    print('  CTE: {}'.format(path))
    return path


class FastMACECalculator(MACECalculator):
    """MACECalculator + torch.compile (triton) + bf16 autocast.

    ~1.7x faster per step on consumer GPUs (measured: 94 -> 55 ms/step on
    RTX 3070 Ti, 256 atoms). bf16 outputs are cast back to fp32 before
    mace's numpy conversion (numpy has no bfloat16).
    """

    def __init__(self, *a, compile_mode='default', use_bf16=True, **kw):
        kw.setdefault('default_dtype', 'float32')
        kw['compile_mode'] = compile_mode
        super().__init__(*a, **kw)
        self._use_bf16 = bool(use_bf16) and str(self.device).startswith('cuda')

    def calculate(self, *a, **k):
        if self._use_bf16:
            import torch
            with torch.autocast('cuda', dtype=torch.bfloat16):
                return super().calculate(*a, **k)
        return super().calculate(*a, **k)

    def _create_result_tensors(self, num_models, num_atoms, batch, out):
        import torch
        out = {k: (v.float() if torch.is_tensor(v)
                   and v.dtype == torch.bfloat16 else v)
               for k, v in out.items()}
        with torch.autocast('cuda', enabled=False):
            return super()._create_result_tensors(
                num_models, num_atoms, batch, out)


def main():
    global _OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=None, help='path to MACE .pt/.model')
    ap.add_argument('--device', default='auto',
                    choices=['auto', 'cuda', 'cpu'])
    ap.add_argument('--quick', action='store_true',
                    help='smoke test: 1 comp, 2 T, short runs')
    ap.add_argument('--temps', type=int, nargs='+', default=None)
    ap.add_argument('--comps', type=float, nargs='+', default=None)
    ap.add_argument('--eq', type=int, default=None)
    ap.add_argument('--prod', type=int, default=None)
    ap.add_argument('--interval', type=int, default=100,
                    help='thermo sample interval (steps)')
    ap.add_argument('--grid', type=int, default=None,
                    help='supercell replication N: atoms=4*N^3 '
                         '(4 -> 256 atoms, 2 -> 32; default 4, quick: 2)')
    ap.add_argument('--out', default=None,
                    help='output directory (default <proj>/results_mace)')
    ap.add_argument('--fp32', action='store_true',
                    help='disable bf16 autocast (slower on GPU, max accuracy)')
    ap.add_argument('--no-compile', action='store_true',
                    help='disable torch.compile/triton (slower on GPU)')
    args = ap.parse_args()

    if args.quick:
        comps = [0.50]
        temps = [300, 1200]
        eq_steps, prod_steps = 300, 700
    else:
        comps = args.comps or [0.0, 0.20, 0.40, 0.50, 0.80, 1.00]
        temps = args.temps or [300, 600, 900, 1200, 1500, 1800]
        eq_steps = args.eq or 50_000
        prod_steps = args.prod or 100_000
    grid = args.grid or (2 if args.quick else 4)

    # device
    import torch
    cuda_ok = torch.cuda.is_available()
    if args.device == 'auto':
        device = 'cuda' if cuda_ok else 'cpu'
    else:
        device = args.device
        if str(device).startswith('cuda') and not cuda_ok:
            print('WARNING: --device {} requested but CUDA is unavailable; '
                  'falling back to CPU'.format(device))
            device = 'cpu'
    extra = ''
    if device == 'cuda':
        extra = ' on {}'.format(torch.cuda.get_device_name(0))
    print('Device: {}{} (torch {})'.format(device, extra, torch.__version__))

    # model
    model = find_model(args.model)
    if model is None:
        print('ERROR: MACE model file not found.')
        print('  Put FePt-potential.pt into scripts/ or potentials/,')
        print('  or pass --model /path/to/model.pt')
        return 1
    print('Model: {}'.format(model))

    compile_mode = None
    use_bf16 = False
    if device.startswith('cuda'):
        compile_mode = None if args.no_compile else 'default'
        use_bf16 = not args.fp32
    print('MACE speed mode: compile={} bf16={}'.format(
        compile_mode or 'off', 'on' if use_bf16 else 'off'))
    calc = FastMACECalculator(model_paths=model, device=device,
                              compile_mode=compile_mode,
                              use_bf16=use_bf16)

    if args.out:
        _OUT = os.path.abspath(args.out)
    os.makedirs(_OUT, exist_ok=True)
    print('Fe-Pt CTE — MACE NNP | {}x{} grid, EQ={} PROD={}, '
          '{} atoms/point ({}^3 supercell)'
          .format(len(comps), len(temps), eq_steps, prod_steps,
                  4 * grid ** 3, grid))

    seed = 42
    parsed_all = {}
    for comp in comps:
        print('comp x_Pt={:.2f}'.format(comp))
        for T in temps:
            parsed_all[(comp, T)] = run_point(
                calc, comp, T, eq_steps, prod_steps, args.interval,
                seed=seed, grid=grid)

    lmp.write_csv(parsed_all, comps, temps, _OUT, seed,
                  mode_label='mace', eq_steps=eq_steps,
                  prod_steps=prod_steps)
    write_cte_full(parsed_all, comps, temps, _OUT)
    try:
        lmp.make_plots(parsed_all, comps, temps, seed, _OUT,
                       title_prefix='Fe-Pt MACE')
    except Exception as e:
        print('  plots skipped: {}'.format(e))
    lmp.print_trends(parsed_all, comps, temps, seed)
    print('DONE -> {}'.format(_OUT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
