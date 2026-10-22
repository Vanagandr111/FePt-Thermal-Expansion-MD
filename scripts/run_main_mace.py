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
import os
# CUDA: avoid allocator fragmentation (parallel workers + inductor temp
# buffers OOM'd on an 8 GiB card with 5 GiB still "free").
# garbage_collection_threshold:0.8 = the allocator reclaims segment slack
# itself before hitting the physical cap.  If a torch/driver combo rejects
# this key (rare on WDDM), the except-fallback below swaps in
# max_split_size_mb:128 — same intent, coarser tool.
os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF',
                      'expandable_segments:True,'
                      'garbage_collection_threshold:0.8')
# F. Keep compiler caches inside the project: a clean machine / fresh clone
# must not recompile triton+inductor from scratch on every first run.
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('TRITON_CACHE_DIR',
                      os.path.join(_PROJ_ROOT, '.cache', 'triton'))
os.environ.setdefault('TORCHINDUCTOR_CACHE_DIR',
                      os.path.join(_PROJ_ROOT, '.cache', 'inductor'))
# torch 2.6 defaults weights_only=True; e3nn/o3 constants.pt legitimately
# need a plain pickle -> force the old behaviour, else import dies with
# UnpicklingError (or hangs in an unreadable traceback) in any shell where
# this variable was not preset.
os.environ.setdefault('TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD', '1')
import argparse
import math
import subprocess
import sys
import time

import numpy as np

from mace.calculators import MACECalculator  # noqa: E402 (needs torch env)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lmp_helper as lmp                      # noqa: E402
import lmpdata                                # noqa: E402
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


