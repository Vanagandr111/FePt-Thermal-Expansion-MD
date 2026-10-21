"""Pre-run time/memory estimation from a calibrated profile (stdlib only).

The profile (data/estim_profile.json) is filled by
scripts/calibrate_profile.py on the actual machine and/or auto-updated
from every finished run's printed ms/step line. Before calibration the
estimator falls back to documented pre-calibration guesses and says so
(confidence='guess'), so nothing is ever silently invented.
"""
import json
import os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_PATH = os.path.join(PROJ, 'data', 'estim_profile.json')

# Pre-calibration honest guesses (marked as such in the UI):
#   mace/cuda: real control run: 54.4 ms/step @256 atoms (RTX 3070 Ti),
#              VRAM alloc peak 1360 MB, RSS 1841 MB;
#   mace/cpu : code comment "~4s per force call @256 atoms";
#   lammps   : classic EAM on CPU is ~2 ms/step @256 (order of magnitude).
GUESS = {
    'mace': {
        'cuda': {'ms_per_step': 54.4, 'vram_mb': 1360.0, 'rss_mb': 1850.0},
        'cpu': {'ms_per_step': 4000.0, 'vram_mb': 0.0, 'rss_mb': 3000.0},
    },
    'lammps': {
        'cpu': {'ms_per_step': 2.0, 'vram_mb': 0.0, 'rss_mb': 600.0},
        'cuda': {'ms_per_step': 2.0, 'vram_mb': 0.0, 'rss_mb': 600.0},
    },
}
COMPILE_S = 60.0        # torch.compile one-time cost on cuda (real: ~53 s)
OVERHEAD_DEFAULT = 1.6  # wall / production window (relax+io+parse; from the
                        # real control run 646 s wall vs 381 s production)


def natoms_of(grid):
    """fcc supercell atoms for grid n: 4*n^3 (2 -> 32, 4 -> 256)."""
    n = max(1, int(grid))
    return 4 * n ** 3


def interp(points, natoms):
    """Linear interpolation of [(natoms, value), ...]; None if no points.

    Outside the calibrated range it extends the closest segment slope
    (honest extrapolation, flagged via the returned tuple's 'extrap').
    Returns (value, extrap_bool) or (None, False).
    """
    pts = sorted((float(a), float(v)) for a, v in points)
    if not pts:
        return None, False
    n = float(natoms)
    if len(pts) == 1:
        return pts[0][1], False
    if n <= pts[0][0]:
        (n0, v0), (n1, v1) = pts[0], pts[1]
        slope = (v1 - v0) / (n1 - n0) if n1 > n0 else 0.0
        return v0 + slope * (n - n0), n < n0
    if n >= pts[-1][0]:
        (n0, v0), (n1, v1) = pts[-2], pts[-1]
        slope = (v1 - v0) / (n1 - n0) if n1 > n0 else 0.0
        return v1 + slope * (n - n1), n > n1
    for (n0, v0), (n1, v1) in zip(pts, pts[1:]):
        if n0 <= n <= n1:
            t = (n - n0) / (n1 - n0) if n1 > n0 else 0.0
            return v0 + t * (v1 - v0), False
    return None, False


def _profile_points(profile, mode, device):
    return [(p['natoms'], p['ms_per_step']) for p in profile.get('points', [])
            if p.get('mode') == mode and p.get('device') == device
            and p.get('ms_per_step')]


def estimate(profile, mode, device, grid, temps, eq, prod):
    """One pre-run estimate dict for the GUI card.

    mode: 'mace'|'lammps'; device: 'cuda'|'cpu'; grid: int n;
    temps: string "300 1200" (or list); eq/prod: step counts.
    """
    profile = profile or {}
    if mode == 'lammps':
        device = 'cpu'          # classic engine has no GPU path here
    n = natoms_of(grid)
    try:
        ntemps = len(str(temps).split())
    except Exception:
        ntemps = 1
    ntemps = max(1, ntemps)
    steps = (int(eq) + int(prod)) * ntemps

    guess = GUESS.get(mode, GUESS['mace']).get(
        device, GUESS['mace']['cuda'])
    pts = _profile_points(profile, mode, device)
    calibrated = bool(pts)
    ms, ms_ext = interp(pts, n) if pts else (None, False)
    if ms is None:
        ms = guess['ms_per_step']
    vram = ram = None
    if calibrated:
        vp = [(p['natoms'], p['vram_mb']) for p in profile.get('points', [])
              if p.get('mode') == mode and p.get('device') == device
              and p.get('vram_mb') is not None]
        rp = [(p['natoms'], p['rss_mb']) for p in profile.get('points', [])
              if p.get('mode') == mode and p.get('device') == device
              and p.get('rss_mb') is not None]
        vram, _ = interp(vp, n) if vp else (None, False)
        ram, _ = interp(rp, n) if rp else (None, False)
    if vram is None:
        vram = guess['vram_mb']
    if ram is None:
        ram = guess['rss_mb']

    overhead = float(profile.get('overhead') or OVERHEAD_DEFAULT)
    md_s = steps * ms / 1000.0
    extra_s = ntemps * COMPILE_S if (mode == 'mace' and device == 'cuda') else 0.0
    seconds = md_s * overhead + extra_s

    if mode == 'lammps':
        confidence = 'guess'          # no lammps calibration path yet
    elif calibrated and not ms_ext:
        confidence = 'calibrated'
    elif calibrated:
        confidence = 'extrapolated'
    else:
        confidence = 'guess'

    return {
        'natoms': n,
        'points': ntemps,
        'steps': steps,
        'ms_step': round(ms, 2),
        'seconds': round(seconds, 1),
        'md_seconds': round(md_s, 1),
        'vram_mb': round(vram, 0),
        'ram_mb': round(ram, 0),
        'confidence': confidence,
        'overhead': overhead,
        'machine_gpu': (profile.get('machine') or {}).get('gpu'),
        'calibrated_at': profile.get('calibrated_at'),
    }


def fits_memory(vram_mb, total_mb, warn=70.0, bad=87.0):
    """Traffic-light verdict for a VRAM estimate vs the card total.

    >=87% of the card is the documented thrashing zone; >=100% does not
    fit at all. Returns dict for the UI.
    """
    if not total_mb or vram_mb is None:
        return {'ok': None, 'level': 'off', 'percent': None}
    percent = 100.0 * float(vram_mb) / float(total_mb)
    level = 'bad' if percent >= bad else ('warn' if percent >= warn else 'ok')
    return {
        'ok': percent < 100.0,
        'level': level,
        'percent': round(percent, 1),
        'total_mb': total_mb,
    }


def load_profile(path=None):
    try:
        with open(path or PROFILE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def update_point(profile, mode, device, grid, ms_per_step,
                 source='run'):
    """Merge/refresh one calibrated point (auto-calibration from a run).

    Returns True if the profile dict changed.
    """
    n = natoms_of(grid)
    pts = profile.setdefault('points', [])
    for p in pts:
        if (p.get('mode') == mode and p.get('device') == device
                and p.get('natoms') == n):
            if abs(float(p.get('ms_per_step', 0)) - float(ms_per_step)) < 1e-9:
                return False
            p['ms_per_step'] = round(float(ms_per_step), 2)
            p['source'] = source
            return True
    pts.append({'mode': mode, 'device': device, 'grid': int(grid),
                'natoms': n, 'ms_per_step': round(float(ms_per_step), 2),
                'vram_mb': None, 'rss_mb': None, 'source': source})
    return True


def save_profile(profile, path=None):
    path = path or PROFILE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
