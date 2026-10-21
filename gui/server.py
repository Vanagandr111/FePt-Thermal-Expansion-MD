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
import json
import os
import platform
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# windowed (no-console) builds have no sys.stdout — keep prints harmless
if getattr(sys, 'stdout', None) is None:
    import io as _io
    sys.stdout = _io.StringIO()
    sys.stderr = _io.StringIO()

# Paths: source layout when running from the repo, exe layout when frozen
# (PyInstaller): everything external lives NEXT TO the exe (potentials/,
# lammps/, libs/) and only our own code is inside the bundle.
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
STATIC = os.path.join(GUI_DIR, 'static')
if not os.path.isdir(STATIC):
    STATIC = os.path.join(RESOURCE, 'gui', 'static')
SCRIPTS_DIR = os.path.join(RESOURCE, 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

PORT = int(os.environ.get('FEPT_PORT', 8321))
IS_WIN = os.name == 'nt'
LAMMPS_DIR = os.path.join(PROJ, 'lammps')
GPU_DIR = os.path.join(PROJ, 'potentials', 'gpu')
CPU_DIR = os.path.join(PROJ, 'potentials', 'cpu')
GH_API_LATEST = 'https://api.github.com/repos/lammps/lammps/releases/latest'
# Direct model mirrors (licenses are not ours: fetched on demand only)
MODEL_URLS = {
    'mace-mpa-0-medium.model':
        'https://github.com/ACEsuit/mace-mpa/releases/download/'
        'mace-mpa-0/mace-mpa-0-medium.model',
    'mace-mp-0b3-medium.model':
        'https://github.com/ACEsuit/mace-v0b3/releases/download/'
        '0.3.0/mace-mp-0b3-medium.model',
    'mace-large-0b2.model':
        'https://github.com/ACEsuit/mace-v0b2/releases/download/'
        '2025-04-24/mace-large-0b2.model',
}

# ----------------------------------------------------------------- state --
RUN = {
    'proc': None, 'lines': [], 'n': 0, 'running': False,
    'outdir': None, 'mode': None, 'start': 0.0,
    'state_n': 0, 'last_source': None,
}
COND = threading.Condition()
_DEPS_CACHE = {'t': 0.0, 'data': None}

# Shared form state: the browser edits it via UI, an agent edits it via
# MCP -> POST /api/form; every change bumps state_n so the open GUI
# visibly follows along (fields re-render with an agent pulse).
FORM = {
    'mode': 'mace', 'model': '', 'device': 'cuda',
    'comp': 0.5, 'grid': 4, 'temps': '300 1200',
    'eq': 500, 'prod': 1000,
}
def resolve_python():
    """Interpreter that runs the engine scripts.

    Frozen builds must not use themselves (no torch/ase inside the exe):
    prefer $FEPT_PYTHON, then an external interpreter in <proj>/libs/."""
    envp = os.environ.get('FEPT_PYTHON')
    if envp:
        return envp
    if not FROZEN:
        return sys.executable
    for cand in (os.path.join('libs', 'venv', 'Scripts', 'python.exe'),
                 os.path.join('libs', 'venv', 'bin', 'python'),
                 os.path.join('libs', 'python.exe'),
                 os.path.join('libs', 'python'),
                 # dev layouts on the project host
                 os.path.join('.venv-mace', 'Scripts', 'python.exe'),
                 os.path.join('.venv-mace', 'bin', 'python'),
                 os.path.join('venv', 'Scripts', 'python.exe'),
                 os.path.join('venv', 'bin', 'python')):
        p = os.path.join(PROJ, cand)
        if os.path.isfile(p):
            return p
    # NEVER fall back to sys.executable when frozen: that IS this exe,
    # and spawning it with -c would start a second server (hangs deps).
    return None


_PROBE_CODE = (
    "import json, importlib.util as u\n"
    "d = {'torch': u.find_spec('torch') is not None,\n"
    "     'mace': u.find_spec('mace') is not None,\n"
    "     'ase': u.find_spec('ase') is not None,\n"
    "     'numpy': u.find_spec('numpy') is not None}\n"
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
    "print('PROBE_JSON:' + json.dumps(d))\n"
)


def _probe_libs(python_bin):
    """Probe heavy libs INSIDE the engine interpreter (subprocess).

    Keeps torch/ase/mace as static imports out of the exe bundle and
    makes the deps tab truthful for frozen builds (external venv)."""
    if not python_bin:
        return {'error': 'no engine interpreter (set FEPT_PYTHON or '
                         'create libs/venv next to the exe)'}
    if os.path.abspath(python_bin) == os.path.abspath(sys.executable):
        # would re-launch this very executable (-c is not ours) -> hang
        return {'error': 'engine interpreter resolves to the GUI itself; '
                         'set FEPT_PYTHON to an external python'}
    try:
        cp = subprocess.run([python_bin, '-c', _PROBE_CODE],
                            capture_output=True, timeout=180)
        text = (cp.stdout or b'').decode('utf-8', errors='replace')
        for line in text.splitlines():
            if line.startswith('PROBE_JSON:'):
                return json.loads(line[11:])
        return {'error': (cp.stderr or b'').decode('utf-8',
                                                  'replace')[-300:]}
    except Exception as e:
        return {'error': str(e)[:300]}


FORM_KEYS = ('mode', 'model', 'device', 'comp', 'grid', 'temps', 'eq', 'prod')


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
    data = {
        'python': sys.version.split()[0],
        'executable': sys.executable,
        'engine_python': resolve_python(),
        'frozen': FROZEN,
        'project': PROJ,
        'platform': '{} {} ({})'.format(platform.system(),
                                        platform.release(), platform.machine()),
        'libs': {
            'torch': torch_info,
            'mace': probe.get('mace', False),
            'ase': probe.get('ase', False),
            'numpy': probe.get('numpy', False),
            'probe_error': probe.get('error'),
        },
        'lammps': {'found': bool(lammps), 'path': lammps},
        'potentials': scan_potentials(),
        'folders': {'gpu': GPU_DIR, 'cpu': CPU_DIR, 'lammps': LAMMPS_DIR},
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
                'seg_300_600': None, 'seg_600_900': None,
                'seg_900_1200': None,
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
    stamp = time.strftime('%Y%m%d_%H%M%S')
    outdir = os.path.join(PROJ, 'results_{}_{}'.format(mode, stamp))
    py = resolve_python()
    if not py:
        return {'ok': False,
                'error': 'no engine python found: set FEPT_PYTHON or '
                         'place an interpreter in libs/ (see Dependencies)'}
    if mode == 'mace':
        cmd = [py, '-u',
               os.path.join(SCRIPTS_DIR, 'run_main_mace.py')]
        model = merged.get('model')
        if not model:
            pot = scan_potentials()['gpu']
            if pot:
                model = pot[0]['path']
                state_update({'model': model}, source=params.get('source'))
        if not model:
            return {'ok': False, 'error': 'no model selected'}
        device = merged.get('device', 'cuda')
        cmd += ['--device', device, '--model', model,
                '--comps', str(comp), '--temps'] + [str(t) for t in temps] + \
               ['--grid', str(grid), '--eq', str(eq), '--prod', str(prod),
                '--out', outdir]
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
            encoding='utf-8', errors='replace')
    except Exception as e:
        return {'ok': False, 'error': str(e)}

    RUN.update(proc=proc, running=True, outdir=outdir, mode=mode,
               start=time.time())

    def pump():
        for line in proc.stdout:
            log(line)
        proc.wait()
        RUN['proc'] = None
        RUN['running'] = False
        log('[gui] === run finished (exit {}), took {:.1f} s'.format(
            proc.returncode, time.time() - RUN['start']))
        log('[gui] results: ' + outdir)

    threading.Thread(target=pump, daemon=True).start()
    return {'ok': True, 'outdir': outdir}


def download_url(url, dest, label):
    """Stream-download with progress into the console log."""
    log('[gui] download {} <- {}'.format(label, url))
    tmp = dest + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': 'fept-gui'})
    done = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, 'wb') as w:
        total = int(r.headers.get('Content-Length') or 0)
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            w.write(chunk)
            done += len(chunk)
            if total and done % (50 << 20) < (1 << 20):
                log('[gui]   {:.0f} / {:.0f} MB'.format(done / 1e6,
                                                         total / 1e6))
    os.replace(tmp, dest)
    size = os.path.getsize(dest)
    log('[gui] saved {} ({:.1f} MB)'.format(dest, size / 1e6))
    return dest


