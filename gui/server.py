"""FePt Thermal Expansion — local web GUI (stdlib only, no framework).

Modes:
  * MACE (neural potential)     -> scripts/run_main_mace.py  (GPU/CPU)
  * LAMMPS (EAM/MEAM, classic)  -> scripts/run_main.py        (CPU)

Everything third-party lives in FOLDERS next to the project (and later
next to the single-file exe), never inside it:
  potentials/gpu/  — MACE weights (.pt/.model, indexed by the GUI)
  potentials/cpu/  — LAMMPS EAM/MEAM files
  lammps/          — lmp binary (download button, never bundled)

Run:  .venv-mace/Scripts/python.exe gui/server.py  (or python3 on Linux)
Then: http://127.0.0.1:8321  (auto-opens in the default browser)

Linux: identical, open-folder uses xdg-open, lmp download unpacks the
official linux tarball.
"""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import elements
import estimator
import potfile
import sysmetrics

# windowed (no-console) builds have no sys.stdout — keep prints harmless
if getattr(sys, 'stdout', None) is None:
    import io as _io
    sys.stdout = _io.StringIO()
    sys.stderr = _io.StringIO()

# Paths: source layout when running from the repo. A frozen exe keeps
# only its own code in the bundle and stores ALL data (venv, potentials,
# results, lammps) in a USER-CHOSEN app-root folder picked in the
# first-boot modal - never next to the exe, so a copy on the Desktop
# or in Downloads stays clean.
FROZEN = bool(getattr(sys, 'frozen', False))
if FROZEN:
    GUI_DIR = os.path.dirname(os.path.abspath(sys.executable))
    PROJ = GUI_DIR
    RESOURCE = getattr(sys, '_MEIPASS', GUI_DIR)   # bundled resources
else:
    GUI_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJ = os.path.dirname(GUI_DIR)
    RESOURCE = PROJ
# frozen: lmp_helper derives its root from __file__ (inside the bundle,
# i.e. the temp dir) — pin it to the real root NEXT TO the exe
if FROZEN:
    os.environ.setdefault('FEPT_PROJECT_DIR', PROJ)
# Windows: background helpers (nvidia-smi probes, pip, engine pipes)
# must never flash a console window; 0 = no-op elsewhere
NOWIN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
STATIC = os.path.join(GUI_DIR, 'static')
if not os.path.isdir(STATIC):
    STATIC = os.path.join(RESOURCE, 'gui', 'static')
SCRIPTS_DIR = os.path.join(RESOURCE, 'scripts')
sys.path.insert(0, SCRIPTS_DIR)
import lmpdata                                # noqa: E402  (scripts/)

PORT = int(os.environ.get('FEPT_PORT', 8321))
IS_WIN = os.name == 'nt'
LAMMPS_DIR = os.path.join(PROJ, 'lammps')
GPU_DIR = os.path.join(PROJ, 'potentials', 'gpu')
CPU_DIR = os.path.join(PROJ, 'potentials', 'cpu')
ELEMENTS_PATH = os.path.join(PROJ, 'data', 'elements.json')


# ---------------- app root (frozen first boot) ------------------------
APP_NAME = 'FePtMD'
BOOT = {'need_folder': False, 'phase': 'ready', 'pct': 0, 'line': '',
        'logs': [], 'error': '', 'root': '', 'default': ''}


def _approot_file():
    # The marker lives in %LOCALAPPDATA%, never next to the exe: a text
    # file beside it would litter whatever folder the user unpacked it
    # into (and would be unwritable under Program Files anyway).
    d = os.path.join(os.environ.get('LOCALAPPDATA') or
                     os.environ.get('APPDATA') or GUI_DIR, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'app_root.txt')


def load_app_root():
    path = _approot_file()
    try:
        with open(path, encoding='utf-8') as f:
            p = f.read().strip()
        if p:
            return p
    except OSError:
        pass
    # migrate the legacy copy that older builds wrote next to the exe
    legacy = os.path.join(GUI_DIR, 'app_root.txt')
    try:
        with open(legacy, encoding='utf-8') as f:
            p = f.read().strip()
    except OSError:
        return None
    if p:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(p)
        except OSError:
            pass
        try:
            os.unlink(legacy)   # remove the stray file from the exe folder
        except OSError:
            pass
    return p or None


def save_app_root(path):
    try:
        with open(_approot_file(), 'w', encoding='utf-8') as f:
            f.write(path)
    except OSError as e:
        log('[gui] cannot remember the app root: ' + str(e))


def default_app_root():
    d = (os.environ.get('LOCALAPPDATA') or
         os.path.expanduser('~') or '.')
    return os.path.join(d, APP_NAME)


def apply_app_root(root):
    # Point every data path at the chosen folder.
    global PROJ, LAMMPS_DIR, GPU_DIR, CPU_DIR, ELEMENTS_PATH
    PROJ = root
    LAMMPS_DIR = os.path.join(root, 'lammps')
    GPU_DIR = os.path.join(root, 'potentials', 'gpu')
    CPU_DIR = os.path.join(root, 'potentials', 'cpu')
    ELEMENTS_PATH = os.path.join(root, 'data', 'elements.json')
    os.environ['FEPT_PROJECT_DIR'] = root
    BOOT['root'] = root


if FROZEN:
    _saved_root = load_app_root()
    if _saved_root and os.path.isdir(_saved_root):
        apply_app_root(_saved_root)
    else:
        BOOT['need_folder'] = True
        BOOT['phase'] = 'need-folder'
        BOOT['default'] = default_app_root()
GH_API_LATEST = 'https://api.github.com/repos/lammps/lammps/releases/latest'
# ACEsuit foundation-model catalog (mace-mp / mace-foundations releases).
# Weights are fetched ON DEMAND into potentials/gpu/ - keeping ~1 GB of
# checkpoints locally for models nobody runs is pointless, so the GUI
# downloads any of them in one click through its own Python loader.
# Licenses: MIT (MP family) / ASL (OMAT, MATPES, MH) - not ours.
MODEL_URLS = {
    # MACE-MP-0 (1st generation, MPTrj, PBE+U)
    'mace-mp-0-small.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0/2023-12-10-mace-128-L0_epoch-199.model',
    'mace-mp-0-small-energy.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0/2023-12-10-mace-128-L0_energy_epoch-249.model',
    'mace-mp-0-medium.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0/2023-12-03-mace-128-L1_epoch-199.model',
    'mace-mp-0-large.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0/2024-01-07-mace-128-L2_epoch-199.model',
    'mace-mPtrj-2022.9.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0/MACE_MPtrj_2022.9.model',
    # MACE-MP-0b (2nd generation: core repulsion, stable MD)
    'mace-mp-0b-small.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0b/mace_agnesi_small.model',
    'mace-mp-0b-medium.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0b/mace_agnesi_medium.model',
    # MACE-MP-0b2 (high-pressure stability)
    'mace-mp-0b2-small.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0b2/mace-small-density-agnesi-stress.model',
    'mace-mp-0b2-medium.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0b2/mace-medium-density-agnesi-stress.model',
    'mace-large-0b2.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0b2/mace-large-density-agnesi-stress.model',
    # MACE-MP-0b3 (fixed phonons vs b2)
    'mace-mp-0b3-medium.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mp_0b3/mace-mp-0b3-medium.model',
    # MACE-MPA-0 (MPTrj + sAlex, SOTA Matbench)
    'mace-mpa-0-medium.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_mpa_0/mace-mpa-0-medium.model',
    # MACE-OMAT-0 (excellent phonons)
    'mace-omat-0-medium.model':
        'https://github.com/ACEsuit/mace-mp/releases/download/'
        'mace_omat_0/mace-omat-0-medium.model',
    'mace-omat-0-small.model':
        'https://github.com/ACEsuit/mace-foundations/releases/download/'
        'mace_omat_0/mace-omat-0-small.model',
    # MACE-MATPES (surrogate functionals)
    'mace-matpes-pbe-0-medium.model':
        'https://github.com/ACEsuit/mace-foundations/releases/download/'
        'mace_matpes_0/MACE-matpes-pbe-omat-ft.model',
    'mace-matpes-r2scan-0-medium.model':
        'https://github.com/ACEsuit/mace-foundations/releases/download/'
        'mace_matpes_0/MACE-matpes-r2scan-omat-ft.model',
    # MACE-MH (hybrid OMAT/OMOL/OC20/MATPES)
    'mace-mh-0.model':
        'https://github.com/ACEsuit/mace-foundations/releases/download/'
        'mace_mh_1/mace-mh-0.model',
    'mace-mh-1.model':
        'https://github.com/ACEsuit/mace-foundations/releases/download/'
        'mace_mh_1/mace-mh-1.model',
}

# (file, family, human label, MB) - drives the GUI download buttons
MODEL_CATALOG = [
    ('mace-mp-0-small.model', 'MP-0', 'MP-0 small (L0)', 32.6),
    ('mace-mp-0-small-energy.model', 'MP-0', 'MP-0 small, energy fit', 32.6),
    ('mace-mp-0-medium.model', 'MP-0', 'MP-0 medium (L1)', 44.4),
    ('mace-mp-0-large.model', 'MP-0', 'MP-0 large (L2)', 63.5),
    ('mace-mPtrj-2022.9.model', 'MP-0', 'MPtrj 2022.9 prototype', 133.8),
    ('mace-mp-0b-small.model', 'MP-0b', 'MP-0b small (agnesi)', 67.6),
    ('mace-mp-0b-medium.model', 'MP-0b', 'MP-0b medium (agnesi)', 79.4),
    ('mace-mp-0b2-small.model', 'MP-0b2', 'MP-0b2 small', 67.6),
    ('mace-mp-0b2-medium.model', 'MP-0b2', 'MP-0b2 medium', 79.5),
    ('mace-large-0b2.model', 'MP-0b2', 'MP-0b2 large', 98.5),
    ('mace-mp-0b3-medium.model', 'MP-0b3', 'MP-0b3 medium (fixed phonons)', 79.5),
    ('mace-mpa-0-medium.model', 'MPA-0', 'MPA-0 medium (MPTrj+sAlex)', 79.5),
    ('mace-omat-0-medium.model', 'OMAT-0', 'OMAT-0 medium (excellent phonons)', 79.5),
    ('mace-omat-0-small.model', 'OMAT-0', 'OMAT-0 small', 67.6),
    ('mace-matpes-pbe-0-medium.model', 'MATPES', 'MATPES-PBE medium (no +U)', 79.5),
    ('mace-matpes-r2scan-0-medium.model', 'MATPES', 'MATPES-r2SCAN medium', 79.5),
    ('mace-mh-0.model', 'MH', 'MH-0 hybrid (crystals+surfaces)', 39.9),
    ('mace-mh-1.model', 'MH', 'MH-1 hybrid', 59.2),
]

# Neural families ship weights through THEIR loader (sevenn / orb-models)
# instead of a raw URL: a tiny precache job pulls the weights once, so the
# first calculation does not stall on a silent multi-hundred-MB download.
PRECACHE = {'active': False}
PRECACHE_CMDS = {
    '7net-0': 'from sevenn.calculator import SevenNetCalculator; '
              'SevenNetCalculator(model="7net-0", device="cpu"); '
              'print("7net-0 weights cached")',
    '7net-omni-i12': 'from sevenn.calculator import SevenNetCalculator; '
                     'SevenNetCalculator(model="7net-omni-i12", '
                     'device="cpu"); print("7net-omni-i12 weights cached")',
    'orb-v3': 'from orb_models.forcefield.pretrained import '
              'orb_v3_conservative_20_omat; '
              'orb_v3_conservative_20_omat(device="cpu"); '
              'print("orb-v3 weights cached")',
}

# ----------------------------------------------------------------- state --
RUN = {
    'proc': None, 'lines': [], 'n': 0, 'running': False,
    'outdir': None, 'mode': None, 'start': 0.0,
    'state_n': 0, 'last_source': None,
    # live progress of the CURRENT run (points of the planned grid):
    'done_points': 0, 'plan_total': 0, 'last_exit': None,
}
COND = threading.Condition()
_DEPS_CACHE = {'t': 0.0, 'data': None}

# Shared form state: the browser edits it via UI, an agent edits it via
# MCP -> POST /api/form; every change bumps state_n so the open GUI
# visibly follows along (fields re-render with an agent pulse).
FORM = {
    'mode': 'mace', 'model': '', 'device': 'cuda',
    'precision': 'fp16',        # fp16 (default, recommended) | bf16 | fp32
    'comp': 0.5, 'grid': 4, 'temps': '300 1200',
    'eq': 500, 'prod': 1000, 'seed': 42,
    'elem_a': 'Fe', 'elem_b': 'Pt',
}
_PY_MISS_LOGGED = False
_PY_PICK_LOGGED = False


_KNOWN_PKGS = ('torch', 'mace', 'psutil', 'pandas', 'numpy',
              'ase', 'scipy', 'triton')


def _py_has_libs(py):
    # True when this interpreter site-packages already holds a known
    # project package: upgrades must pick the populated env, not an
    # empty one (otherwise 2-4 GB get re-downloaded).
    d = os.path.dirname(py)
    cands = [os.path.join(d, 'Lib', 'site-packages'),
             os.path.normpath(os.path.join(d, '..', 'lib',
                                           'site-packages'))]
    try:
        import glob as _g
        cands += _g.glob(os.path.join(d, 'lib', 'python*', 'site-packages'))
    except Exception:
        pass
    for sp in cands:
        if any(os.path.isdir(os.path.join(sp, k)) for k in _KNOWN_PKGS):
            return True
    return False


def _missing_modules(py, names):
    # Which of `names` the engine interpreter cannot import; empty on
    # any probe failure (never block on a flaky check).
    try:
        cp = subprocess.run(
            [py, '-c', 'import importlib.util as u, sys; '
                       'print(",".join(m for m in sys.argv[1:] '
                       'if not u.find_spec(m)))'] + list(names),
            capture_output=True, text=True, timeout=30,
            creationflags=NOWIN)
        if cp.returncode != 0:
            return []
        return [m for m in (cp.stdout or '').strip().split(',') if m]
    except Exception:
        return []


def resolve_python():
    """Interpreter that runs the engine scripts.

    Frozen builds must not use themselves (no torch/ase inside the exe):
    prefer $FEPT_PYTHON, then an external interpreter in <proj>/libs/."""
    envp = os.environ.get('FEPT_PYTHON')
    if envp:
        return envp
    if not FROZEN:
        return sys.executable
    # The engine python can live next to the exe (release layout), in
    # the directory the exe was started from, one level up (exe in
    # dist/) or in the project root - try ALL of them before giving up
    # (this used to return None -> "pip install numpy into None").
    roots = []
    for r in (PROJ, os.getcwd(), GUI_DIR, os.path.dirname(GUI_DIR)):
        r = os.path.abspath(r)
        if r not in roots:
            roots.append(r)
    rels = (('libs', 'venv', 'Scripts', 'python.exe'),
            ('libs', 'venv', 'bin', 'python'),
            ('libs', 'python.exe'),
            ('libs', 'python'),
            ('libs', 'python-dist', 'python.exe'),
            ('libs', 'python-dist', 'bin', 'python'),
            ('.venv-mace', 'Scripts', 'python.exe'),
            ('.venv-mace', 'bin', 'python'),
            ('venv', 'Scripts', 'python.exe'),
            ('venv', 'bin', 'python'))
    # Several envs can coexist after an upgrade (the old loader's libs/
    # plus a fresh .venv-mace): pick the one that actually HOLDS the
    # packages, otherwise an empty env wins and "old install invisible"
    # makes everyone re-download 2-4 GB.
    found = []
    for root in roots:
        for rel in rels:
            p = os.path.join(root, *rel)
            if os.path.isfile(p) and p not in found:
                found.append(p)
    global _PY_PICK_LOGGED
    for p in found:
        if _py_has_libs(p):
            if len(found) > 1 and not _PY_PICK_LOGGED:
                _PY_PICK_LOGGED = True
                log('[gui] engine python (of {} candidates): {}'.format(
                    len(found), p))
            return p
    if found:
        if not _PY_PICK_LOGGED:
            _PY_PICK_LOGGED = True
            log('[gui] engine python has NO packages yet: ' + found[0])
        return found[0]
    # one console line per launch, not one per deps poll (~15 s)
    global _PY_MISS_LOGGED
    if not _PY_MISS_LOGGED:
        _PY_MISS_LOGGED = True
        log('[gui] engine python NOT FOUND; searched: ' +
            '; '.join(roots) + ' (patterns: libs/, .venv-mace/, venv/)')
    # NEVER fall back to sys.executable when frozen: that IS this exe,
    # and spawning it with -c would start a second server (hangs deps).
    return None


