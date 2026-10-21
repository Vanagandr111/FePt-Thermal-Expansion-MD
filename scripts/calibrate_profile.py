"""Calibrate the GUI time/memory estimator on THIS machine.

Design notes (why per-size subprocess):
  * torch.compile recompiles when the neighbor graph outgrows the pad
    budget ("Edge count ... exceeded pad budget"), and doing several
    sizes in one process leaked allocator/inductor state -> the whole
    calibration died silently. One child process per size keeps the peak
    VRAM measurement clean and a failure only skips that size.
  * No relax/MD here: we measure production-like force+stress calls,
    which is exactly what the estimator's ms/step needs.

Parent:
    python scripts/calibrate_profile.py --device cuda --grids 2 3 4
Child (single size, prints one marker line):
    ... --single 4
Points land in data/estim_profile.json (gui/estimator.py reads it) and
are refreshed automatically from every finished run's ms/step output.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(_PROJ, 'scripts')
PROFILE_PATH = os.path.join(_PROJ, 'data', 'estim_profile.json')
MARKER = '[CALIB_POINT] '


def load_profile():
    try:
        with open(PROFILE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_profile(profile):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    tmp = PROFILE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=1, ensure_ascii=False)
    os.replace(tmp, PROFILE_PATH)


def merge_point(profile, point):
    """Replace the (mode, device, grid) point, else append. Returns True."""
    pts = profile.setdefault('points', [])
    for i, p in enumerate(pts):
        if (p.get('mode') == point['mode']
                and p.get('device') == point['device']
                and p.get('grid') == point['grid']):
            if p != point:
                pts[i] = point
                return True
            return False
    pts.append(point)
    return True


# ---------------------------------------------------------------- child --
def calibrate_single(args):
    """Measure ONE size in this (fresh) process; print [CALIB_POINT] json."""
    import psutil
    import torch
    import lmp_helper as lmp
    from run_main_mace import (FastMACECalculator, find_model,
                               read_lammps_data, _print_weights)

    model = find_model(args.model)
    if model is None:
        print('ERROR: no MACE model found (put one into potentials/gpu/)')
        return 1
    cuda = args.device == 'cuda'
    # match the REAL run config: production uses torch.compile on cuda,
    # the calibration must measure the same code path (54 ms/step vs
    # ~400 ms/step measured without compile)
    calc = FastMACECalculator(model_paths=model, device=args.device,
                              compile_mode='default' if cuda else None,
                              use_bf16=cuda)
    _print_weights(calc)
    proc = psutil.Process()
    gpu_name = (torch.cuda.get_device_name(0) if cuda and
                torch.cuda.is_available() else None)
    g = args.single
    t0 = time.time()
    datafile = lmp.gen_structure(args.comp, nx=g, ny=g, nz=g, force=True)
    atoms = read_lammps_data(datafile)
    atoms.calc = calc
    # direct calculate() bypasses the ASE cache: get_forces() with
    # unchanged positions would serve the cache and measure nothing
    calc.calculate(atoms=atoms)                  # warmup / compile
    if cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    rss0 = proc.memory_info().rss / 2 ** 20
    t1 = time.perf_counter()
    for _ in range(args.steps):
        calc.calculate(atoms=atoms)              # MACE: stress included
    if cuda:
        torch.cuda.synchronize()
    ms_step = 1000.0 * (time.perf_counter() - t1) / args.steps
    vram = (torch.cuda.max_memory_allocated() / 2 ** 20) if cuda else 0.0
    rss = proc.memory_info().rss / 2 ** 20
    point = {
        'mode': 'mace', 'device': args.device, 'grid': int(g),
        'natoms': 4 * int(g) ** 3,
        'ms_per_step': round(ms_step, 2),
        'vram_mb': round(max(vram, 0.0), 1),
        'rss_mb': round(max(rss, rss0), 1),
        'gpu': gpu_name, 'model': os.path.basename(model),
        'compile': bool(cuda),
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    print(MARKER + json.dumps(point), flush=True)
    print('[calib] grid={} n={:4d}  {:7.1f} ms/step  vram={:5.0f} MB  '
          'rss={:5.0f} MB  ({:.0f}s)'.format(
              g, point['natoms'], ms_step, vram, rss, time.time() - t0),
          flush=True)
    return 0


# --------------------------------------------------------------- parent --
def run_child(args, grid):
    cmd = [sys.executable, '-u', os.path.abspath(__file__),
           '--single', str(grid), '--device', args.device,
           '--steps', str(args.steps), '--comp', str(args.comp)]
    if args.model:
        cmd += ['--model', args.model]
    try:
        r = subprocess.run(cmd, cwd=_PROJ, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,
                           timeout=args.grid_timeout,
                           encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        print('[calib] grid={} TIMEOUT after {}s — skipped'.format(
            grid, args.grid_timeout), flush=True)
        return None
    out = r.stdout or ''
    for ln in out.splitlines():
        if ln.startswith(MARKER):
            try:
                return json.loads(ln[len(MARKER):])
            except Exception:
                pass
    print('[calib] grid={} FAILED (exit {}) — skipped'.format(
        grid, r.returncode), flush=True)
    tail = [l for l in out.splitlines() if l.strip()][-6:]
    for l in tail:
        print('    ' + l, flush=True)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    ap.add_argument('--grids', type=int, nargs='+', default=[2, 3, 4])
    ap.add_argument('--steps', type=int, default=20,
                    help='force+stress evaluations per size '
                         '(first = warmup/compile)')
    ap.add_argument('--comp', type=float, default=0.5)
    ap.add_argument('--model', default=None,
                    help='path to MACE .model (default: find_model)')
    ap.add_argument('--single', type=int, default=None,
                    help='internal: measure one size and print a marker')
    ap.add_argument('--grid-timeout', type=int, default=600,
                    help='per-size timeout in the parent')
    args = ap.parse_args()

    if args.single is not None:
        return calibrate_single(args)

    prof = load_profile()
    got = 0
    for g in args.grids:
        print('[calib] --- size grid={} ---'.format(g), flush=True)
        point = run_child(args, g)
        if point:
            merge_point(prof, point)
            save_profile(prof)      # persist after EVERY size
            got += 1
            print('[calib] grid={} n={}  {:.1f} ms/step  vram={:.0f} MB  '
                  'rss={:.0f} MB  [{}]'.format(
                      point['grid'], point['natoms'], point['ms_per_step'],
                      point.get('vram_mb') or 0, point.get('rss_mb') or 0,
                      point.get('ts')), flush=True)

    prof['version'] = 1
    prof['machine'] = {
        'gpu': next((p.get('gpu') for p in prof.get('points', [])
                     if p.get('gpu')), None),
        'platform': platform.platform(),
        'python': sys.version.split()[0],
    }
    # wall/production overhead from the real control run (646 s wall vs
    # 381 s production window -> 1.7; keep 1.6 as the working default)
    prof.setdefault('overhead', 1.6)
    prof['calibrated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    save_profile(prof)
    print('[calib] saved {} ({}/{} sizes ok)'.format(
        PROFILE_PATH, got, len(args.grids)))
    return 0 if got else 1


if __name__ == '__main__':
    raise SystemExit(main())