def download_lammps():
    """Official LAMMPS binary into lammps/ (never bundled into the app)."""
    if find_lmp():
        log('[gui] LAMMPS already present: ' + find_lmp())
        return
    try:
        with urllib.request.urlopen(GH_API_LATEST, timeout=30) as r:
            rel = json.load(r)
        assets = [(a['name'], a['browser_download_url']) for a in rel['assets']]
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
        log('[gui] silent install into ' + LAMMPS_DIR + ' ...')
        try:
            subprocess.run([installer, '/S',
                            '/D={}'.format(LAMMPS_DIR)],
                           check=False, timeout=600)
        except Exception as e:
            log('[gui] installer error: ' + str(e))
        for probe in ('lmp.exe', os.path.join('bin', 'lmp.exe')):
            if os.path.isfile(os.path.join(LAMMPS_DIR, probe)):
                log('[gui] OK: ' + os.path.join(LAMMPS_DIR, probe))
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
        if path == '/api/form':
            self._json({'form': dict(FORM),
                        'running': RUN['running'],
                        'outdir': RUN.get('outdir'),
                        'state_n': RUN['state_n']})
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
            self._json(collect_results(outdir))
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
        body = self._read_body()
        if path == '/api/run':
            self._json(start_run(body))
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
        if path == '/api/stop':
            stop_run()
            self._json({'ok': True})
            return
        if path == '/api/open_folder':
            outdir = body.get('path') or RUN.get('outdir') \
                or os.path.join(PROJ, 'results_mace')
            if not os.path.isdir(outdir):
                os.makedirs(outdir, exist_ok=True)
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
        if path == '/api/download_lammps':
            threading.Thread(target=download_lammps, daemon=True).start()
            self._json({'ok': True})
            return
        if path == '/api/download_model':
            name = body.get('name')
            url = body.get('url') or MODEL_URLS.get(name)
            if not name or not url:
                self._json({'ok': False, 'error': 'unknown model'})
                return
            os.makedirs(GPU_DIR, exist_ok=True)
            dest = os.path.join(GPU_DIR, name)

            def _job():
                try:
                    download_url(url, dest, name)
                    _DEPS_CACHE['t'] = 0.0
                except Exception as e:
                    log('[gui] download FAILED: ' + str(e))

            threading.Thread(target=_job, daemon=True).start()
            self._json({'ok': True})
            return
        self.send_response(404)
        self.end_headers()


def main():
    global PORT
    if '--port' in sys.argv:
        PORT = int(sys.argv[sys.argv.index('--port') + 1])
    for d in (LAMMPS_DIR, GPU_DIR, CPU_DIR):
        os.makedirs(d, exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    srv.daemon_threads = True
    url = 'http://127.0.0.1:{}/'.format(PORT)
    print('FePt GUI running at ' + url)
    print('project: ' + PROJ)
    if '--no-browser' not in sys.argv:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop_run()
        print('\nbye')


if __name__ == '__main__':
    main()