def find_system_python():
    """An external interpreter 3.10..3.14 we could build a venv from.

    Clean machines have NO venv next to the exe, and some have no Python
    at all -> the caller then offers a python-build-standalone link.
    """
    tries = []
    envp = os.environ.get('FEPT_BASE_PYTHON')
    if envp:
        tries.append([envp])
    if IS_WIN:
        pyp = shutil.which('py')
        if pyp:
            tries.append([pyp, '-3'])
        p = shutil.which('python')
        if p:
            tries.append([p])
        # right after a .exe installer THIS process has an unchanged
        # PATH, so look in the default per-user install location too
        for g in sorted(glob.glob(os.path.join(
                os.environ.get('LOCALAPPDATA', ''),
                'Programs', 'Python', 'Python*', 'python.exe'))):
            tries.append([g])
    else:
        for name in ('python3', 'python'):
            p = shutil.which(name)
            if p:
                tries.append([p])
        tries.append(['/usr/bin/python3'])
    gate = ('import sys; v = sys.version_info; '
            'sys.exit(0 if (3, 10) <= v[:2] <= (3, 14) else 1)')
    for t in tries:
        try:
            r = subprocess.run(t + ['-c', gate], capture_output=True,
                               timeout=20, creationflags=NOWIN)
            if r.returncode == 0:
                return t[0]
        except Exception:
            continue
    return None


def ensure_engine_python():
    """(interpreter, need_url): the engine python, creating .venv-mace
    from a system Python on first use. need_url=True means nothing
    usable exists -> the deps tab must offer the Python-link block.
    """
    py = resolve_python()
    if py or not FROZEN:
        return py, False
    base = find_system_python()
    if not base:
        log('[gui] engine python NOT FOUND and no system Python 3.10-3.14')
        return None, True
    log('[gui] creating .venv-mace from ' + base)
    venv_dir = os.path.join(PROJ, '.venv-mace')
    try:
        r = subprocess.run([base, '-m', 'venv', venv_dir],
                           capture_output=True, text=True, timeout=300,
                           creationflags=NOWIN, cwd=PROJ)
        if r.returncode != 0:
            log('[gui] venv FAILED: ' + ((r.stderr or '')[-300:] or
                                         (r.stdout or '')[-300:]))
            log('[gui] this Python cannot make venvs (no ensurepip) -> '
                'install Python from a link in the deps tab')
            return None, True
    except Exception as e:
        log('[gui] venv error: ' + str(e))
        return None, True
    py = resolve_python()
    if py:
        log('[gui] venv ready: ' + py)
        return py, False
    return None, True


_PY_HINT = {'t': 0.0, 'url': ''}


def python_hint():
    """Newest python-build-standalone install-only tarball for THIS OS."""
    now = time.time()
    if _PY_HINT['url'] and now - _PY_HINT['t'] < 6 * 3600:
        return {'ok': True, 'url': _PY_HINT['url']}
    triple = ('x86_64-pc-windows-msvc-install_only.tar.gz' if IS_WIN else
              'x86_64-unknown-linux-gnu-install_only.tar.gz')
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/astral-sh/'
            'python-build-standalone/releases/latest',
            headers={'User-Agent': 'fept-gui/1.9',
                     'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            rel = json.loads(r.read())
        best = (None, (-1, -1, -1))
        # torch/mace wheels stop at the CPython the engine gates on
        # (3.10..3.14): a newer standalone python installs fine but
        # then 'torch from cu128' has NO wheel for it -> refuse to offer
        for a in rel.get('assets') or []:
            name = a.get('name') or ''
            if not name.endswith(triple) or 'debug' in name:
                continue
            # stable releases only: 'cpython-3.13.5+2025...'; prereleases
            # carry an a/b/rc marker ('cpython-3.16.0a1+...') and must
            # not be offered - they break mace/torch pins
            m = re.search(r'cpython-(\d+)\.(\d+)\.(\d+)\+', name)
            if not m:
                continue
            ver = tuple(int(x) for x in m.groups())
            if ver[0] != 3 or ver[1] < 10 or ver[1] > 14:
                continue  # engine/torch support window
            if ver > best[1]:
                best = (a.get('browser_download_url'), ver)
        if not best[0]:
            return {'ok': False, 'error': 'no asset for ' + triple}
        _PY_HINT.update(t=now, url=best[0])
        return {'ok': True, 'url': best[0]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _find_python_bin(root):
    """First python executable unpacked under root (or None)."""
    for dirpath, _dirs, files in os.walk(root):
        if dirpath[len(root):].count(os.sep) > 3:
            _dirs[:] = []
            continue
        for cand in ('python3', 'python3.exe', 'python', 'python.exe'):
            if cand in files:
                p = os.path.join(dirpath, cand)
                if os.path.isfile(p):
                    return p
    return None


def _safe_extract_tar(tf, stage):
    for m in tf.getmembers():
        first = (m.name or '').replace('\\', '/').split('/')[0]
        if not m.name or m.name.startswith('/') or ':' in first or \
                '..' in m.name.split('/'):
            raise RuntimeError('unsafe path in archive: ' + m.name)
    tf.extractall(stage)


def first_boot_engine():
    # Frozen exe start: make sure the engine env exists AND the LIGHT
    # stack is inside it, then set phase='ready'. (It used to return
    # early when a venv merely existed -> phase stayed 'setup' forever
    # and the UI never started: clicks did nothing.)
    if not resolve_python():
        log('[gui] no engine venv in the app folder - bootstrapping')
        py, need_url = ensure_engine_python()
        if not py:
            if need_url:
                log('[gui] no system Python 3.10-3.14 either -> paste a '
                    'Python link in the Deps tab (Python-установка) or '
                    'set FEPT_PYTHON')
            return
        log('[gui] engine venv is ready: ' + py)
    _boot_setup()


def _boot_setup():
    # First boot installs only the LIGHT stack into the chosen folder
    # (fast even on slow lines); torch/triton/mace/LAMMPS are on-demand
    # from the Deps tab - the tab blinks red until they are all present.
    steps = list(LIGHT_LIBS)

    def note(i, msg, total=len(steps) + 1):
        BOOT.update(pct=int(100.0 * i / total), phase='setup', line=msg)
        BOOT['logs'] = (BOOT.get('logs') or []) + [msg]
        del BOOT['logs'][:-40]
        log('[boot] ' + msg)

    try:
        note(0, 'создаю среду (.venv-mace) в ' + PROJ)
        py, need_url = ensure_engine_python()
        if not py:
            if need_url:
                note(1, 'нужен системный Python 3.10-3.14 - установи его и '
                        'нажми Повторить')
                BOOT.update(phase='error', error='no-python')
            else:
                BOOT.update(phase='error', error='venv-failed')
            return
        for i, name in enumerate(steps, start=1):
            note(i, 'устанавливаю ' + name + '...')
            install_lib(name)
        if resolve_python():
            BOOT.update(phase='ready', pct=100, line='готово')
            log('[boot] engine ready in ' + PROJ)
        else:
            BOOT.update(phase='error', error='engine-missing')
    except Exception as e:
        BOOT.update(phase='error', error=str(e))


def native_folder_dialog():
    # Visible Windows folder picker on the user's own desktop: the exe
    # has no tkinter, so use PowerShell + WinForms (always present).
    if not IS_WIN:
        return None
    ps = ('Add-Type -AssemblyName System.Windows.Forms; '
          '$d = New-Object System.Windows.Forms.FolderBrowserDialog; '
          '$d.Description = "Где хранить данные FePt MD '
          '(среда, потенциалы, результаты)"; '
          '$d.ShowNewFolderButton = $true; '
          'if ($d.ShowDialog() -eq '
          '[System.Windows.Forms.DialogResult]::OK) { $d.SelectedPath }')
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-STA', '-Command', ps],
            capture_output=True, text=True, timeout=600,
            creationflags=NOWIN)
        p = (r.stdout or '').strip()
        return p if p and os.path.isdir(p) else None
    except Exception as e:
        log('[gui] folder dialog failed: ' + str(e))
        return None


def install_python_job(url):
    """Download Python from a user link and turn it into .venv-mace so
    the deps tab becomes usable (python_hint() offers a known-good
    python-build-standalone URL to paste).
    """
    url = (url or '').strip()
    if not re.match(r'^https?://', url):
        dl_end('python: нужна http(s)-ссылка')
        return
    if DL['active']:
        dl_end('другая загрузка уже идёт')
        return
    fname = os.path.basename(url.split('?')[0]) or 'python-dist'
    cache = os.path.join(tempfile.gettempdir(), 'fept-python')
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, re.sub(r'[^A-Za-z0-9._+-]', '_', fname))
    try:
        if not (os.path.isfile(dest) and os.path.getsize(dest) > 1 << 20):
            download_url(url, dest, 'python dist', attempts=3)
        dl_begin('python install', mode='indeterminate')
        stage = os.path.join(cache, 'stage')
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage, exist_ok=True)
        if tarfile.is_tarfile(dest):
            with tarfile.open(dest, 'r:*') as tf:
                _safe_extract_tar(tf, stage)
        elif zipfile.is_zipfile(dest):
            with zipfile.ZipFile(dest) as zf:
                for zi in zf.infolist():
                    first = zi.filename.replace('\\', '/').split('/')[0]
                    if zi.filename.startswith('/') or '..' in zi.filename.split('/') or ':' in first:
                        raise RuntimeError('unsafe path in zip: ' + zi.filename)
                zf.extractall(stage)
        else:
            raise RuntimeError('не tar.gz и не zip: ' + fname)
        base = _find_python_bin(stage)
        if not base:
            raise RuntimeError('python executable not found inside ' + fname)
        if not IS_WIN:
            os.chmod(base, 0o755)
        venv_dir = os.path.join(PROJ, '.venv-mace')
        shutil.rmtree(venv_dir, ignore_errors=True)
        r = subprocess.run([base, '-m', 'venv', venv_dir],
                           capture_output=True, text=True, timeout=600,
                           creationflags=NOWIN, cwd=PROJ)
        if r.returncode != 0:
            raise RuntimeError('venv: ' + ((r.stderr or '')[-400:] or
                                           (r.stdout or '')[-400:]))
        py = resolve_python()
        if not py:
            raise RuntimeError('venv created but resolve_python missed it')
        gate = subprocess.run(
            [py, '-c', 'import sys; v = sys.version_info; '
                       'sys.exit(0 if (3, 10) <= v[:2] <= (3, 14) else 1)'],
            capture_output=True, timeout=30, creationflags=NOWIN)
        if gate.returncode != 0:
            ver = subprocess.run([py, '-c', 'import sys; print(*sys.version_info[:2])'],
                                 capture_output=True, text=True, timeout=30,
                                 creationflags=NOWIN).stdout.strip()
            shutil.rmtree(venv_dir, ignore_errors=True)
            raise RuntimeError(
                'python ' + ver + ' не подходит движку (нужен 3.10..3.14; '
                'под него есть torch/mace wheel) - возьми ссылку из кнопки '
                '"Подобрать"')
        log('[gui] python installed -> engine venv: ' + py)
        _DEPS_CACHE['t'] = 0.0
        dl_end('Python установлен: ' + py)
    except Exception as e:
        log('[gui] python install FAILED: ' + str(e))
        dl_end('python: ' + str(e))


_PROBE_CODE = (
    "import json, importlib.util as u\n"
    "d = {'torch': u.find_spec('torch') is not None,\n"
    "     'mace': u.find_spec('mace') is not None,\n"
    "     'ase': u.find_spec('ase') is not None,\n"
    "     'numpy': u.find_spec('numpy') is not None,\n"
    "     'scipy': u.find_spec('scipy') is not None,\n"
    "     'psutil': u.find_spec('psutil') is not None,\n"
    "     'pandas': u.find_spec('pandas') is not None}\n"
    "from importlib.metadata import version\n"
    "for k in ('numpy', 'scipy', 'pandas', 'psutil', 'ase', 'mace-torch'):\n"
    "    key = 'mace' if k == 'mace-torch' else k\n"
    "    if d.get(key):\n"
    "        try:\n"
    "            d[key + '_v'] = version(k)\n"
    "        except Exception:\n"
    "            pass\n"
    "if d['torch']:\n"
    "    try:\n"
    "        import torch\n"
    "        d['tv'] = torch.__version__\n"
    "        d['cuda_built'] = torch.version.cuda\n"
    "        d['cuda_ok'] = bool(torch.version.cuda) and torch.cuda.is_available()\n"
    "        if d['cuda_ok']:\n"
    "            d['gpu'] = torch.cuda.get_device_name(0)\n"
    "    except Exception as e:\n"
    "        d['terr'] = str(e)[:300]\n"
    "d['triton'] = u.find_spec('triton') is not None\n"
    "if d['triton']:\n"
    "    from importlib.metadata import version as _v\n"
    "    for _pkg in ('triton-windows', 'triton'):\n"
    "        try:\n"
    "            d['triton_v'] = v if (v := _v(_pkg)) else ''\n"
    "            break\n"
    "        except Exception:\n"
    "            pass\n"
    "    import triton as _t, os as _o\n"
    "    _b = _o.path.join(_o.path.dirname(_t.__file__), 'backends')\n"
    "    _found = ''\n"
    "    if _o.path.isdir(_b):\n"
    "        for _r, _d, _f in _o.walk(_b):\n"
    "            for _x in _f:\n"
    "                if _x.startswith('ptxas'):\n"
    "                    _found = _o.path.join(_r, _x)\n"
    "                    break\n"
    "            if _found:\n"
    "                break\n"
    "    d['ptxas'] = _found\n"
    "print('PROBE_JSON:' + json.dumps(d))\n"
)


def _probe_libs(python_bin):
    """Probe heavy libs INSIDE the engine interpreter (subprocess).

    Keeps torch/ase/mace as static imports out of the exe bundle and
    makes the deps tab truthful for frozen builds (external venv)."""
    if not python_bin:
        return {'error': 'no engine interpreter (set FEPT_PYTHON or '
                         'create libs/venv next to the exe)'}
    if FROZEN and os.path.abspath(python_bin) == os.path.abspath(sys.executable):
        # would re-launch this very executable (-c is not ours) -> hang.
        # Only frozen: in dev mode sys.executable IS the engine python.
        return {'error': 'engine interpreter resolves to the GUI itself; '
                         'set FEPT_PYTHON to an external python'}
    try:
        cp = subprocess.run([python_bin, '-c', _PROBE_CODE],
                            creationflags=NOWIN,
                            capture_output=True, timeout=180)
        text = (cp.stdout or b'').decode('utf-8', errors='replace')
        for line in text.splitlines():
            if line.startswith('PROBE_JSON:'):
                return json.loads(line[11:])
        return {'error': (cp.stderr or b'').decode('utf-8',
                                                  'replace')[-300:]}
    except Exception as e:
        return {'error': str(e)[:300]}


FORM_KEYS = ('mode', 'model', 'device', 'precision', 'comp', 'grid', 'temps',
             'eq', 'prod',
             'seed', 'elem_a', 'elem_b')


def build_estimate(form):
    """Estimate payload for a form dict (GET shows FORM; POST may override)."""
    prof = estimator.load_profile()
    est = estimator.estimate(
        prof,
        form.get('mode', 'mace'), form.get('device', 'cuda'),
        int(form.get('grid', 4)), str(form.get('temps', '')),
        int(form.get('eq', 500)), int(form.get('prod', 1000)),
        precision=form.get('precision', 'fp16'))
    want_vram = (form.get('mode') == 'mace'
                 and form.get('device') == 'cuda')
    total_vram = sysmetrics.gpu_info().get('vram_total_mb')
    est['fits'] = estimator.fits_memory(
        est['vram_mb'] if want_vram else None, total_vram)
    est['ram_total_mb'] = sysmetrics.ram_info().get('total_mb')
    # machine profile tab: the raw calibration points behind the estimate
    est['profile'] = {'points': prof.get('points', []),
                      'overhead': prof.get('overhead'),
                      'calibrated_at': prof.get('calibrated_at')}
    # "how many atoms still fit this card" (None until 2 calibration points)
    est['max_atoms'] = estimator.max_atoms_for_vram(
        prof, total_vram, form.get('mode', 'mace'),
        form.get('device', 'cuda'))
    return est