def _rss_mb():
    """Current process RSS in MB (no psutil dependency in the env)."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2 ** 20
    except Exception:
        pass
    try:
        import ctypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ('cb', ctypes.c_uint32),
                ('PageFaultCount', ctypes.c_uint32),
                ('PeakWorkingSetSize', ctypes.c_size_t),
                ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t),
                ('PeakPagefileUsage', ctypes.c_size_t)]

        buf = _PMC()
        buf.cb = ctypes.sizeof(_PMC)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(
                h, ctypes.byref(buf), buf.cb):
            return buf.WorkingSetSize / 2 ** 20
    except Exception:
        pass
    return -1.0


def _print_weights(calc_obj):
    """Audit line: how many model params carry requires_grad (must be 0).

    Frozen weights mean inference builds no autograd nodes on the weight
    path, so no weight activations are retained for backprop.
    """
    try:
        params = [p for m in getattr(calc_obj, 'models', [])
                  for p in m.parameters()]
        if not params:
            return
        grad = sum(1 for p in params if p.requires_grad)
        print('  [audit] model weights: {} params, requires_grad={} '
              '(0 = frozen, correct for inference)'.format(len(params), grad))
    except Exception:
        pass


def mem_report(tag=''):
    """Memory telemetry line (audit lever; read-only, no math effect).

    torch counters: peak allocator demand this process ever made (MB).
    rss: resident set of this process.  Empty line when torch missing.
    """
    try:
        import torch
        parts = ['  [mem {}]'.format(tag) if tag else '  [mem]']
        if torch.cuda.is_available():
            parts.append('alloc={:.0f}MB'.format(
                torch.cuda.max_memory_allocated() / 2 ** 20))
            parts.append('reserved={:.0f}MB'.format(
                torch.cuda.max_memory_reserved() / 2 ** 20))
        parts.append('rss={:.0f}MB'.format(_rss_mb()))
        print(' '.join(parts))
    except Exception:
        pass


# ── LAMMPS data reader (atomic style, types 1=Fe 2=Pt) ─────────────
def read_lammps_data(path):
    """Parse atomic-style LAMMPS data file written by gen_structure.py.

    Returns ase.Atoms with correct Fe/Pt symbols and orthorhombic cell.
    Parsing itself lives in scripts/lmpdata.py (shared with the GUI
    structure view) — this wrapper only adapts the exception type so the
    runner's error handling stays as before.
    """
    try:
        return lmpdata.read_lammps_data(path)
    except lmpdata.DataFileError as e:
        raise RuntimeError('bad LAMMPS data file: {}'.format(path)) from e


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
    # any .model/.pt under potentials/ or potentials/gpu/ as last resort
    # (the GUI indexes potentials/gpu — keep the CLI search in sync)
    for sub in ('potentials', os.path.join('potentials', 'gpu')):
        pot = os.path.join(_PROJ, sub)
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
              timestep_fs=1.0, seed=42, grid=4, prepare=True,
              md_log=None):
    """NPT run for one (composition, T) point.

    Client's version ran pure Langevin (NVT): cell frozen, CTE = 0.
    Here: NPT integrator at 0 bar -> volume expands with T.
    `grid`: supercell replication (4 -> 256 atoms, 2 -> 32 atoms).
    `prepare=False`: structure must already exist (parallel workers must
    not regenerate the same file concurrently - torn reads).
    Returns dict in lmp_helper.parse_production() format.
    """
    t0 = time.time()
    datafile = lmp.gen_structure(comp, nx=grid, ny=grid, nz=grid,
                                 force=prepare)
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
    _K_B = 8.617333262145e-5  # eV/K
    phase = {'name': 'eq'}
    emit = {'on': False}  # frames flow only after the collector attaches
    log_fh = None
    if md_log:
        try:
            d = os.path.dirname(md_log)
            if d:
                os.makedirs(d, exist_ok=True)
            log_fh = open(md_log, 'w', newline='')
            meta = {'x_Pt': '{:.2f}'.format(comp), 'T_K': T,
                    'atoms': len(atoms), 'grid': grid,
                    'eq_steps': eq_steps, 'prod_steps': prod_steps,
                    'dt_fs': timestep_fs, 'thermo_interval':
                    thermo_interval, 'seed': seed}
            for h in lmp.md_log_header(meta):
                log_fh.write(h + '\n')
            log_fh.flush()
        except OSError:
            log_fh = None

    def collect():
        # get_stress(voigt=True) already returns the 6-component voigt vector
        stress = atoms.get_stress(voigt=True)
        p_bar = float(np.mean(stress[:3])) / units.GPa * 1.0e5  # GPa->bar
        vol = atoms.get_volume()
        a_lat = (4.0 * vol / len(atoms)) ** (1.0 / 3.0)
        records.append((a_lat, p_bar, vol))
        # one LAMMPS-style frame: console (live GUI stream) + md_*.log
        step = int(getattr(dyn_md, 'nsteps', 0))
        pe = float(atoms.get_potential_energy())
        ke = float(atoms.get_kinetic_energy())
        temp = 2.0 * ke / (3.0 * len(atoms) * _K_B)
        if emit['on']:
            frame = lmp.md_log_line(step, step * timestep_fs / 1000.0,
                                    phase['name'], pe, ke, temp, p_bar,
                                    vol, a_lat)
            print(frame, flush=True)
            if log_fh:
                log_fh.write(frame + '\n')
                log_fh.flush()

    collect()  # t=0 point into records only (no frame yet: the attached
    # collector fires once more at nsteps==0 right when run() starts)
    emit['on'] = True
    dyn_md.attach(collect, interval=thermo_interval)
    try:
        dyn_md.run(eq_steps)
        n_eq = len(records)
        phase['name'] = 'prod'
        t_prod0 = time.time()
        dyn_md.run(prod_steps)
    except BaseException:
        if log_fh:
            log_fh.close()
        raise
    prod_wall = time.time() - t_prod0
    ms_step = 1000.0 * prod_wall / max(1, prod_steps)

    # parse production window
    a_vals = [r[0] for r in records[n_eq:]]
    p_vals = [r[1] for r in records[n_eq:]]
    a_arr = np.array(a_vals)
    drift = float(a_arr[-1] - a_arr[0]) if len(a_arr) > 1 else 0.0
    wall = time.time() - t0

    print('  comp={:.2f} T={:4d}K  a={:.5f} A  n={:d}  wall={:.0f}s  '
          'ms/step={:.1f}'
          .format(comp, T, float(a_arr.mean()), len(a_arr), wall, ms_step))
    mem_report('T{}'.format(T))

    # # === FINAL === end-of-run summary: console tail AND md_*.log
    # (same stats block the client reads in their reference logs)
    all_press = [r[1] for r in records]
    for ln in lmp.md_log_final(
            total_steps=eq_steps + prod_steps,
            log_records=len(records),
            log_interval=thermo_interval,
            a_mean=float(a_arr.mean()) if len(a_arr) else 0.0,
            a_std=float(a_arr.std()) if len(a_arr) else 0.0,
            a_min=float(a_arr.min()) if len(a_arr) else 0.0,
            a_max=float(a_arr.max()) if len(a_arr) else 0.0,
            drift=drift,
            n_prod_points=len(a_vals),
            runtime_s=wall,
            mean_press_bar=float(np.mean(all_press)) if all_press
            else 0.0):
        print(ln, flush=True)
        if log_fh:
            log_fh.write(ln + '\n')
    if log_fh:
        log_fh.flush()
        log_fh.close()

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
                    'CTE_chordal', 'CTE_300_1200', 'R2', 'n_points',
                    'seg_300_600', 'seg_600_900', 'seg_900_1200'])
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
            # segmental CTE per grid interval: '300-600K' -> seg_300_600
            segs = dict(zip(rep.get('seg_labels') or [],
                            rep.get('alpha_segmental') or []))
            # grid-node intervals win over adjacent-pair labels (dense
            # temperature grids never match the bare 300-600K lookups)
            segs.update(rep.get('facet_seg') or {})

            def _seg(label):
                v = segs.get(label)
                return '{:.6e}'.format(v) if v is not None else ''

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
                _seg('300-600K'),
                _seg('600-900K'),
                _seg('900-1200K'),
            ])
    print('  CTE: {}'.format(path))
    return path


class FastMACECalculator(MACECalculator):
    """MACECalculator + torch.compile (triton) + autocast (fp16/bf16).

    ~1.7x faster per step on consumer GPUs (measured: 94 -> 55 ms/step on
    RTX 3070 Ti, 256 atoms). bf16 outputs are cast back to fp32 before
    mace's numpy conversion (numpy has no bfloat16).
    """

    def __init__(self, *a, compile_mode='default', precision='fp16', **kw):
        kw.setdefault('default_dtype', 'float32')
        kw['compile_mode'] = compile_mode
        super().__init__(*a, **kw)
        # fp16: recommended default, works on Turing (T4) and newer;
        # bf16: Ampere+; fp32: no autocast, maximum accuracy
        cuda = str(self.device).startswith('cuda')
        self._autocast_dtype = {
            'fp16': 'float16', 'bf16': 'bfloat16', 'fp32': None,
        }.get(str(precision).lower(), 'float16') if cuda else None

    def calculate(self, *a, **k):
        if self._autocast_dtype:
            import torch
            with torch.autocast('cuda',
                                dtype=getattr(torch, self._autocast_dtype)):
                return super().calculate(*a, **k)
        return super().calculate(*a, **k)

    def _create_result_tensors(self, num_models, num_atoms, batch, out):
        import torch
        out = {k: (v.float() if torch.is_tensor(v)
                   and v.dtype in (torch.bfloat16, torch.float16) else v)
               for k, v in out.items()}
        with torch.autocast('cuda', enabled=False):
            return super()._create_result_tensors(
                num_models, num_atoms, batch, out)


# ---------------- D. Verlet-skin neighbour-list cache -------------------
# Off by default: --nl-skin <A>. The neighbour list is built once with
# cutoff+skin; later steps reuse it and filter pairs back to the model
# cutoff by CURRENT distances. Within skin/2 the pair set inside r_max is
# provably complete (classic Verlet), and the boolean filter preserves
# the matscipy edge order -> same pairs, same order (math unchanged).
_NL_CACHE = {'on': False, 'skin': 0.0, 'cutoff': None, 'pos0': None,
             'edge_index': None, 'unit_shifts': None,
             'hits': 0, 'rebuilds': 0}


# intent: monkey-patch mace's get_neighborhood with a skin-cached version
# allies: mace.data.atomic_data.get_neighborhood (target), main() (--nl-skin)
# sidefx: process-local patch of site-packages memory only (no files touched)
# purity: impure
# errors: falls back to the original builder on any non-PBC / shape case
def _install_nl_cache(skin):
    import mace.data.atomic_data as _ad
    orig = _ad.get_neighborhood

    def _gn(positions, cutoff, pbc=None, cell=None,
            true_self_interaction=False):
        c = _NL_CACHE
        if not c['on']:
            return orig(positions, cutoff, pbc, cell, true_self_interaction)
        import numpy as np
        pos = np.asarray(positions, dtype=float)
        if cell is None or np.asarray(cell).shape != (3, 3):
            cell_arr = np.eye(3)
        else:
            cell_arr = np.asarray(cell, dtype=float)
        pbc_arr = (np.zeros(3, bool) if pbc is None
                   else np.asarray(pbc, dtype=bool))
        hit = (c['pos0'] is not None
               and bool(pbc_arr.all())          # full-PBC fast path only
               and c['cutoff'] == cutoff
               and c['pos0'].shape == pos.shape)
        if hit:
            # max atomic displacement vs build positions (min-image w.r.t.
            # the current cell; isotropic cell growth adds ~0 at skin=1 A)
            d = pos - c['pos0']
            frac = d @ np.linalg.inv(cell_arr)
            frac -= np.round(frac)
            if np.linalg.norm(frac @ cell_arr, axis=1).max() > c['skin'] * 0.5:
                hit = False
        if hit:
            ei = c['edge_index']
            us = c['unit_shifts']
            dj = pos[ei[1]] - pos[ei[0]] + us @ cell_arr
            keep = np.einsum('ij,ij->i', dj, dj) <= cutoff * cutoff + 1e-8
            c['hits'] += 1
            return ei[:, keep], us[keep] @ cell_arr, us[keep], cell_arr
        # rebuild with the buffered cutoff, filter back to the model cutoff
        ei, shifts, us, c_out = orig(pos, cutoff + c['skin'], pbc, cell,
                                     true_self_interaction)
        dj = pos[ei[1]] - pos[ei[0]] + shifts
        keep = np.einsum('ij,ij->i', dj, dj) <= cutoff * cutoff + 1e-8
        c.update({'cutoff': cutoff, 'pos0': pos.copy(),
                  'edge_index': ei, 'unit_shifts': us})
        c['rebuilds'] += 1
        return ei[:, keep], shifts[keep], us[keep], c_out

    _ad.get_neighborhood = _gn
    _NL_CACHE['on'] = True
    _NL_CACHE['skin'] = float(skin)


def _mp_worker(tasks, out_queue, model, device, compile_mode, precision,
               eq_steps, prod_steps, interval, grid, base_seed,
               outdir=None):
    """Parallel worker: own compiled calculator on the shared GPU."""
    # Windows: spawned workers race on the shared triton cache (Permission
    # error on .cubin). Give each worker its own sub-cache; single-worker
    # runs keep the plain shared .cache/triton.
    for _ev in ('TRITON_CACHE_DIR', 'TORCHINDUCTOR_CACHE_DIR'):
        _base = os.environ.get(_ev)
        if _base:
            os.environ[_ev] = os.path.join(
                _base, 'pid{}'.format(os.getpid()))
    calc = FastMACECalculator(model_paths=model, device=device,
                              compile_mode=compile_mode, precision=precision)
    _print_weights(calc)
    # one cleanup pass before this worker's heavy loop (never per-step)
    import gc
    gc.collect()
    try:
        import torch
        if str(device).startswith('cuda') and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass
    for comp, T in tasks:
        parsed = run_point(
            calc, comp, T, eq_steps, prod_steps, interval,
            seed=base_seed, grid=grid, prepare=False,
            md_log=os.path.join(
                outdir, 'md_comp_{:.2f}_T{:d}.log'.format(comp, T))
            if outdir else None)
        out_queue.put(((comp, T), parsed))


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
    ap.add_argument('--lc', type=float, default=None,
                    help='seed lattice constant in Angstrom; default: '
                         'LC_TABLE by system (pt=experimental fcc 3.9242 A, '
                         'fe/MACE-EOS 3.5647, fept=historical 3.615 seed)')
    ap.add_argument('--nl-skin', type=float, default=1.0,
                    help='Verlet skin in Angstrom for the cached neighbour '
                         'list (D lever; merged after gate: 56.0->52.5 '
                         'ms/step). 0 = off, rebuild every step.')
    ap.add_argument('--out', default=None,
                    help='output directory (default <proj>/results_mace)')
    ap.add_argument('--precision', default='fp16',
                    choices=['fp16', 'bf16', 'fp32'],
                    help='compute/storage precision: fp16 (default, '
                         'recommended - works on Turing T4+), bf16 '
                         '(Ampere+), fp32 (no autocast, max accuracy)')
    ap.add_argument('--fp32', action='store_true',
                    help='legacy alias for --precision fp32')
    ap.add_argument('--no-compile', action='store_true',
                    help='disable torch.compile/triton (slower on GPU)')
    ap.add_argument('--compile-mode', default='default',
                    choices=['default', 'max-autotune-no-cudagraphs'],
                    help='torch.compile mode; A lever: '
                         'max-autotune-no-cudagraphs benchmarks triton '
                         'tiles (long first compile, no cuda graphs)')
    ap.add_argument('--workers', type=int, default=None,
                    help='parallel GPU workers (default: 2 on cuda when '
                         '>1 point; each worker owns a compiled calculator)')
    ap.add_argument('--seed', type=int, default=42,
                    help='RNG seed for the NPT initialization '
                         '(default 42)')
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
    # Seed lattice constant (Angstrom): None = LC_TABLE by system
    # (pt = our MACE-MP-0 EOS fit, fe/fept = historical v1.5 seed).
    lmp.SEED_LC = args.lc
    # D lever: skin-cached neighbour list (process-local patch; workers>1
    # does not inherit it -> use --workers 1 when --nl-skin is on).
    if args.nl_skin > 0:
        _install_nl_cache(args.nl_skin)
        print('MACE nl-skin: {:.2f} A (cached neighbour list)'.format(
            args.nl_skin))

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
    precision = str(args.precision or 'fp16').lower()
    if getattr(args, 'fp32', False):
        precision = 'fp32'          # legacy flag wins
    if not str(device).startswith('cuda'):
        precision = 'fp32'          # autocast only makes sense on cuda
    if device.startswith('cuda'):
        compile_mode = None if args.no_compile else args.compile_mode
    print('MACE speed mode: compile={} precision={}'.format(
        compile_mode or 'off', precision))

    if args.out:
        _OUT = os.path.abspath(args.out)
    os.makedirs(_OUT, exist_ok=True)
    print('Fe-Pt CTE — MACE NNP | {}x{} grid, EQ={} PROD={}, '
          '{} atoms/point ({}^3 supercell)'
          .format(len(comps), len(temps), eq_steps, prod_steps,
                  4 * grid ** 3, grid))

    seed = args.seed
    parsed_all = {}
    tasks = [(comp, T) for comp in comps for T in temps]
    workers = args.workers
    if workers is None:
        # 256-atom points already saturate the GPU (measured: 140s sequential
        # vs 147s with 2 workers) -> extra workers only help tiny systems.
        workers = 2 if (device.startswith('cuda') and grid <= 2
                        and len(tasks) > 1) else 1
    workers = max(1, min(workers, len(tasks)))
    print('Workers: {}'.format(workers))

    if workers == 1:
        calc = FastMACECalculator(model_paths=model, device=device,
                                  compile_mode=compile_mode,
                                  precision=precision)
        _print_weights(calc)
        # memory audit baseline: ONE cleanup pass before the heavy loop
        # (never inside the step loop — empty_cache there syncs CPU/GPU
        # and drops the fast allocator pool, 2-3x slowdown).
        import gc
        gc.collect()
        if device.startswith('cuda'):
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        for comp, T in tasks:
            print('comp x_Pt={:.2f}'.format(comp))
            parsed_all[(comp, T)] = run_point(
                calc, comp, T, eq_steps, prod_steps, args.interval,
                seed=seed, grid=grid,
                md_log=os.path.join(
                    _OUT, 'md_comp_{:.2f}_T{:d}.log'.format(comp, T)))
    else:
        # spawn: each worker owns its compiled calculator on the GPU;
        # point seed stays fixed (42) so results do not depend on the
        # worker layout.
        # Pre-generate structures in the parent: workers must never
        # regenerate the same file concurrently (torn-read race).
        for comp in {c for c, _ in tasks}:
            lmp.gen_structure(comp, nx=grid, ny=grid, nz=grid, force=True)
        from multiprocessing import get_context
        ctx = get_context('spawn')
        q = ctx.Queue()
        chunks = [tasks[i::workers] for i in range(workers)]
        procs = []
        for chunk in chunks:
            p = ctx.Process(
                target=_mp_worker,
                args=(chunk, q, model, device, compile_mode, precision,
                      eq_steps, prod_steps, args.interval, grid, seed,
                      _OUT))
            p.start()
            procs.append(p)
        # Collect with timeout: a dead worker must fail fast instead of
        # hanging forever in q.get().
        import queue as _queue
        owned = [set(c) for c in chunks]
        delivered = set()
        while len(delivered) < len(tasks):
            try:
                key, parsed = q.get(timeout=30)
            except _queue.Empty:
                dead = [(i, p.exitcode, sorted(owned[i] - delivered))
                        for i, p in enumerate(procs)
                        if not p.is_alive() and owned[i] - delivered]
                if dead:
                    raise RuntimeError(
                        'worker(s) died before delivering their points: {}'
                        .format(dead))
                continue
            parsed_all[key] = parsed
            delivered.add(key)
            print('  point done {}/{}'.format(len(parsed_all), len(tasks)))
        for p in procs:
            p.join()
            if p.exitcode != 0:
                print('WARNING: worker exited with code {}'.format(p.exitcode))

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
    mem_report('end')
    print('DONE -> {}'.format(_OUT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