def state_update(diff, source=None):
    """Merge form changes; log every agent touch into the console."""
    clean = {}
    for key in FORM_KEYS:
        if key in diff and diff[key] is not None and diff[key] != FORM[key]:
            clean[key] = diff[key]
    if not clean:
        return
    with COND:
        FORM.update(clean)
        RUN['state_n'] += 1
        RUN['last_source'] = source
        COND.notify_all()
    if source == 'agent':
        for k, v in clean.items():
            log('[agent] {} <- {}'.format(k, v))


def log(line):
    with COND:
        RUN['lines'].append(line.rstrip('\n'))
        RUN['n'] += 1
        if len(RUN['lines']) > 50000:
            del RUN['lines'][:10000]
        COND.notify_all()


# ------------------------------------------------------------- helpers --
def scan_potentials():
    def lst(folder, exts):
        out = []
        if os.path.isdir(folder):
            for fn in sorted(os.listdir(folder)):
                if any(fn.lower().endswith(e) for e in exts):
                    p = os.path.join(folder, fn)
                    out.append({'name': fn, 'path': p,
                                'mb': round(os.path.getsize(p) / 1e6, 1)})
        return out
    return {
        'gpu': lst(GPU_DIR, ('.pt', '.model')),
        'cpu': lst(CPU_DIR, ('.eam', '.meam', '.alloy', '.fs')),
    }


def find_lmp():
    """Locate lmp via the project helper (lammps/ first, then bin/, PATH)."""
    try:
        import lmp_helper
        return lmp_helper.find_lmp_display()
    except Exception:
        return None


def engine_py_ver(py):
    # one cheap 'python -V' subprocess - collect_deps caches this
    try:
        return subprocess.run([py, '-V'], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception:
        return ''


def collect_deps(refresh=False):
    now = time.time()
    if not refresh and _DEPS_CACHE['data'] and now - _DEPS_CACHE['t'] < 120:
        return _DEPS_CACHE['data']

    # Heavy libs (torch/mace/ase) live in the ENGINE interpreter — an
    # external venv for frozen builds — so probe them THERE via a
    # subprocess. This also keeps torch out of the PyInstaller bundle.
    eng = resolve_python()
    probe = _probe_libs(eng)
    torch_info = {'installed': probe.get('torch', False)}
    if torch_info['installed']:
        torch_info['version'] = probe.get('tv')
        torch_info['cuda_available'] = probe.get('cuda_ok', False)
        cuda_built = probe.get('cuda_built')
        if torch_info['cuda_available']:
            torch_info['device'] = probe.get('gpu')
            torch_info['cuda'] = cuda_built
        else:
            torch_info['cuda'] = (
                'CPU-only wheel' if cuda_built is None else
                'CUDA {} built, not usable'.format(cuda_built))
        if probe.get('terr'):
            torch_info['error'] = probe['terr']

    lammps = find_lmp()
    engine_py = resolve_python()
    data = {
        'python': sys.version.split()[0],
        'no_engine_python': engine_py is None,
        'python_system': (find_system_python() if engine_py is None
                          else None),
        'executable': sys.executable,
        'engine_python': resolve_python(),
        'frozen': FROZEN,
        'project': PROJ,
        'platform': '{} {} ({})'.format(platform.system(),
                                        platform.release(), platform.machine()),
        'libs': {
            'torch': torch_info,
            'mace': probe.get('mace', False),
            'mace_v': probe.get('mace_v'),
            'ase': probe.get('ase', False),
            'ase_v': probe.get('ase_v'),
            'numpy': probe.get('numpy', False),
            'numpy_v': probe.get('numpy_v'),
            'scipy': probe.get('scipy', False),
            'scipy_v': probe.get('scipy_v'),
            'pandas': probe.get('pandas', False),
            'pandas_v': probe.get('pandas_v'),
            'psutil': probe.get('psutil', False),
            'psutil_v': probe.get('psutil_v'),
            'triton': probe.get('triton', False),
            'triton_v': probe.get('triton_v'),
            'ptxas': probe.get('ptxas'),
            'probe_error': probe.get('error'),
        },
        'lammps': {'found': bool(lammps), 'path': lammps},
        # folder that opens the bundled python (venv root) in explorer
        'python_dir': (os.path.dirname(os.path.dirname(_py))
                       if (_py := resolve_python()) else None),
        'potentials': scan_potentials(),
        # on-demand model catalog: name/label/size for the download
        # buttons (weights themselves are NOT kept locally)
        'models': [{'name': n, 'family': fam, 'label': lab, 'mb': mb,
                    'url': MODEL_URLS.get(n, '')}
                   for (n, fam, lab, mb) in MODEL_CATALOG
                   if n not in [p.get('name')
                                for p in scan_potentials().get('gpu', [])]],
        'catalog_names': [n for (n, _f, _l, _m) in MODEL_CATALOG],
        'folders': {'gpu': GPU_DIR, 'cpu': CPU_DIR, 'lammps': LAMMPS_DIR},
        # ---- fast component state + mirrors + proxy (deps tab) ----
        'components': engine_component_state(),
        'heavy': list(HEAVY_LIBS),
        'light': list(LIGHT_LIBS),
        'python_links': list(PYTHON_LINKS),
        'lammps_links': list(LAMMPS_LINKS),
        'proxy': proxy_summary(),
        'manifest_at': manifest_load().get('updated_at', ''),
        'engine_python_version': (engine_py_ver(engine_py)
                                  if engine_py else ''),
    }
    _DEPS_CACHE['t'] = now
    _DEPS_CACHE['data'] = data
    return data


def parse_csv(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        header = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(';')]
            if header is None:
                header = parts
                continue
            rows.append(dict(zip(header, parts)))
    return rows


# --------------------- multi-run averaging --------------------------------
MULTI = {'total': 0, 'left': 0, 'dirs': [], 'params': None}


def average_runs(dirs):
    """Mean over several independent runs -> one NEW results dir.

    Every leg keeps its own outdir (runs saved separately); this builds
    the aggregate all_results.csv / cte_report.csv so the normal
    /api/results path renders the averaged numbers unchanged, and
    meta.json marks the dir type=average for the UI badge.
    """
    import csv as _csv
    runs = [d for d in dirs if d and os.path.isfile(
        os.path.join(d, 'all_results.csv'))]
    if len(runs) < 2:
        raise RuntimeError('need >=2 runs with all_results.csv, got {}'
                           .format(len(runs)))

    def merge_rows(files, group_keys):
        """Mean of numeric columns per group; a_std pooled across runs."""
        grouped, order, headers = {}, [], None
        for path in files:
            hdr = None
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split(';')]
                    if hdr is None:
                        hdr = parts
                        if headers is None:
                            headers = list(parts)
                        continue
                    row = dict(zip(hdr, parts))
                    key = tuple(row.get(k, '') for k in group_keys)
                    grouped.setdefault(key, []).append(row)
                    if key not in order:
                        order.append(key)
        out_rows = []
        for key in order:
            samples = grouped[key]
            res = dict(zip(group_keys, key))
            for col in headers:
                if col in group_keys:
                    continue
                vals = []
                ok = True
                for row in samples:
                    try:
                        vals.append(float(str(row.get(col, ''))
                                          .replace(',', '.')))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok or not vals:
                    res[col] = samples[0].get(col, '')
                    continue
                mean = sum(vals) / len(vals)
                if col.startswith('a_std'):
                    # pooled scatter: within-run (std_i^2) + between-run
                    # variance of the per-run MEANS (a_mean_Angstrom),
                    # not of the std column itself
                    var = sum(s * s for s in vals) / len(vals)
                    means = []
                    for row in samples:
                        try:
                            means.append(float(str(
                                row.get('a_mean_Angstrom', '')
                                .replace(',', '.'))))
                        except (TypeError, ValueError):
                            means = []
                            break
                    if len(means) >= 2:
                        gm = sum(means) / len(means)
                        var += sum((m - gm) ** 2 for m in means) / len(means)
                    res[col] = '{:.6f}'.format(var ** 0.5)
                else:
                    res[col] = '{:.6g}'.format(mean)
            res['runs_n'] = str(len(samples))
            out_rows.append(res)
        return list(headers) + ['runs_n'], out_rows

    stamp = time.strftime('%Y%m%d_%H%M%S')
    avg_dir = os.path.join(PROJ, 'results_avg_{}'.format(stamp))
    os.makedirs(avg_dir, exist_ok=True)

    a_hdr, a_rows = merge_rows(
        [os.path.join(d, 'all_results.csv') for d in runs],
        ('x_Pt', 'T_K'))
    with open(os.path.join(avg_dir, 'all_results.csv'), 'w',
              newline='', encoding='utf-8') as f:
        w = _csv.DictWriter(f, fieldnames=a_hdr, delimiter=';')
        w.writeheader()
        w.writerows(a_rows)

    cte_files = [os.path.join(d, 'cte_report.csv') for d in runs
                 if os.path.isfile(os.path.join(d, 'cte_report.csv'))]
    if cte_files:
        c_hdr, c_rows = merge_rows(cte_files, ('x_Pt',))
        with open(os.path.join(avg_dir, 'cte_report.csv'), 'w',
                  newline='', encoding='utf-8') as f:
            w = _csv.DictWriter(f, fieldnames=c_hdr, delimiter=';')
            w.writeheader()
            w.writerows(c_rows)

    import json as _json
    with open(os.path.join(avg_dir, 'meta.json'), 'w',
              encoding='utf-8') as f:
        _json.dump({'type': 'average', 'runs_n': len(runs),
                    'runs': list(runs),
                    'created_at': time.strftime('%Y-%m-%d %H:%M:%S')},
                   f, ensure_ascii=False, indent=1)
    return avg_dir


def finish_multi():
    """Last leg done: average every run and report the means in the log."""
    dirs = list(MULTI.get('dirs') or [])
    MULTI.update(total=0, left=0, dirs=[], params=None)
    if len(dirs) < 2:
        return
    log('[gui] === all {} runs finished — averaging in ~2 s...'
        .format(len(dirs)))
    time.sleep(2)
    try:
        avg_dir = average_runs(dirs)
    except Exception as e:
        log('[gui] averaging failed: ' + str(e))
        return
    RUN['outdir'] = avg_dir
    RUN['multi_done'] = {'runs': dirs, 'avg': avg_dir}
    log('[gui] === MEAN over {} runs: --> {}'
        .format(len(dirs), avg_dir))
    try:
        for row in parse_csv(os.path.join(avg_dir, 'all_results.csv')):
            log('[gui] MEAN  x_Pt={} T={}K  a={} +- {} A'
                .format(row.get('x_Pt'), row.get('T_K'),
                        row.get('a_mean_Angstrom'),
                        row.get('a_std_Angstrom')))
        for row in parse_csv(os.path.join(avg_dir, 'cte_report.csv')):
            keys = ('CTE_fit', 'alpha_fit')
            hit = [(k, row.get(k)) for k in keys if row.get(k)]
            if hit:
                log('[gui] MEAN  x_Pt={}  CTE={} /K ({})'
                    .format(row.get('x_Pt'), hit[0][1], hit[0][0]))
    except Exception as e:
        log('[gui] mean summary skipped: ' + str(e))


def collect_results(outdir):
    """all_results + cte_report of one run dir -> chart-ready JSON."""
    all_path = os.path.join(outdir, 'all_results.csv')
    cte_path = os.path.join(outdir, 'cte_report.csv')
    rows = parse_csv(all_path)
    cte_rows = parse_csv(cte_path)

    def f(row, key):
        try:
            return float(row[key])
        except Exception:
            return None

    series = {}
    for row in rows:
        comp = f(row, 'x_Pt')
        temp = f(row, 'T_K')
        a = f(row, 'a_mean_Angstrom')
        std = f(row, 'a_std_Angstrom')
        if comp is None or temp is None or a is None:
            continue
        series.setdefault(str(comp), []).append({
            'T': temp, 'a': a, 'std': std or 0.0,
            'runtime': f(row, 'runtime_s'),
            'drift': f(row, 'drift'),
        })
    for key in series:
        series[key].sort(key=lambda d: d['T'])

    cte = []
    for row in cte_rows:
        # Two CTE formats exist: quick mode writes
        #   x_Pt;a_300K;a_maxT;dA;CTE_fit;CTE_chordal;CTE_300_1200;R2;n_points
        # full mode writes
        #   x_Pt;R_squared;alpha_2pt;alpha_fit;alpha_min;...;seg_900_1200
        if 'CTE_fit' in row:
            fit = f(row, 'CTE_fit')
            entry = {
                'x_Pt': f(row, 'x_Pt'),
                'alpha_fit': fit,
                'alpha_min': f(row, 'CTE_chordal') if fit is not None else None,
                'alpha_max': f(row, 'CTE_300_1200') if fit is not None else None,
                'R2': f(row, 'R2'),
                # segmental CTE columns are appended by write_cte_full
                # when the grid has >= 2 segments (legacy reports: None)
                'seg_300_600': f(row, 'seg_300_600'),
                'seg_600_900': f(row, 'seg_600_900'),
                'seg_900_1200': f(row, 'seg_900_1200'),
            }
        else:
            entry = {
                'x_Pt': f(row, 'x_Pt'),
                'alpha_fit': f(row, 'alpha_fit'),
                'alpha_min': f(row, 'alpha_min'),
                'alpha_max': f(row, 'alpha_max'),
                'R2': f(row, 'R_squared'),
                'seg_300_600': f(row, 'seg_300_600'),
                'seg_600_900': f(row, 'seg_600_900'),
                'seg_900_1200': f(row, 'seg_900_1200'),
            }
        cte.append(entry)
    cte.sort(key=lambda d: d['x_Pt'] if d['x_Pt'] is not None else 0)
    return {
        'outdir': os.path.abspath(outdir),
        'series': series,
        'cte': cte,
        'files': sorted(os.listdir(outdir)) if os.path.isdir(outdir) else [],
        'mtime': os.path.getmtime(all_path) if os.path.isfile(all_path)
                 else None,
    }


# ------------------------------------------------- xlsx export/import --
def _current_outdir():
    """The run folder the Results tab shows: RUN's own one, else the
    newest folder holding all_results.csv, else a default path."""
    outdir = RUN.get('outdir')
    if outdir:
        return outdir
    best, best_t = None, 0.0
    try:
        names = os.listdir(PROJ)
    except OSError:
        names = []
    for name in names:
        cand = os.path.join(PROJ, name)
        csvf = os.path.join(cand, 'all_results.csv')
        if os.path.isfile(csvf):
            t = os.path.getmtime(csvf)
            if t > best_t:
                best, best_t = cand, t
    return best or os.path.join(PROJ, 'results_mace')


def _write_export_xlsx(payload):
    """Excel package: sheet 1 = the data table (per-point series and
    the CTE report), sheet 2 = every chart/histogram the GUI renders,
    embedded as PNG images with captions."""
    import base64
    from io import BytesIO
    from openpyxl import Workbook, load_workbook  # noqa: F401
    from openpyxl.drawing.image import Image as XlImage
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    series = payload.get('series') or {}
    cte = payload.get('cte') or []
    meta = payload.get('meta') or {}

    wb = Workbook()
    ws = wb.active
    ws.title = 'Данные'
    ws['A1'] = 'Fe-Pt results' + (
        '  (seed={})'.format(meta.get('form', {}).get('seed'))
        if isinstance(meta.get('form'), dict)
        and meta.get('form', {}).get('seed') is not None else '')
    ws['A1'].font = Font(bold=True, size=12)
    head = ['x_Pt', 'T_K', 'a_mean_Angstrom', 'a_std_Angstrom',
            'drift', 'runtime_s']
    hrow = 3
    for ci, h in enumerate(head, 1):
        c = ws.cell(row=hrow, column=ci, value=h)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal='center')
    row = hrow + 1
    for key in sorted(series, key=lambda s: float(s)):
        for d in series[key]:
            ws.cell(row=row, column=1, value=float(key))
            ws.cell(row=row, column=2, value=d.get('T'))
            ws.cell(row=row, column=3, value=d.get('a'))
            ws.cell(row=row, column=4, value=d.get('std'))
            ws.cell(row=row, column=5, value=d.get('drift'))
            ws.cell(row=row, column=6, value=d.get('runtime'))
            row += 1
    if cte:
        row += 2
        ws.cell(row=row, column=1,
                value='CTE report').font = Font(bold=True)
        row += 1
        chead = ['x_Pt', 'alpha_2pt', 'alpha_fit', 'alpha_min', 'alpha_max',
                 'alpha_range', 'R2', 'seg_300_600', 'seg_600_900',
                 'seg_900_1200']
        for ci, h in enumerate(chead, 1):
            ws.cell(row=row, column=ci, value=h).font = Font(bold=True)
        row += 1
        for c in cte:
            r2 = c.get('R2') if c.get('R2') is not None else c.get('R_squared')
            vals = [c.get('x_Pt'), c.get('alpha_2pt'), c.get('alpha_fit'),
                    c.get('alpha_min'), c.get('alpha_max'),
                    c.get('alpha_range'), r2, c.get('seg_300_600'),
                    c.get('seg_600_900'), c.get('seg_900_1200')]
            for ci, v in enumerate(vals, 1):
                ws.cell(row=row, column=ci, value=v)
            row += 1
    for ci, w in enumerate((11, 11, 17, 17, 14, 12, 10, 13, 13, 13), 1):
        ws.column_dimensions[get_column_letter(ci)].width = w

    # ---- sheet 2: every chart from the GUI -------------------------
    ws2 = wb.create_sheet('Графики')
    r0 = 1
    placed = 0
    for img in (payload.get('images') or []):
        name = str(img.get('name') or 'график')[:80]
        try:
            raw = base64.b64decode(img.get('png') or '')
            if len(raw) < 100:
                continue
            xl = XlImage(BytesIO(raw))
        except Exception:
            continue
        ws2.cell(row=r0, column=1, value=name).font = Font(bold=True)
        r0 += 1
        try:
            ws2.add_image(xl, 'A{}'.format(r0))
        except Exception:
            continue
        placed += 1
        r0 += max(20, int(getattr(xl, 'height', 400) / 20) + 2)
    if not placed:
        ws2['A1'] = 'графики не приложены'

    outdir = _current_outdir()
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError:
        pass
    dest = os.path.join(outdir, 'fept_export.xlsx')
    try:
        wb.save(dest)
    except PermissionError:
        # the previous export is open in Excel — write next to it instead
        # of failing, so a second export always produces a file
        stamp = time.strftime('%Y%m%d_%H%M%S')
        dest = os.path.join(outdir, 'fept_export_%s.xlsx' % stamp)
        wb.save(dest)
    return dest


def _compute_cte(series):
    """CTE rows built from bare series data (imported files carry no
    cte_report.csv): linear fit a(T) per composition plus the chordal,
    segmental and range values the charts/summary expect."""
    out = []
    for key in sorted(series, key=lambda s: float(s)):
        pts = sorted(series[key], key=lambda d: d.get('T') or 0)
        if len(pts) < 2:
            continue
        xs = [float(d['T']) for d in pts]
        ys = [float(d['a']) for d in pts]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        slope = sxy / sxx if sxx else 0.0
        inter = my - slope * mx
        ss_res = sum((y - (slope * x + inter)) ** 2 for x, y in zip(xs, ys))
        ss_tot = sum((y - my) ** 2 for y in ys) or 1e-30
        r2 = 1.0 - ss_res / ss_tot
        alpha_fit = slope / my if my else 0.0
        a2pt = ((ys[-1] - ys[0]) / (ys[0] * (xs[-1] - xs[0]))
                if xs[-1] != xs[0] and ys[0] else 0.0)
        inst = []
        for i in range(1, n):
            dt = xs[i] - xs[i - 1]
            if dt and ys[i - 1]:
                inst.append((ys[i] - ys[i - 1]) / (ys[i - 1] * dt))
        amin = min(inst) if inst else 0.0
        amax = max(inst) if inst else 0.0

        def seg(t0, t1):
            idx = [i for i in range(n) if t0 <= xs[i] <= t1]
            if len(idx) < 2:
                return None
            i0, i1 = idx[0], idx[-1]
            dt = xs[i1] - xs[i0]
            if not dt or not ys[i0]:
                return None
            return (ys[i1] - ys[i0]) / (ys[i0] * dt)

        out.append({
            'x_Pt': float(key),
            'alpha_2pt': a2pt,
            'alpha_fit': alpha_fit,
            'alpha_min': amin,
            'alpha_max': amax,
            'alpha_range': amax - amin,
            'R2': r2,
            'seg_300_600': seg(300, 600),
            'seg_600_900': seg(600, 900),
            'seg_900_1200': seg(900, 1200),
        })
    return out


def _parse_results_upload(name, raw):
    """Uploaded .xlsx / .csv / .txt -> series dict. Accepts our own
    export sheet (x_Pt,T_K,a_mean...) and the all_results.csv layout;
    any delimited text with those columns works too."""
    import csv as _csv
    from io import StringIO
    low = (name or '').lower()
    rows = []
    if low.endswith(('.xlsx', '.xlsm')):
        from io import BytesIO
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                hdr_i, head = None, None
                for i, r in enumerate(ws.iter_rows(values_only=True), 1):
                    vals = [str(v).strip().lower()
                            if v is not None else '' for v in r]
                    if 'x_pt' in vals and 't_k' in vals:
                        hdr_i, head = i, vals
                        break
                if head:
                    for r in ws.iter_rows(min_row=hdr_i + 1,
                                          values_only=True):
                        rows.append(dict(zip(head, r)))
                    break
        finally:
            wb.close()
        if not rows:
            raise ValueError(
                'в книге не найдена таблица с колонками x_Pt / T_K '
                '(или после заголовка нет ни одной строки данных)')
    else:
        text = raw.decode('utf-8-sig', errors='replace')
        first = text.splitlines()[0] if text else ''
        delim = ';' if first.count(';') >= first.count(',') else ','
        rdr = _csv.DictReader(StringIO(text), delimiter=delim)
        rows = [{(k or '').strip().lower(): v for k, v in r.items()}
                for r in rdr]

    def pick(r, *names):
        for n in names:
            if n in r and r[n] not in (None, ''):
                try:
                    return float(r[n])
                except (TypeError, ValueError):
                    return None
        return None

    series = {}
    for r in rows:
        comp = pick(r, 'x_pt', 'x(pt)', 'x', 'comp')
        temp = pick(r, 't_k', 't(k)', 't', 'temp')
        a = pick(r, 'a_mean_angstrom', 'a_mean', 'a_mean_a', 'a')
        if comp is None or temp is None or a is None:
            continue
        series.setdefault(str(comp), []).append({
            'T': temp, 'a': a,
            'std': pick(r, 'a_std_angstrom', 'a_std', 'std', 'sigma') or 0.0,
            'runtime': pick(r, 'runtime_s', 'runtime'),
            'drift': pick(r, 'drift'),
        })
    if not series:
        raise ValueError('не найдены колонки x_Pt / T_K / a_mean')
    for k in series:
        series[k].sort(key=lambda d: d['T'])
    return series


# --------------------------------------------------------------- runners --
def available_memory_bytes():
    """PhysMem available (Windows GlobalMemoryStatusEx, POSIX sysinfo)."""
    try:
        if IS_WIN:
            import ctypes
            class _M(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _M()
            m.dwLength = ctypes.sizeof(_M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullAvailPhys
        # POSIX
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def stop_run():
    proc = RUN.get('proc')
    if proc and proc.poll() is None:
        log('[gui] stop requested')
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def start_run(params):
    if RUN.get('running') and RUN['proc'] and RUN['proc'].poll() is None:
        return {'ok': False, 'error': 'run already in progress'}
    try:
        leg_count = max(1, min(20, int(params.get('run_count') or 1)))
    except (TypeError, ValueError):
        leg_count = 1
    from_multi = str(params.get('source') or '') == 'multi'
    # form first (what the GUI shows), request wins (browser/MCP explicit)
    merged = dict(FORM)
    merged.update({k: v for k, v in params.items()
                   if k in FORM_KEYS and v is not None})
    state_update(merged, source=params.get('source'))
    mode = merged.get('mode', 'mace')
    comp = float(merged.get('comp', 0.5))
    grid = int(merged.get('grid', 4))
    eq = int(merged.get('eq', 500))
    prod = int(merged.get('prod', 1000))
    temps = [int(t) for t in str(merged.get('temps', '300 1200')).split()]
    RUN['done_points'] = 0
    RUN['plan_total'] = len(temps)  # one composition per run
    RUN['compile_off'] = False
    stamp = time.strftime('%Y%m%d_%H%M%S')
    outdir = os.path.join(PROJ, 'results_{}_{}'.format(mode, stamp))
    py = resolve_python()
    if not py:
        return {'ok': False,
                'error': 'no engine python found: set FEPT_PYTHON or '
                         'place an interpreter in libs/ (see Dependencies)'}
    # preflight: an unprepared engine would die with "exit 1" in 0.2 s
    # (ModuleNotFoundError) - say exactly WHAT is missing instead
    missing = _missing_modules(py, ('numpy', 'ase', 'torch', 'mace'))
    if missing:
        return {'ok': False,
                'error': 'в движке нет ' + ', '.join(missing) +
                         ' — вкладка Зависимости → Установить, '
                         'затем запусти снова'}
    if mode == 'mace':
        cmd = [py, '-u',
               os.path.join(SCRIPTS_DIR, 'run_main_mace.py')]
        model = merged.get('model')
        if model and not os.path.isfile(model):
            # accept a bare filename too: resolve it inside the gpu
            # folder (agents/UI may send 'mace-mp-0-small.model')
            cand = os.path.join(GPU_DIR, model)
            if os.path.isfile(cand):
                model = cand
                state_update({'model': model}, source=params.get('source'))
        if not model:
            pot = scan_potentials()['gpu']
            if pot:
                model = pot[0]['path']
                state_update({'model': model}, source=params.get('source'))
        if not model or (not str(model).startswith(('sevennet', '7net', 'orb'))
                        and not os.path.isfile(model)):
            return {'ok': False,
                    'error': 'no model selected (download one on the Models tab first)'}
        device = merged.get('device', 'cuda')
        seed = int(merged.get('seed', 42))
        precision = str(merged.get('precision') or 'fp16').lower()
        if precision not in ('fp16', 'bf16', 'fp32'):
            precision = 'fp16'
        cmd += ['--device', device, '--model', model,
                '--precision', precision,
                '--comps', str(comp), '--temps'] + [str(t) for t in temps] + \
               ['--grid', str(grid), '--eq', str(eq), '--prod', str(prod),
                '--seed', str(seed), '--out', outdir]
        if not compile_enabled():
            cmd.append('--no-compile')
            log('[gui] torch.compile OFF for this run (default; '
                'FEPT_COMPILE=1 opts back in where triton works)')
    elif mode == 'lammps':
        cmd = [resolve_python(), '-u',
               os.path.join(SCRIPTS_DIR, 'run_main.py'),
               '--comps', str(comp),
               '--temps', ' '.join(str(t) for t in temps),
               '--grid', str(grid), '--eq', str(eq), '--prod', str(prod),
               '--out', outdir]
    else:
        return {'ok': False, 'error': 'unknown mode ' + mode}

    src = (params.get('source') or 'ui').upper()
    log('[{}] === start {} mode | comp={} grid={} eq={} prod={} T={}'
        .format(src, mode, comp, grid, eq, prod, temps))
    log('[gui] out: ' + outdir)
    try:
        os.makedirs(outdir, exist_ok=True)
        import json as _json
        import time as _time
        with open(os.path.join(outdir, 'meta.json'), 'w',
                  encoding='utf-8') as _mf:
            _json.dump({'started_at': _time.strftime('%Y-%m-%d %H:%M:%S'),
                        'outdir': outdir,
                        'form': dict(FORM)}, _mf, ensure_ascii=False,
                       indent=1)
    except Exception as _e:
        log('[gui] meta.json skipped: %s' % _e)
    log('[gui] cmd: ' + ' '.join(os.path.basename(c) for c in cmd[1:2]) +
        ' ' + ' '.join(cmd[2:]))

    env = dict(os.environ)
    # torch 2.6: e3nn constants need legacy unpickling (see run_main_mace)
    env.setdefault('TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD', '1')
    # OpenBLAS/OMP: bound threads (big buffers are what fails first on a
    # low-memory box; MACE runs on CUDA anyway)
    env.setdefault('OPENBLAS_NUM_THREADS', '4')
    env.setdefault('OMP_NUM_THREADS', '4')
    env.setdefault('MKL_NUM_THREADS', '4')
    # external root for the engine: potentials/, lammps/, data/ live NEXT
    # TO the exe in frozen builds (lmp_helper reads FEPT_PROJECT_DIR)
    env['FEPT_PROJECT_DIR'] = PROJ
    avail = available_memory_bytes()
    if avail:
        gb = avail / 1e9
        log('[gui] free memory before run: {:.1f} GB'.format(gb))
        if gb < 1.0:
            return {'ok': False,
                    'error': 'free RAM only {:.1f} GB — close heavy apps '
                             '(MC java, Roblox, games) and retry'.format(gb)}
    try:
        proc = subprocess.Popen(
            cmd, cwd=PROJ, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True,
            encoding='utf-8', errors='replace', creationflags=NOWIN)
    except Exception as e:
        return {'ok': False, 'error': str(e)}

    RUN.update(proc=proc, running=True, outdir=outdir, mode=mode,
               start=time.time(),
               run_device=merged.get('device', 'cuda'),
               run_grid=grid)
    # --- multi-run queue (mean over N legs, average at the end) ---
    if from_multi:
        MULTI['dirs'].append(outdir)
        log('[gui] leg {}/{} - out: {}'.format(
            MULTI['total'] - MULTI['left'],
            MULTI['total'], outdir))
    elif leg_count > 1:
        MULTI.update(total=leg_count, left=leg_count - 1, dirs=[outdir],
                     params={k: merged.get(k) for k in FORM_KEYS})
        log('[gui] MULTI-RUN: {} legs queued - mean at the end'.format(
            leg_count))
    else:
        MULTI.update(total=0, left=0, dirs=[], params=None)

    def pump():
        import re
        ms_re = re.compile(r'ms/step=([0-9.]+)')
        pt_re = re.compile(r'^\s+comp=[\d.]+\s+T=\s*\d+K\s+a=')
        for line in proc.stdout:
            log(line)
            if '[preflight] torch.compile disabled' in line:
                RUN['compile_off'] = True
            if pt_re.match(line):
                RUN['done_points'] += 1
                log('[gui] point done {}/{}'.format(
                    RUN['done_points'], RUN['plan_total']))
                continue
            m = ms_re.search(line)
            if m and RUN.get('mode') == 'mace':
                # auto-calibration: every finished production window
                # refreshes the estimator point for this grid/device
                try:
                    prof = estimator.load_profile()
                    if estimator.update_point(
                            prof, 'mace', RUN.get('run_device', 'cuda'),
                            RUN.get('run_grid', 4), float(m.group(1))):
                        estimator.save_profile(prof)
                        log('[gui] estimator profile updated: {} atoms, '
                            '{} ms/step'.format(
                                estimator.natoms_of(RUN.get('run_grid', 4)),
                                m.group(1)))
                except Exception as e:
                    log('[gui] estimator update failed: ' + str(e))
        proc.wait()
        RUN['proc'] = None
        RUN['running'] = False
        RUN['last_exit'] = proc.returncode
        log('[gui] === run finished (exit {}), took {:.1f} s'.format(
            proc.returncode, time.time() - RUN['start']))
        log('[gui] results: ' + outdir)
        # --- multi-run: next leg, or average everything at the end ---
        if (proc.returncode == 0 and MULTI.get('left', 0) > 0
                and MULTI.get('params')):
            MULTI['left'] -= 1
            nxt = dict(MULTI['params'])
            nxt['run_count'] = MULTI['left'] + 1
            nxt['source'] = 'multi'
            log('[gui] === leg done ({}/{}), starting the next one...'
                .format(MULTI['total'] - MULTI['left'],
                        MULTI['total']))
            try:
                res = start_run(nxt)
                if not res.get('ok'):
                    log('[gui] next leg failed: ' + str(res.get('error')))
                    MULTI.update(total=0, left=0, dirs=[], params=None)
            except Exception as e:
                log('[gui] next leg error: ' + str(e))
                MULTI.update(total=0, left=0, dirs=[], params=None)
            return
        if MULTI.get('total', 0) > 1:
            try:
                finish_multi()
            except Exception as e:
                log('[gui] multi finish error: ' + str(e))

    threading.Thread(target=pump, daemon=True).start()
    return {'ok': True, 'outdir': outdir}


# --------------------- torch.compile switch (FEPT_COMPILE) --------------
def compile_enabled():
    """GUI default: torch.compile OFF for engine runs (blocked ptxas on
    client machines killed runs with [WinError 5]; uncompiled always
    finishes). FEPT_COMPILE=1 turns compilation back on for machines
    where it works -- the engine's preflight/rescue then still guards it.
    Mirrors the client-side fix shipped on the customer's PC.
    """
    return str(os.environ.get('FEPT_COMPILE', '')).strip().lower() in (
        '1', 'true', 'yes', 'on')


# --------------------- run progress (points, rate, ETA) -----------------
def progress_summary():
    """Live progress of the CURRENT run for the progress card.

    The client wanted a card that cannot lie: points done out of the
    planned grid, speed measured from the FIRST finished points and an
    ETA that the bar is aligned against (bar = done/total, ETA from the
    measured rate - both converge as points land).
    """
    legs = int(MULTI.get('total') or 0)
    left = int(MULTI.get('left') or 0)
    total = int(RUN.get('plan_total') or 0)
    done = int(RUN.get('done_points') or 0)
    if legs > 1:
        # the bar spans ALL queued legs: finished legs count in full
        done = (legs - left - 1) * total + done
        total = total * legs
    start = float(RUN.get('start') or 0.0)
    running = bool(RUN.get('running'))
    elapsed = (time.time() - start) if start else 0.0
    if not running and RUN.get('last_exit') is not None:
        # frozen final elapsed of the finished run
        elapsed = elapsed or 0.0
    rate = (done / elapsed * 60.0) if (done > 0 and elapsed > 0) else 0.0
    eta = ((total - done) * elapsed / done) if (done > 0 and total > done
                                               and elapsed > 0) else None
    # legs already finished are not in elapsed - add their known cost
    if legs > 1 and left > 0 and done > 0 and total > done:
        per_leg = elapsed / max(1, (legs - left - 1))
        eta += per_leg * left
    pct = (100.0 * done / total) if total > 0 else 0.0
    return {
        'running': running,
        'total': total,
        'done': done,
        'leg': (MULTI['total'] - MULTI['left']) if legs > 1 else 1,
        'legs_total': legs if legs > 1 else 1,
        'pct': round(min(100.0, pct), 1),
        'elapsed_s': round(elapsed, 1),
        'rate_per_min': round(rate, 2),
        'eta_s': (round(eta, 1) if eta is not None else None),
        'last_exit': RUN.get('last_exit'),
        'outdir': RUN.get('outdir'),
    }


# --------------------- app status (ok / warn / error / update) ----------
APP_VERSION = '2.1.0'

# UI languages. Russian is the default AND the only one shipped today;
# the selector reads this table, so adding a locale is one tuple.
LANGS = [('ru', 'Русский')]
LANG_PATH = os.path.join(PROJ, '.ui_lang')


def get_lang():
    """Persisted UI language code, defaulting to the current one."""
    try:
        with open(LANG_PATH, encoding='utf-8') as f:
            code = f.read().strip()
        if code in {c for c, _ in LANGS}:
            return code
    except OSError:
        pass
    return LANGS[0][0]


def set_lang(code):
    """Persist the chosen language; False when the code is unknown."""
    if code not in {c for c, _ in LANGS}:
        return False
    try:
        with open(LANG_PATH, 'w', encoding='utf-8') as f:
            f.write(str(code))
    except OSError as e:
        log('[gui] cannot save language: ' + str(e))
        return False
    return True
UPDATE_CACHE = {'checked_at': 0.0, 'latest': None, 'asset': None,
                'err': None}
UPDATE_TTL = 6 * 3600.0
REPO_REL = ('https://api.github.com/repos/'
            'Vanagandr111/FePt-Thermal-Expansion-MD/releases/latest')


def _release_json(url=None):
    """Latest release info. FEPT_UPDATE_JSON overrides the endpoint
    (tests / staged rollouts point it at a local file or server)."""
    u = url or os.environ.get('FEPT_UPDATE_JSON') or REPO_REL
    if u.startswith('file://'):
        u = u[len('file://'):]
    req = urllib.request.Request(
        u, headers={'User-Agent': 'fept-gui/1.8',
                    'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def check_latest_release(force=False):
    """Cached lookup of the newest release tag + exe asset."""
    if not force and UPDATE_CACHE['latest'] and \
            time.time() - UPDATE_CACHE['checked_at'] < UPDATE_TTL:
        return UPDATE_CACHE
    try:
        rel = _release_json()
        tag = str(rel.get('tag_name') or '').lstrip('vV')
        want = 'FePt-GUI.exe' if IS_WIN else 'FePt-GUI-linux-x86_64'
        asset = None
        for a in rel.get('assets') or []:
            if a.get('name') == want:
                asset = a
                break
        UPDATE_CACHE.update(latest=tag, asset=asset, err=None,
                            checked_at=time.time())
    except Exception as e:
        UPDATE_CACHE.update(err=str(e), checked_at=time.time())
    return UPDATE_CACHE


def _ver_tuple(v):
    parts = []
    for p in str(v or '0').split('.'):
        digits = ''.join(c for c in p if c.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def update_available():
    """(bool_newer, latest_tag)."""
    c = check_latest_release()
    if not c['latest'] or c['err']:
        return False, c['latest']
    return _ver_tuple(c['latest']) > _ver_tuple(APP_VERSION), c['latest']


def status_summary():
    """One badge for the header: are dependencies OK, did the last run
    fail, is there an update? Levels: error > update > warn > ok."""
    checks = []
    level = 'ok'
    last_exit = RUN.get('last_exit')
    if last_exit not in (None, 0):
        level = 'error'
        checks.append('последний расчёт завершился с кодом {}'.format(
            last_exit))
    if not resolve_python():
        level = 'error' if level == 'error' else 'warn'
        checks.append('не найден интерпретатор движка (Dependencies)')
    model = FORM.get('model') or ''
    if FORM.get('mode') == 'mace' and (
            not model or not os.path.exists(model)):
        if level == 'ok':
            level = 'warn'
        checks.append('не выбрана/не найдена модель MACE')
    if RUN.get('compile_off'):
        if level == 'ok':
            level = 'warn'
        checks.append('triton-компиляция отключена автоматически '
                      '(ptxas блок AV/Policy) — расчёт идёт без '
                      'torch.compile, медленнее, но не падает')
    newer, latest = update_available()
    if newer and level == 'ok':
        level = 'update'
    if newer:
        checks.append('доступна версия v{} (у вас v{})'.format(
            latest, APP_VERSION))
    if not checks:
        checks.append('все зависимости на месте, ошибок нет')
    # --- the About tab reads this too: real machine/run info ---
    calib = estimator.load_profile()
    n_pts = len(calib.get('points') or [])
    samples = sum(int(p.get('samples') or len(p.get('history') or []) or 1)
                  for p in (calib.get('points') or []))
    if n_pts:
        calib_txt = '{} точек, {} замеров, файл {}'.format(
            n_pts, samples, os.path.basename(estimator.profile_path()))
    else:
        calib_txt = 'нет (оценка по документированным guess-значениям)'
    try:
        res_dirs = sum(1 for n in os.listdir(PROJ)
                       if n.startswith('results_') and os.path.isdir(
                           os.path.join(PROJ, n)))
    except OSError:
        res_dirs = 0
    return {'level': level, 'text': 'status: ' + level,
            'version': APP_VERSION, 'latest': latest,
            'update_available': bool(newer), 'checks': checks,
            'frozen': FROZEN, 'lang': get_lang(),
            'python': sys.version.split()[0],
            'host': estimator.machine_name(),
            'proj': PROJ,
            'calibration': calib_txt,
            'results_dirs': res_dirs,
            'last_outdir': RUN.get('outdir') or '—'}


def _sh_quote(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def build_update_bat(self_pid, new_exe, cur_exe):
    """Batch file that swaps the frozen exe after we exit.

    A running one-file exe cannot overwrite itself, so the updater
    downloads to .new, writes this bat and defers: the bat kills our
    PID, moves .new over the exe, relaunches and deletes itself.
    """
    report = os.path.join(os.path.dirname(new_exe), 'update_report.txt')
    return (
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        'echo bat-start %(ver)s -> %(ts)s >> "%(report)s"\r\n'
        'ping -n 3 127.0.0.1 >nul\r\n'
        'taskkill /F /PID %(pid)d >nul 2>nul\r\n'
        'echo taskkill rc=%%ERRORLEVEL%% >> "%(report)s"\r\n'
        'ping -n 3 127.0.0.1 >nul\r\n'
        ':swap\r\n'
        'move /Y "%(new)s" "%(cur)s" >nul\r\n'
        'if exist "%(new)s" (\r\n'
        '  echo swap-retry %%TIME%% >> "%(report)s"\r\n'
        '  ping -n 2 127.0.0.1 >nul\r\n'
        '  goto :swap\r\n'
        ')\r\n'
        'echo swapped %%TIME%% >> "%(report)s"\r\n'
        'ping -n 4 127.0.0.1 >nul\r\n'
        'start "" "%(cur)s"\r\n'
        'echo relaunched %%TIME%% >> "%(report)s"\r\n'
        'ping -n 12 127.0.0.1 >nul\r\n'
        'start "" "%(cur)s"\r\n'
        'echo watchdog-relaunch %%TIME%% >> "%(report)s"\r\n'
        'del "%%~f0"\r\n'
    ) % {'pid': int(self_pid), 'new': new_exe, 'cur': cur_exe,
         'report': report, 'ver': APP_VERSION,
         'ts': time.strftime('%F %T')}


def build_update_sh(self_pid, new_exe, cur_exe):
    """sh twin of build_update_bat: swap the running Linux binary."""
    report = os.path.join(os.path.dirname(new_exe),
                          'update_report.txt').replace('\\', '/')
    return (
        '#!/bin/sh\n'
        'set -u\n'
        'report=' + _sh_quote(report) + '\n'
        'echo "sh-start %(ver)s -> $(date -u +%%F_%%T)" >> "$report"\n'
        'sleep 1\n'
        'kill -9 %(pid)d 2>/dev/null || true\n'
        'echo "killed" >> "$report"\n'
        'sleep 2\n'
        'tries=0\n'
        'while ! mv -f %(new)s %(cur)s 2>>"$report"; do\n'
        '  tries=$((tries+1))\n'
        '  echo "swap-retry $tries" >> "$report"\n'
        '  [ "$tries" -lt 15 ] || { echo "swap-gave-up" >> "$report"; exit 1; }\n'
        '  sleep 1\n'
        'done\n'
        'chmod +x %(cur)s 2>/dev/null || echo "chmod-failed" >> "$report"\n'
        'echo "swapped" >> "$report"\n'
        'rm -f "$0"\n'
        'echo "relaunched" >> "$report"\n'
        'nohup %(cur)s >/dev/null 2>&1 &\n'
    ).replace('\r', '') % {'pid': int(self_pid), 'new': _sh_quote(new_exe),
                            'cur': _sh_quote(cur_exe), 'ver': APP_VERSION}


def run_self_update():
    """Download the newest exe (never over a running file) and arm the
    swap batch. Returns a dict for /api/update."""
    newer, latest = update_available()
    c = check_latest_release()
    if not newer or not c.get('asset'):
        return {'ok': True, 'action': 'up-to-date',
                'version': APP_VERSION, 'latest': latest}
    url = os.environ.get('FEPT_UPDATE_ASSET') or \
        c['asset']['browser_download_url']
    upd_dir = os.path.join(PROJ, 'update_staging')
    os.makedirs(upd_dir, exist_ok=True)
    new_exe = os.path.join(upd_dir, 'FePt-GUI.exe.new' if IS_WIN
                           else 'FePt-GUI.new')
    _download(url, new_exe)
    if not IS_WIN:
        os.chmod(new_exe, 0o755)
    size = os.path.getsize(new_exe)
    if not FROZEN:
        return {'ok': True, 'action': 'staged-not-frozen',
                'version': APP_VERSION, 'latest': latest,
                'staged': new_exe, 'size': size,
                'note': 'dev mode: файл обновления подготовлен, '
                        'exe не заменяется'}
    cur = os.path.abspath(sys.executable)
    if IS_WIN:
        bat = os.path.join(upd_dir, 'apply_update.bat')
        with open(bat, 'w', newline='') as f:
            f.write(build_update_bat(os.getpid(), new_exe, cur))
        # .bat only starts via cmd.exe on Windows
        runner = ['cmd', '/c', bat]
    else:
        bat = os.path.join(upd_dir, 'apply_update.sh')
        with open(bat, 'w', encoding='utf-8') as f:
            f.write(build_update_sh(os.getpid(), new_exe, cur))
        os.chmod(bat, 0o755)
        runner = ['sh', bat]
    log('[gui] update v{} -> v{} staged ({} bytes); restarting '
        'via {}'.format(APP_VERSION, latest, size, bat))
    threading.Timer(2.0, lambda: subprocess.Popen(
        runner, cwd=upd_dir, creationflags=NOWIN,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)).start()
    return {'ok': True, 'action': 'restart-pending',
            'version': APP_VERSION, 'latest': latest, 'size': size}


def _download(url, dest):
    req = urllib.request.Request(url,
                                 headers={'User-Agent': 'fept-gui/1.8'})
    with urllib.request.urlopen(req, timeout=600) as r, \
            open(dest + '.part', 'wb') as w:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            w.write(chunk)
    os.replace(dest + '.part', dest)


# --------------------- download / install status (progress bar) ---------
# Shared with the deps tab: the UI polls /api/download_status.
DL = {'active': False, 'label': '', 'have': 0, 'total': 0, 'mode': 'bytes',
      'done_msg': ''}

# torch.compile needs triton; on Windows the pip package is
# 'triton-windows' (vendor fork with ptxas.exe), plain 'triton' has no
# win wheels. The customer's machine had deps installed ONLY from this
# tab -> no triton at all -> 'triton dead', so the installer owns it.
TRITON_SPEC = ['triton-windows'] if os.name == 'nt' else ['triton']

# ---------------- proxy (HTTP(S) / SOCKS5, optional auth) --------------
# Config lives in the app root (proxy.json); it applies to EVERY download
# the app does (python, lammps, models, updates) and to pip via --proxy.
PROXY_CFG = {'type': '', 'host': '', 'port': '', 'user': '', 'pass': ''}
PROXY_PATH = os.path.join(PROJ, 'proxy.json')


def load_proxy():
    global PROXY_PATH
    PROXY_PATH = os.path.join(PROJ, 'proxy.json')
    try:
        with open(PROXY_PATH, encoding='utf-8') as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            PROXY_CFG.update({k: str(cfg.get(k) or '')
                              for k in ('type', 'host', 'port', 'user',
                                        'pass')})
    except (OSError, ValueError):
        pass


def save_proxy(cfg):
    global PROXY_PATH
    PROXY_PATH = os.path.join(PROJ, 'proxy.json')
    for k in ('type', 'host', 'port', 'user', 'pass'):
        PROXY_CFG[k] = str(cfg.get(k) or '')
    with open(PROXY_PATH, 'w', encoding='utf-8') as f:
        json.dump({k: PROXY_CFG[k] for k in
                   ('type', 'host', 'port', 'user', 'pass')},
                  f, ensure_ascii=False, indent=1)


def _socks_enable():
    # Make socks5:// proxy URLs usable: PySocks lives in the engine venv
    # (a light dep), pull it into sys.path when needed.
    if PROXY_CFG['type'] != 'socks5':
        return True
    try:
        import socks                     # noqa: F401
        return True
    except ImportError:
        pass
    import glob as _g
    cands = _g.glob(os.path.join(PROJ, '.venv-mace', 'Lib',
                                 'site-packages'))
    cands += _g.glob(os.path.join(PROJ, '.venv-mace', 'lib',
                                  'python*', 'site-packages'))
    for cand in cands:
        if cand not in sys.path:
            sys.path.insert(0, cand)
        try:
            import socks                 # noqa: F401
            return True
        except ImportError:
            continue
    return False


def proxy_opener():
    # urllib opener honouring the saved proxy (None = direct connection)
    t = (PROXY_CFG.get('type') or '').lower()
    if t in ('', 'none', 'off') or not PROXY_CFG.get('host'):
        return None
    host, port = PROXY_CFG['host'], PROXY_CFG.get('port') or ''
    auth = ''
    if PROXY_CFG.get('user'):
        from urllib.parse import quote
        auth = quote(PROXY_CFG['user'], safe='') + ':' + \
            quote(PROXY_CFG.get('pass') or '', safe='') + '@'
    if t == 'socks5':
        if not _socks_enable():
            raise RuntimeError('SOCKS5: PySocks не найден - поставь '
                               'компонент pysocks в Зависимостях')
        url = 'socks5h://{}{}:{}'.format(auth, host, port or 1080)
    else:                       # http / https proxy
        url = 'http://{}{}:{}'.format(auth, host, port or 8080)
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({'http': url, 'https': url}))


def proxy_summary():
    # Safe-to-show proxy info for the deps tab (password never leaks)
    t = (PROXY_CFG.get('type') or '').lower()
    if t in ('', 'none') or not PROXY_CFG.get('host'):
        return {'enabled': False}
    return {'enabled': True, 'type': t,
            'addr': '{}:{}'.format(PROXY_CFG['host'],
                                   PROXY_CFG.get('port') or ''),
            'auth': bool(PROXY_CFG.get('user'))}


def url_open(req, timeout=60):
    # urlopen through the configured proxy when one is set
    op = proxy_opener()
    if op is None:
        return urllib.request.urlopen(req, timeout=timeout)
    return op.open(req, timeout=timeout)


def pip_proxy_args():
    # --proxy ... for pip (http(s) directly; socks5 once PySocks is in venv)
    t = (PROXY_CFG.get('type') or '').lower()
    if t in ('', 'none') or not PROXY_CFG.get('host'):
        return []
    host, port = PROXY_CFG['host'], PROXY_CFG.get('port') or ''
    if t == 'socks5':
        user = PROXY_CFG.get('user') or ''
        auth = (user + ':' + PROXY_CFG.get('pass', '') + '@') if user else ''
        return ['--proxy',
                'socks5://{}{}:{}'.format(auth, host, port or 1080)]
    return ['--proxy', 'http://{}:{}'.format(host, port or 8080)]


# ---------------- install manifest (fast starts) ------------------------
# Every install is recorded in <app root>/install_manifest.json, so the
# splash loader only does a sub-second presence check on later launches
# instead of re-verifying the whole environment every time.
INSTALL_LIBS = ['numpy', 'ase', 'pysocks', 'psutil', 'triton', 'torch',
                'mace']
LIGHT_LIBS = ['numpy', 'ase', 'pysocks', 'psutil']
# Heavy parts are NEVER installed on first boot: torch alone is ~2.5 GB
# (slow lines) and LAMMPS ships under its own license - the user clicks
# Install in the Deps tab and the tab blinks red until everything is in.
HEAVY_LIBS = ['triton', 'torch', 'mace']

TORCH_MIRRORS = [
    ['torch', '--index-url', 'https://download.pytorch.org/whl/cu128'],
    ['torch', '--index-url', 'https://pypi.org/simple'],
    ['torch', '--index-url', 'https://download.pytorch.org/whl/cu126'],
]

PYTHON_LINKS = [
    {'label': 'python.org - официальный установщик',
     'url': 'https://www.python.org/downloads/'},
    {'label': 'python-build-standalone - portable zip (astral-sh)',
     'url': 'https://github.com/astral-sh/python-build-standalone/releases'},
    {'label': 'зеркало: релизы этого проекта',
     'url': 'https://github.com/Vanagandr111/FePt-Thermal-Expansion-MD/releases'},
]

LAMMPS_LINKS = [
    {'label': 'LAMMPS releases (GitHub, Windows installer)',
     'url': 'https://github.com/lammps/lammps/releases'},
    {'label': 'официальная страница загрузки (инструкции)',
     'url': 'https://www.lammps.org/download.html'},
]


def manifest_path():
    return os.path.join(PROJ, 'install_manifest.json')


def manifest_load():
    try:
        with open(manifest_path(), encoding='utf-8') as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def manifest_note(name, info):
    m = manifest_load()
    libs = m.get('libs') or {}
    libs[name] = info
    m['libs'] = libs
    m['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(manifest_path(), 'w', encoding='utf-8') as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _site_packages():
    # site-packages of the env the app actually runs with (the splash
    # presence check must describe THAT env, not a hardcoded one)
    import glob as _g
    cands = []
    py = resolve_python()
    if py:
        d = os.path.dirname(py)
        cands += [os.path.join(d, 'Lib', 'site-packages'),
                  os.path.normpath(os.path.join(d, '..', 'lib',
                                                'site-packages'))]
        cands += _g.glob(os.path.join(d, 'lib', 'python*',
                                      'site-packages'))
    cands += [os.path.join(PROJ, '.venv-mace', 'Lib', 'site-packages'),
              os.path.join(PROJ, '.venv-mace', 'lib', 'python*',
                           'site-packages')]
    for c in cands:
        if os.path.isdir(c):
            return os.path.normpath(c)
    return None


def engine_component_state():
    # Fast presence check for the splash loader: NO interpreter spawn -
    # just the venv site-packages dir plus the recorded manifest.
    sp = _site_packages()
    m = manifest_load()
    out = {}
    for name in INSTALL_LIBS:
        # a package may be a dir, a single .py module (PySocks ->
        # socks.py), or land with different casing (PySocks/)
        present = False
        if sp:
            low = name.lower()
            try:
                for entry in os.listdir(sp):
                    el = entry.lower()
                    if el == low or el.startswith(low + '.') or \
                            el.startswith(low + '-'):
                        present = True
                        break
            except OSError:
                pass
        ver = ((m.get('libs') or {}).get(name) or {}).get('version', '')
        out[name] = {'present': present, 'version': ver}
    lmp = find_lmp() if 'find_lmp' in globals() else None
    out['lammps'] = {'present': bool(lmp), 'version': '', 'path': lmp or ''}
    return out


INSTALL_SPECS = {
    'pysocks': ['pysocks'],
    'numpy': ['numpy'],
    'psutil': ['psutil'],
    'scipy': ['scipy'],
    'pandas': ['pandas'],
    'ase': ['ase'],
    'mace': ['mace-torch'],
    'triton': list(TRITON_SPEC),
    'torch': ['torch', '--index-url',
              'https://download.pytorch.org/whl/cu128'],
}


# install/download queue: when a transfer is already running, further
# requests wait in line (with their position shown in the UI) instead
# of failing with 'another transfer is already active'.
QUEUE = []


def queue_add(name, kind='lib'):
    """Return the position (0 = started right now)."""
    if not DL['active']:
        return 0
    QUEUE.append({'name': name, 'kind': kind})
    log('[gui] queued: {} (position {})'.format(name, len(QUEUE)))
    return len(QUEUE)


def queue_remove(name):
    for i, item in enumerate(list(QUEUE)):
        if item['name'] == name:
            QUEUE.pop(i)
            log('[gui] removed from queue: ' + name)
            return True
    return False


def queue_pump():
    """Called when a transfer finishes: start the next queued item."""
    if DL['active'] or not QUEUE:
        return
    item = QUEUE.pop(0)
    log('[gui] queue: starting ' + item['name'])
    if item.get('kind') == 'lammps':
        threading.Thread(target=download_lammps, daemon=True).start()
    else:
        threading.Thread(target=install_lib, args=(item['name'],),
                         daemon=True).start()


class DlCancelled(Exception):
    """User pressed the cancel button for the running download."""


def dl_begin(label, mode='bytes', total=0):
    DL.update(active=True, label=label, have=0, total=total, mode=mode,
              done_msg='', cancel=False)


def dl_end(msg=''):
    DL.update(active=False, done_msg=msg)
    try:
        queue_pump()
    except Exception:
        pass


def install_lib(name):
    """pip-install a whitelisted dependency into the ENGINE interpreter."""
    spec = INSTALL_SPECS.get((name or '').lower())
    if not spec:
        log('[gui] install: unknown package ' + repr(name))
        return
    # show the bar IMMEDIATELY (the user must see something start);
    # every early-return path below already calls dl_end()
    dl_begin('установка: ' + spec[0], mode='indeterminate')
    py, need_url = ensure_engine_python()
    if py and name == 'mace' and not _torch_present(py):
        # mace-torch would otherwise pull the NEWEST torch from pypi
        # (cu130+, breaks on drivers that only do 12.9) - install our
        # pinned cu128 build first so pip keeps it
        log('[gui] mace needs torch first -> installing pinned torch '
            '(cu128)')
        install_lib('torch')
    if not py:
        if need_url:
            log('[gui] no Python at all -> paste a python link in the '
                'deps tab (Python-установка) and press Установить')
            dl_end('Python не найден - укажи ссылку на Python во вкладке Зависимости')
        else:
            log('[gui] pip install FAILED: engine interpreter not found. '
                'Run bootstrap.bat (creates .venv-mace) or set FEPT_PYTHON.')
            dl_end('интерпретатор не найден - запусти bootstrap.bat')
        return
    # torch: walk the mirror chain (pytorch index -> pypi -> cu126)
    variants = ([list(s) for s in TORCH_MIRRORS]
                if name == 'torch' else [list(spec)])
    r, vspec = None, list(spec)
    try:
        for vi, vspec in enumerate(variants):
            log('[gui] pip install {} into {} (mirror {}/{})'.format(
                vspec[0], py, vi + 1, len(variants)))
            dl_begin('pip install ' + vspec[0], mode='indeterminate')
            r = subprocess.run([py, '-m', 'pip', 'install'] +
                               pip_proxy_args() + vspec,
                               capture_output=True, text=True,
                               timeout=1800, creationflags=NOWIN)
            if r.returncode == 0:
                break
    except Exception as e:
        log('[gui] pip error: ' + str(e))
        r = None
    finally:
        dl_end('pip install завершён: ' + spec[0])
    if r is None:
        return
    for line in (r.stdout or '').strip().splitlines()[-4:]:
        log('[gui]   ' + line)
    if r.returncode != 0:
        log('[gui] pip FAILED (code {}): {}'.format(
            r.returncode, (r.stderr or '')[-400:]))
        return
    log('[gui] pip OK: ' + vspec[0])
    if name == 'torch' and not _triton_present(py):
        log('[gui] torch OK -> installing ' + TRITON_SPEC[0] +
            ' (needed by torch.compile)')
        rt = subprocess.run([py, '-m', 'pip', 'install'] +
                            pip_proxy_args() + list(TRITON_SPEC),
                            capture_output=True, text=True,
                            timeout=1800, creationflags=NOWIN)
        for tline in (rt.stdout or '').strip().splitlines()[-3:]:
            log('[gui]   ' + tline)
        if rt.returncode != 0:
            log('[gui] pip FAILED (code {}): {}'.format(
                rt.returncode, (rt.stderr or '')[-300:]))
        else:
            log('[gui] pip OK: ' + TRITON_SPEC[0])
    # record into the install manifest -> fast splash starts later
    idx = (vspec[vspec.index('--index-url') + 1]
           if '--index-url' in vspec else 'pypi')
    manifest_note(name, {'spec': vspec[0], 'index': idx})
    _DEPS_CACHE['t'] = 0.0


def _torch_present(py):
    """True when the engine interpreter can already import torch."""
    try:
        cp = subprocess.run(
            [py, '-c', 'import importlib.util as u, sys; '
                       'sys.exit(0 if u.find_spec("torch") else 1)'],
            capture_output=True, timeout=60, creationflags=NOWIN)
        return cp.returncode == 0
    except Exception:
        return False


def _triton_present(py):
    """True when the engine interpreter can see the triton module."""
    try:
        cp = subprocess.run(
            [py, '-c', 'import importlib.util as u, sys; '
                       'sys.exit(0 if u.find_spec("triton") else 1)'],
            capture_output=True, timeout=60, creationflags=NOWIN)
        return cp.returncode == 0
    except Exception:
        return False


def download_url(url, dest, label, attempts=4):
    """Stream-download with progress into the console log.

    url may be ONE url or a LIST of mirrors - every failure moves to the
    next mirror before the retry budget is spent, so a dead CDN or a
    blocked github mirror never blocks the user.

    Failure-safety: DL['active'] is ALWAYS released (a WinError 10054
    reset used to leave it True forever, so every later download click
    answered 'another transfer is already active' until a restart), and
    transient connection resets are retried before giving up.
    """
    urls = list(url) if isinstance(url, (list, tuple)) else [url]
    tmp = dest + '.part'
    last_err = None
    for u_i, url in enumerate(urls):
        if len(urls) > 1:
            log('[gui] download {} <- mirror {}/{}: {}'.format(
                label, u_i + 1, len(urls), url))
        else:
            log('[gui] download {} <- {}'.format(label, url))
        for attempt in range(1, attempts + 1):
            try:
                req = urllib.request.Request(
                    url, headers={'User-Agent': 'fept-gui/1.8'})
                done = 0
                dl_begin(label)
                try:
                    with url_open(req, timeout=60) as r, \
                            open(tmp, 'wb') as w:
                        total = int(r.headers.get('Content-Length') or 0)
                        DL['total'] = total
                        while True:
                            if DL.get('cancel'):
                                raise DlCancelled()
                            chunk = r.read(1 << 20)
                            if not chunk:
                                break
                            w.write(chunk)
                            done += len(chunk)
                            DL['have'] = done
                            if total and done % (50 << 20) < (1 << 20):
                                log('[gui]   {:.0f} / {:.0f} MB'.format(
                                    done / 1e6, total / 1e6))
                finally:
                    DL['active'] = False
                os.replace(tmp, dest)
                size = os.path.getsize(dest)
                log('[gui] saved {} ({:.1f} MB)'.format(dest, size / 1e6))
                dl_end('сохранён: ' + os.path.basename(dest))
                return dest
            except DlCancelled:
                DL['active'] = False
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                log('[gui] download cancelled by user: ' + label)
                dl_end('отменено пользователем')
                return None
            except Exception as e:
                last_err = e
                DL['active'] = False
                log('[gui] mirror {}/{} attempt {}/{} failed ({})'.format(
                    u_i + 1, len(urls), attempt, attempts, e))
                if attempt < attempts:
                    time.sleep(3)
                else:
                    log('[gui] mirror exhausted, moving to the next one')
    try:
        os.unlink(tmp)
    except OSError:
        pass
    dl_end('ошибка загрузки (все зеркала): ' + str(last_err))
    raise RuntimeError('загрузка не удалась (все зеркала): ' + str(last_err))


def download_lammps():
    """Official LAMMPS binary into lammps/ (never bundled into the app)."""
    if find_lmp():
        log('[gui] LAMMPS already present: ' + find_lmp())
        return
    try:
        with url_open(GH_API_LATEST, timeout=30) as r:
            rel = json.load(r)
        assets = [(a['name'], a['browser_download_url'])
                  for a in rel['assets']]
    except Exception as e:
        log('[gui] ERROR: cannot query LAMMPS releases: ' + str(e))
        log('[gui] manual page: https://www.lammps.org/download.html')
        return
    log('[gui] latest LAMMPS: ' + rel['tag_name'])
    os.makedirs(LAMMPS_DIR, exist_ok=True)

    if IS_WIN:
        cand = [u for n, u in assets
                if 'Win' in n and n.lower().endswith('.exe')]
        if not cand:
            log('[gui] ERROR: no Windows asset found')
            return
        installer = download_url(cand[0], os.path.join(LAMMPS_DIR,
                                                       'lammps_setup.exe'),
                                 'LAMMPS Windows installer')
        if not installer:
            log('[gui] download cancelled — install step skipped')
            return
        log('[gui] silent install into ' + LAMMPS_DIR + ' ...')
        dl_begin('LAMMPS: тихая установка', mode='indeterminate')
        try:
            subprocess.run([installer, '/S',
                            '/D={}'.format(LAMMPS_DIR)],
                           check=False, timeout=600)
        except Exception as e:
            log('[gui] installer error: ' + str(e))
        dl_end('LAMMPS: установка завершена')
        for probe in ('lmp.exe', os.path.join('bin', 'lmp.exe')):
            if os.path.isfile(os.path.join(LAMMPS_DIR, probe)):
                log('[gui] OK: ' + os.path.join(LAMMPS_DIR, probe))
                manifest_note('lammps',
                              {'version': rel.get('tag_name', ''),
                               'path': os.path.join(LAMMPS_DIR, probe)})
                _DEPS_CACHE['t'] = 0.0
                return
        log('[gui] lmp.exe not found after install; check lammps/ manually')
    else:
        cand = [u for n, u in assets
                if n.startswith('lammps-linux') and 'GUI' not in n
                and n.endswith('.tar.gz')]
        if not cand:
            log('[gui] ERROR: no linux binary tarball found')
            return
        tgz = download_url(cand[0], os.path.join(LAMMPS_DIR,
                                                 'lammps-bin.tar.gz'),
                           'LAMMPS linux tarball')
        try:
            with tarfile.open(tgz) as tf:
                tf.extractall(LAMMPS_DIR, filter='data')
            log('[gui] unpacked')
        except Exception as e:
            log('[gui] unpack error: ' + str(e))
            return
        lmp_src = None
        for root, _dirs, files in os.walk(LAMMPS_DIR):
            if 'lmp' in files:
                lmp_src = os.path.join(root, 'lmp')
                break
        if lmp_src:
            dest = os.path.join(LAMMPS_DIR, 'lmp')
            if os.path.abspath(lmp_src) != os.path.abspath(dest):
                os.replace(lmp_src, dest)
            os.chmod(dest, 0o755)
            log('[gui] OK: ' + dest)
            _DEPS_CACHE['t'] = 0.0
        else:
            log('[gui] lmp not found in the archive')


# --------------------------------------------------------------- server --
def app_restart():
    """Cold restart: spawn a fresh copy of the program, then exit.
    Used by the header menu and by the tray icon."""
    time.sleep(2)
    args = sys.argv[1:] or (
        [sys.argv[0]] if sys.argv[0].endswith('.py') else [])
    subprocess.Popen([sys.executable] + args,
                     cwd=os.getcwd(), env=os.environ.copy())
    os._exit(0)


def app_shutdown():
    """Quit fully: stop any run, drop the tray icon, leave no processes."""
    try:
        stop_run()
    except Exception:
        pass
    try:
        import tray
        tray.stop()
    except Exception:
        pass
    time.sleep(0.4)
    os._exit(0)


class Handler(BaseHTTPRequestHandler):
    server_version = 'FePtGUI/1.0'

    def log_message(self, fmt, *args):  # quiet access log
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            fn = os.path.join(STATIC, 'index.html')
            try:
                with open(fn, 'rb') as f:
                    body = f.read()
            except OSError:
                body = b'<h1>index.html missing</h1>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == '/api/deps':
            refresh = 'refresh=1' in self.path
            self._json(collect_deps(refresh=refresh))
            return
        if path == '/api/potentials':
            self._json(scan_potentials())
            return
        if path == '/api/python_hint':
            self._json(python_hint())
            return
        if path == '/api/download_status':
            # progress bar state for the deps tab (DL is module-level)
            self._json(dict(DL))
            return
        if path == '/api/queue':
            self._json({'items': [dict(q) for q in QUEUE],
                        'active': bool(DL['active']),
                        'label': DL['label']})
            return
        if path == '/api/symbol_info':
            import urllib.parse
            q = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query)
            sym = (q.get('symbol') or [''])[0]
            self._json(elements.symbol_info(sym))
            return
        if path == '/api/progress':
            self._json(progress_summary())
            return
        if path == '/api/status_summary':
            self._json(status_summary())
            return
        if path == '/api/lang':
            # current UI language + the table of available ones
            self._json({'lang': get_lang(),
                        'langs': [{'code': c, 'label': l}
                                  for (c, l) in LANGS]})
            return
        if path == '/api/update':
            if self.command != 'POST':
                self._json(status_summary())
                return
            try:
                self._json(run_self_update())
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return
        if path == '/api/estimate':
            # pre-run time/memory estimate for the CURRENT form values
            # (POST {form:{...}} may override values for that query only)
            self._json(build_estimate(FORM))
            return
        if path == '/api/structure':
            # newest structure (.lmp): current run's outdir first, else the
            # project data dir (e.g. last calibration structure)
            import urllib.parse as _up
            q = _up.parse_qs(_up.urlsplit(self.path).query)
            outdir = q.get('outdir', [None])[0] or RUN.get('outdir')
            cand = lmpdata.newest_data_file(outdir)
            if not cand:
                cand = lmpdata.newest_data_file(os.path.join(PROJ, 'data'))
            if not cand:
                self._json({'ok': False, 'error': 'нет файлов структуры'})
                return
            try:
                d = lmpdata.parse_data(cand)
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
                return
            n = d['natoms'] or 1
            # x of the B element: form's elem_b when present, else the
            # largest non-majority species - NEVER a bare ['Pt'] that
            # would KeyError on any other chemistry
            _counts = d.get('counts') or {}
            _b = FORM.get('elem_b') or 'Pt'
            if _b not in _counts:
                _b = (sorted(_counts, key=lambda k: _counts[k])[-1]
                      if _counts else None)
            self._json(dict(d, ok=True, file=os.path.basename(cand),
                            x_pt=round((_counts.get(_b) or 0) / n, 4),
                            lengths=[d['cell'][0][0], d['cell'][1][1],
                                     d['cell'][2][2]]))
            return
        if path == '/api/metrics':
            # system resource snapshot for the header gauges
            # (CPU ~200 ms sample; ThreadingHTTPServer -> no stall)
            snap = sysmetrics.sample(cpu_sample_s=0.2)
            try:
                if isinstance(snap.get('cpu'), dict):
                    snap['cpu']['cores'] = os.cpu_count()
            except Exception:
                pass
            self._json(snap)
            return
        if path == '/api/form':
            self._json({'form': dict(FORM),
                        'running': RUN['running'],
                        'outdir': RUN.get('outdir'),
                        'state_n': RUN['state_n']})
            return
        if path == '/api/elements':
            self._json({'elements': elements.load_elements(ELEMENTS_PATH),
                        'file': ELEMENTS_PATH})
            return
        if path == '/api/elements/compat':
            import urllib.parse
            q = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query)
            pot = os.path.realpath((q.get('file') or [''])[0])
            if not os.path.isfile(pot):
                # lammps mode sends no file: fall back to the default
                # MEAM the engine currently uses
                for cand in (os.path.join(CPU_DIR, 'PtFe.meam'),):
                    if os.path.isfile(cand):
                        pot = os.path.realpath(cand)
                        break
            # never read outside the project tree
            if not pot.startswith(os.path.realpath(PROJ) + os.sep):
                self._json({'ok': False, 'error': 'path outside project'})
                return
            chosen = [s.strip() for s in
                      (q.get('system') or [''])[0].split(',') if s.strip()]
            items = elements.load_elements(ELEMENTS_PATH)
            if chosen:
                items = [{'symbol': s} for s in chosen]
            self._json({'ok': True,
                        **elements.compatibility(items, pot)})
            return
        if path == '/api/results':
            outdir = None
            if 'outdir=' in self.path:
                q = self.path.split('outdir=', 1)[1].split('&')[0]
                import urllib.parse
                outdir = urllib.parse.unquote(q)
            if not outdir:
                outdir = RUN.get('outdir')
            if not outdir:
                # no run yet: fall back to the newest folder containing
                # all_results.csv (fresh gate/quick outputs included)
                best, best_t = None, 0.0
                for name in os.listdir(PROJ):
                    cand = os.path.join(PROJ, name)
                    csvf = os.path.join(cand, 'all_results.csv')
                    if os.path.isfile(csvf):
                        t = os.path.getmtime(csvf)
                        if t > best_t:
                            best, best_t = cand, t
                outdir = best or os.path.join(PROJ, 'results_mace')
            payload = collect_results(outdir)
            payload['outdir'] = outdir
            try:
                import json as _json
                with open(os.path.join(outdir, 'meta.json'), 'r',
                          encoding='utf-8') as _mf:
                    payload['meta'] = _json.load(_mf)
            except Exception:
                payload['meta'] = None
            self._json(payload)
            return
        if path == '/api/boot':
            self._json(dict(BOOT, frozen=FROZEN, root=PROJ,
                            default=default_app_root()))
            return
        if path == '/api/hints_base':
            # frozen: the base rides INSIDE the bundle (RESOURCE/_MEIPASS);
            # dev: repo data/ - a beside-exe data/ is a third candidate
            _cand = [os.path.join(RESOURCE, 'data', 'hints_base.json'),
                     os.path.join(PROJ, 'data', 'hints_base.json')]
            _data, _err = None, 'not found'
            for _p in _cand:
                try:
                    with open(_p, encoding='utf-8') as _hf:
                        _data = json.load(_hf)
                    break
                except Exception as _e:
                    _err = '{}: {}'.format(_p, _e)
            self._json(_data if _data else
                       {'elements': {}, 'phases': {}, 'error': _err})
            return
        if path == '/api/log':
            # REST tail of the console buffer (MCP reads logs from here)
            last_n = 80
            if 'last=' in self.path:
                try:
                    last_n = int(self.path.split('last=', 1)[1].split('&')[0])
                except ValueError:
                    last_n = 80
            with COND:
                self._json({'lines': RUN['lines'][-last_n:],
                            'n': RUN['n'], 'running': RUN['running'],
                            'form': dict(FORM),
                            'outdir': RUN.get('outdir'),
                            'state_n': RUN['state_n']})
            return
        if path == '/api/log/stream':
            self.send_response(200)
            self.send_header('Content-Type',
                             'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            last = 0
            if 'since=' in self.path:
                try:
                    last = int(self.path.split('since=', 1)[1].split('&')[0])
                except ValueError:
                    last = 0
            last_state = RUN['state_n']
            try:
                while True:
                    with COND:
                        chunk, state = [], None
                        if RUN['n'] > last:
                            chunk = RUN['lines'][-(RUN['n'] - last):] \
                                if RUN['n'] - last <= len(RUN['lines']) \
                                else RUN['lines']
                            last = RUN['n']
                        if RUN['state_n'] > last_state:
                            last_state = RUN['state_n']
                            state = {'form': dict(FORM),
                                     'source': RUN['last_source'],
                                     'running': RUN['running']}
                        if not chunk and state is None:
                            COND.wait(timeout=15.0)
                    if chunk or state is not None:
                        payload = {'lines': chunk, 'n': last,
                                   'running': RUN['running']}
                        if state is not None:
                            payload['state'] = state
                        data = json.dumps(payload, ensure_ascii=False)
                        self.wfile.write(
                            ('data: ' + data + '\n\n').encode('utf-8'))
                        self.wfile.flush()
                    else:
                        self.wfile.write(
                            ('data: {"ping":1,"n":%d,"running":%s}\n\n'
                             % (last, 'true' if RUN['running'] else 'false'))
                            .encode('utf-8'))
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/api/potentials/upload':
            # raw streamed body (models are up to ~100 MB) -> potentials/
            # (aliased: a local 'import urllib.parse' would shadow the
            # global urllib module for the whole method and break the
            # proxy test below)
            import urllib.parse as _uparse
            q = _uparse.parse_qs(
                _uparse.urlsplit(self.path).query)
            name = (q.get('name') or [''])[0]
            length = int(self.headers.get('Content-Length') or 0)

            def chunks():
                left = length
                while left > 0:
                    b = self.rfile.read(min(1 << 20, left))
                    if not b:
                        break
                    left -= len(b)
                    yield b

            ok, info = potfile.save_upload(GPU_DIR, CPU_DIR, name, chunks())
            if ok:
                _DEPS_CACHE['t'] = 0.0
                log('[gui] potential uploaded: ' + info)
            self._json({'ok': ok, 'info': info})
            return
        body = self._read_body()

        def _jbody():
            if isinstance(body, dict):
                return body          # _read_body already json-decoded
            try:
                return json.loads(body or '{}')
            except (ValueError, TypeError):
                return {}

        # ------- proxy config (applies to every download) -------
        if path == '/api/proxy/save':
            save_proxy(_jbody())
            log('[gui] proxy config saved: {}'.format(proxy_summary()))
            self._json({'ok': True, 'proxy': proxy_summary()})
            return

        if path == '/api/proxy/test':
            # three independent targets: a real proxy check, not a ping
            targets = [
                ('GitHub API', 'https://api.github.com/'),
                ('PyPI', 'https://pypi.org/simple/'),
                ('PyTorch index', 'https://download.pytorch.org/whl/cu128/'),
            ]
            results = []
            for label, url in targets:
                t0 = time.time()
                try:
                    req = urllib.request.Request(
                        url, headers={'User-Agent': 'fept-gui/1.8'})
                    with url_open(req, timeout=25) as resp:
                        data = resp.read(256 * 1024)
                        code = resp.status
                    ms = (time.time() - t0) * 1000.0
                    kbps = (len(data) / 1024.0) / max(ms / 1000.0, 1e-3)
                    results.append({'target': label, 'url': url,
                                    'ok': True, 'code': int(code),
                                    'ms': round(ms), 'kbps': round(kbps),
                                    'bytes': len(data)})
                except Exception as e:
                    results.append({'target': label, 'url': url,
                                    'ok': False, 'error': str(e)[:160]})
            self._json({'results': results, 'proxy': proxy_summary(),
                        'ok': all(r0.get('ok') for r0 in results)})
            return

        # ------- open any app folder (python venv, lammps, ...) -------
        # ---- install queue (position + cancel in the UI) ----
        if path == '/api/queue/add':
            name = str(body.get('name') or '').strip()
            kind = str(body.get('kind') or 'lib').strip()
            if not name:
                self._json({'ok': False, 'error': 'empty name'}, code=400)
                return
            pos = queue_add(name, kind)
            if pos == 0:
                # queue_add returns 0 when idle - then nothing is
                # running, so THIS endpoint must start the worker (the
                # legacy /api/install_lib did; the queue endpoint
                # forgot it -> clicking Install did nothing at all)
                if kind == 'lammps':
                    threading.Thread(target=download_lammps,
                                     daemon=True).start()
                else:
                    threading.Thread(target=install_lib, args=(name,),
                                     daemon=True).start()
            self._json({'ok': True, 'position': pos})
            return
        if path == '/api/queue/remove':
            self._json({'ok': queue_remove(
                str(body.get('name') or '').strip())})
            return

        # ---- program control from the header menu ----
        if path == '/api/app/restart':
            threading.Thread(target=app_restart, daemon=True).start()
            self._json({'ok': True, 'text': 'перезапускаюсь...'})
            return
        if path == '/api/app/shutdown':
            threading.Thread(target=app_shutdown, daemon=True).start()
            self._json({'ok': True, 'text': 'программа остановлена'})
            return

        # the LAMMPS folder (installed copy) in the explorer
        if path == '/api/open_lammps':
            folder = None
            try:
                # find_lmp() returns a display STRING ('D:\...\lmp.exe'),
                # not a pair — unpacking it broke this endpoint silently
                lammps = find_lmp()
                if lammps:
                    folder = os.path.dirname(lammps) if \
                        os.sep in lammps or '/' in lammps else None
            except Exception:
                folder = None
            if not folder:
                self._json({'ok': False, 'error': 'LAMMPS не установлен'},
                           code=400)
                return
            log('[gui] open lammps folder ' + folder)
            threading.Timer(0.25,
                            lambda: os.startfile(folder)).start()
            self._json({'ok': True})
            return

        if path == '/api/open_path':
            p = os.path.abspath(str(_jbody().get('path') or ''))
            allowed = [PROJ, GUI_DIR, os.path.dirname(GUI_DIR)]
            try:
                _py = resolve_python() or ''
                if _py:
                    allowed += [os.path.dirname(_py),
                                os.path.dirname(os.path.dirname(_py))]
            except Exception:
                pass
            if not any(p == a or p.startswith(a + os.sep)
                       for a in allowed) or not os.path.isdir(p):
                self._json({'ok': False, 'error': 'нет папки'}, code=400)
                return
            log('[gui] open folder ' + p)
            threading.Timer(0.25, lambda: os.startfile(p)).start()
            self._json({'ok': True})
            return

        if path == '/api/boot/pick_folder':
            self._json({'ok': True, 'path': native_folder_dialog() or ''})
            return
        if path == '/api/boot/set_root':
            root = os.path.abspath(str(body.get('path') or '').strip())
            if not root or root in (GUI_DIR, os.path.dirname(GUI_DIR)) \
                    or os.path.basename(root).lower() in (
                        'windows', 'program files', 'program files (x86)') \
                    or os.path.dirname(root) == root:
                self._json({'ok': False,
                            'error': 'папка не подходит - выбери свою, '
                                     'не рядом с exe и не системную'})
                return
            try:
                os.makedirs(root, exist_ok=True)
            except OSError as e:
                self._json({'ok': False, 'error': str(e)})
                return
            apply_app_root(root)
            save_app_root(root)
            BOOT.update(need_folder=False, phase='setup', pct=0,
                        error='', logs=[], line='настраиваю папки...')
            for d in (LAMMPS_DIR, GPU_DIR, CPU_DIR,
                      os.path.join(PROJ, 'data')):
                os.makedirs(d, exist_ok=True)
            threading.Thread(target=_boot_setup, daemon=True).start()
            self._json({'ok': True, 'root': root})
            return
        if path == '/api/run':
            self._json(start_run(body))
            return
        if path == '/api/lang':
            # persist the chosen language (only shipped locales accepted)
            code = body.get('lang')
            ok = set_lang(code)
            self._json({'ok': ok, 'lang': get_lang(),
                        'error': None if ok else 'unknown language: ' +
                                 repr(code)})
            return
        if path == '/api/update':
            try:
                self._json(run_self_update())
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return
        if path == '/api/form':
            # agent / UI form edits; source='agent' makes it visible
            updates = body.get('form', body)
            if not isinstance(updates, dict):
                updates = {}
            state_update(updates, source=body.get('source'))
            self._json({'ok': True, 'form': dict(FORM),
                        'state_n': RUN['state_n']})
            return
        if path == '/api/elements':
            action = body.get('action')
            items = elements.load_elements(ELEMENTS_PATH)
            if action == 'save':
                item = body.get('item') or {}
                ok, err = elements.validate_element(item)
                if not ok:
                    self._json({'ok': False, 'error': err})
                    return
                items, idx = elements.upsert_element(items, item)
                elements.save_elements(items, ELEMENTS_PATH)
                log('[gui] element saved: ' + items[idx]['symbol'])
                self._json({'ok': True, 'elements': items, 'index': idx})
                return
            if action == 'delete':
                sym = str(body.get('symbol') or '').strip()
                items = elements.remove_element(items, sym)
                elements.save_elements(items, ELEMENTS_PATH)
                log('[gui] element removed: ' + sym)
                self._json({'ok': True, 'elements': items})
                return
            self._json({'ok': False, 'error': 'unknown action'})
            return
        if path == '/api/stop':
            stop_run()
            self._json({'ok': True})
            return
        if path == '/api/open_folder':
            outdir = body.get('path') or RUN.get('outdir') \
                or os.path.join(PROJ, 'results_mace')
            if outdir == 'POT':  # UI shorthand: the potentials root
                outdir = os.path.join(PROJ, 'potentials')
            if not os.path.isdir(outdir):
                os.makedirs(outdir, exist_ok=True)
            want_file = (body.get('file') or '').strip()
            if want_file:
                # "Перейти в результаты": open the exact artefact
                cand = os.path.join(outdir, os.path.basename(want_file))
                if os.path.isfile(cand):
                    try:
                        os.startfile(cand)  # noqa: S606
                    except Exception as _e:
                        log('[gui] open file failed: %s' % _e)
                else:
                    log('[gui] file not found: ' + cand)
            log('[gui] open folder: ' + outdir)
            try:
                if IS_WIN:
                    os.startfile(outdir)  # noqa: S606
                else:
                    subprocess.Popen(['xdg-open', outdir])
                self._json({'ok': True})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
            return
        if path == '/api/estimate':
            # same estimate, but the request form dict overrides values
            # for THIS query only (agents ask "what if grid=8?" without
            # touching the human's form)
            form = dict(FORM)
            if isinstance(body.get('form'), dict):
                form.update({k: v for k, v in body['form'].items()
                             if k in FORM_KEYS and v is not None})
            self._json(build_estimate(form))
            return
        if path == '/api/potentials/copy':
            # server-side import of a local file (agent/MCP path): same
            # validation + atomic save as the browser upload route
            src = str(body.get('path') or '').strip().strip('"')
            if not src:
                self._json({'ok': False, 'error': 'path is required'})
                return
            if not os.path.isfile(src):
                self._json({'ok': False,
                            'error': 'file not found: ' + src})
                return
            name = os.path.basename(src)
            try:
                with open(src, 'rb') as f:
                    def _chunks(fh=f):
                        while True:
                            b = fh.read(1 << 20)
                            if not b:
                                break
                            yield b
                    saved = potfile.save_upload(GPU_DIR, CPU_DIR, name,
                                                 _chunks())
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
                return
            log('[gui] potential copied from {}: {}'.format(src, saved))
            self._json({'ok': True, 'saved': saved,
                        'potentials': scan_potentials()})
            return
        if path == '/api/calibrate':
            # quick on-machine calibration of the estimator (~3-5 min:
            # force+stress calls at 32/108/256 atoms, NO relax/MD)
            if DL['active']:
                self._json({'ok': False,
                            'error': 'another transfer is already active'})
                return
            py = resolve_python()
            if not py:
                self._json({'ok': False, 'error': 'no engine python'})
                return
            missing = _missing_modules(py, ('psutil', 'numpy', 'ase'))
            if missing:
                self._json({'ok': False,
                            'error': 'в движке нет ' + ', '.join(missing) +
                                     ' — вкладка Зависимости → Установить'})
                return
            cmd = [py, '-u',
                   os.path.join(SCRIPTS_DIR, 'calibrate_profile.py'),
                   '--device',
                   'cuda' if FORM.get('device') == 'cuda' else 'cpu',
                   '--grids', '2', '3', '4']
            model = FORM.get('model')
            if model and os.path.isfile(model):
                cmd += ['--model', model]

            def _calib_job():
                dl_begin('Калибровка оценки (инференс, без MD)', 'indeterminate')
                try:
                    r = subprocess.run(cmd, cwd=PROJ,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       timeout=1200,
                                       encoding='utf-8', errors='replace',
                                       creationflags=NOWIN)
                    for ln in (r.stdout or '').splitlines():
                        log('[calib] ' + ln)
                except Exception as e:
                    log('[calib] ERROR: ' + str(e))
                finally:
                    dl_end('калибровка оценки завершена')

            threading.Thread(target=_calib_job, daemon=True).start()
            self._json({'ok': True})
            return
        if path == '/api/install_python':
            if DL['active']:
                self._json({'ok': False,
                            'error': 'другая загрузка уже идёт'})
                return
            url = str(body.get('url') or '')
            threading.Thread(target=install_python_job, args=(url,),
                             daemon=True).start()
            self._json({'ok': True, 'url': url})
            return
        if path == '/api/install_lib':
            name = body.get('name')
            if (name or '').lower() not in INSTALL_SPECS:
                self._json({'ok': False, 'error': 'unknown package'})
                return
            if DL['active']:
                self._json({'ok': False,
                            'error': 'another transfer is already active'})
                return
            threading.Thread(target=install_lib, args=(name,),
                             daemon=True).start()
            self._json({'ok': True})
            return
        if path == '/api/download/cancel':
            if not DL['active']:
                self._json({'ok': False, 'error': 'ничего не качается'})
                return
            if DL.get('mode') != 'bytes':
                self._json({'ok': False,
                            'error': 'отмена доступна только для скачивания '
                                     'файла (установки останавливаются '
                                     'крестиком в очереди до старта)'})
                return
            DL['cancel'] = True
            log('[gui] cancel requested for: ' + (DL.get('label') or ''))
            self._json({'ok': True})
            return

        # ---- Excel package: sheet 1 table, sheet 2 charts ----------
        if path == '/api/export_xlsx':
            body = _jbody()
            try:
                dest = _write_export_xlsx(body)
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, code=500)
                return
            log('[gui] xlsx export: ' + dest)
            self._json({'ok': True, 'file': dest,
                        'name': os.path.basename(dest)})
            return

        # ---- import: our .xlsx export or a results file (.csv/.txt) -
        if path == '/api/import_results':
            body = _jbody()
            name = str(body.get('name') or 'файл')
            try:
                import base64 as _b64
                raw = _b64.b64decode(str(body.get('data') or ''))
            except Exception:
                self._json({'ok': False, 'error': 'битые данные файла'},
                           code=400)
                return
            if not raw:
                self._json({'ok': False, 'error': 'пустой файл'},
                           code=400)
                return
            try:
                series = _parse_results_upload(name, raw)
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, code=400)
                return
            payload = {
                'series': series,
                'cte': _compute_cte(series),
                'meta': {'type': 'import', 'imported': name,
                         'created_at': time.strftime('%Y-%m-%d %H:%M:%S')},
                'outdir': _current_outdir(),
            }
            log('[gui] imported results: {} ({} compositions)'.format(
                name, len(series)))
            self._json({'ok': True, 'results': payload})
            return

        if path == '/api/download_lammps':
            if DL['active']:
                self._json({'ok': False,
                            'error': 'another transfer is already active'})
                return
            threading.Thread(target=download_lammps, daemon=True).start()
            self._json({'ok': True})
            return
        if path == '/api/download_model':
            name = body.get('name')
            url = body.get('url') or MODEL_URLS.get(name)
            if not name or not url:
                self._json({'ok': False, 'error': 'unknown model'})
                return
            dest = os.path.join(GPU_DIR, os.path.basename(name))
            if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                # never re-download (and never clobber) an existing file
                self._json({'ok': True, 'skipped': True,
                            'info': name + ' уже скачан'})
                return
            if DL['active']:
                self._json({'ok': False,
                            'error': 'another transfer is already active'})
                return
            os.makedirs(GPU_DIR, exist_ok=True)

            def _job():
                try:
                    download_url(url, dest, name)
                    _DEPS_CACHE['t'] = 0.0
                except Exception as e:
                    log('[gui] download FAILED: ' + str(e))

            threading.Thread(target=_job, daemon=True).start()
            self._json({'ok': True})
            return
        if path == '/api/potentials/precache':
            model = body.get('model') or body.get('name') or ''
            code = PRECACHE_CMDS.get(model)
            if not code:
                self._json({'ok': False, 'error': 'unknown model'})
                return
            if PRECACHE['active']:
                self._json({'ok': False,
                            'error': 'precache уже выполняется'})
                return
            if RUN.get('running'):
                # a second torch in a fresh process cannot load shm.dll on
                # Windows while a calculation holds it - refuse politely
                self._json({'ok': False,
                            'error': 'идёт расчёт — дождитесь окончания'})
                return
            py = resolve_python()
            if not py:
                self._json({'ok': False, 'error': 'engine python not found'})
                return
            PRECACHE['active'] = True

            def _pc_job():
                try:
                    log('[gui] precache {}: запуск ({})'.format(model, py))
                    p = subprocess.Popen(
                        [py, '-c', code], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, errors='replace')
                    for line in p.stdout:
                        log('[gui] precache {}: {}'.format(
                            model, line.rstrip()))
                    p.wait()
                    log('[gui] precache {}: rc={} (веса в кэше)'.format(
                        model, p.returncode))
                except Exception as e:
                    log('[gui] precache {} FAILED: {}'.format(model, e))
                finally:
                    PRECACHE['active'] = False

            threading.Thread(target=_pc_job, daemon=True).start()
            self._json({'ok': True})
            return
        self.send_response(404)
        self.end_headers()


# ------------------------------------------------------------- browser --
def browser_open_chain(url, popen=None, startfile=None, wb_open=None,
                       is_nt=None):
    """POP the browser open and VISIBLE; return the strategy that worked.

    A plain webbrowser.open() is not reliable for a windowed (no-console)
    frozen exe on Windows — it can fail silently.  The chain below starts
    with the most assertive method (cmd `start` spawns a fresh, focused
    browser window) and falls back down to webbrowser.  Pure enough for
    TDD: every side-effecting primitive is injectable."""
    if popen is None:
        popen = subprocess.Popen
    if startfile is None:
        startfile = getattr(os, 'startfile', None)
    if wb_open is None:
        wb_open = webbrowser.open
    if is_nt is None:
        is_nt = os.name == 'nt'
    if is_nt:
        # `start` opens a NEW visible window of the default browser
        strategies = [
            ('cmd-start', lambda: popen(
                ['cmd', '/c', 'start', '', url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))),
            ('startfile', lambda: startfile(url)),
        ]
    else:
        strategies = [('xdg-open', lambda: popen(
            ['xdg-open', url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))]
    strategies.append(('webbrowser', lambda: wb_open(url)))
    for name, attempt in strategies:
        try:
            result = attempt()
            # webbrowser.open() reports False instead of raising
            if result is False:
                continue
            return name
        except Exception:
            continue
    return None


def main():
    global PORT
    if '--port' in sys.argv:
        PORT = int(sys.argv[sys.argv.index('--port') + 1])
    load_proxy()
    if FROZEN and BOOT['need_folder']:
        # first boot: NO folders next to the exe - the UI opens the
        # folder-picker modal and setup starts from /api/boot/set_root
        log('[gui] first boot: choose the app folder in the UI modal')
    else:
        for d in (LAMMPS_DIR, GPU_DIR, CPU_DIR):
            os.makedirs(d, exist_ok=True)
        if FROZEN:
            # smart fast start: sub-second presence check (venv
            # site-packages dirs + install manifest) - the splash never
            # re-installs what is already there
            st = engine_component_state()
            light_ok = all(st.get(n, {}).get('present')
                           for n in LIGHT_LIBS)
            if not resolve_python() or not light_ok:
                BOOT['phase'] = 'setup'
                threading.Thread(target=first_boot_engine,
                                 daemon=True).start()
            else:
                BOOT['phase'] = 'ready'
    srv = None
    for _try in range(12):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
            break
        except OSError as exc:
            log('[gui] port {} busy ({}), retrying...'.format(PORT, exc))
            time.sleep(1.5)
    if srv is None:
        raise RuntimeError('port {} never became free'.format(PORT))
    srv.daemon_threads = True
    url = 'http://127.0.0.1:{}/'.format(PORT)
    # system tray icon: open GUI / restart / quit
    try:
        import tray as tray_mod
        tray_ok = tray_mod.start(url, on_restart=app_restart,
                                 on_quit=app_shutdown)
        log('[gui] tray: ' +
            ('icon ready' if tray_ok else 'disabled (' +
             (tray_mod.TRAY_ERR or 'no reason') + ')'))
    except Exception as exc:
        log('[gui] tray disabled: ' + str(exc))
    print('FePt GUI running at ' + url)
    print('project: ' + PROJ)
    if '--no-browser' not in sys.argv:
        # give the listener a moment, then pop the window VISIBLY
        threading.Timer(0.7, lambda: browser_open_chain(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop_run()
        print('\nbye')


if __name__ == '__main__':
    main()
