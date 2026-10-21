"""memwatch - grow-detector for RSS/VRAM of a long-running command.

Usage:
  python -u scripts/memwatch.py --interval 10 --out series.csv -- <cmd> <args...>

Polls process RSS (psutil if present, else Windows GetProcessMemoryInfo via
ctypes fallback) and GPU memory of that process (nvidia-smi, optional),
appends CSV rows, and at the end prints a leak verdict from trend().

Design:
  * trend() is PURE (tested): it looks only at the warmed-up tail of the
    series (first third discarded) and requires BOTH a sustained slope
    and a minimum total growth - noise on a plateau is not a leak.
  * the watcher never invents numbers: missing VRAM polls are skipped,
    not interpolated.
"""
import argparse
import csv
import os
import subprocess
import sys
import time


# ---------------------------------------------------------------- trend

def trend(series, warm_fraction=0.34, slope_mb_min=20.0, delta_mb=150.0):
    """Leak verdict for a [(t_s, rss_mb, vram_mb_or_None), ...] series.

    Returns dict: {'n', 'delta_mb', 'slope_mb_min', 'verdict'} where
    verdict is 'empty' (<4 samples), 'ok' or 'leak?'.
    Cells without a VRAM value are ignored for the vram part; the verdict
    uses whichever of RSS/VRAM looks worse (both must stay calm for 'ok').
    """
    if not series or len(series) < 4:
        return {'n': len(series or []), 'delta_mb': None,
                'slope_mb_min': None, 'verdict': 'empty'}
    tail = series[max(1, int(len(series) * warm_fraction)):]
    if len(tail) < 3:
        tail = series[1:]

    def axis(get):
        pts = [(t, v) for t, v in ((s[0], get(s)) for s in tail)
               if v is not None]
        if len(pts) < 3:
            return None
        t0, t1 = pts[0][0], pts[-1][0]
        span_min = max(1e-9, (t1 - t0) / 60.0)
        delta = pts[-1][1] - pts[0][1]
        # least-squares slope (robust against a single spike)
        n = len(pts)
        tm = sum(p[0] for p in pts) / n
        vm = sum(p[1] for p in pts) / n
        den = sum((p[0] - tm) ** 2 for p in pts)
        slope_per_s = (sum((p[0] - tm) * (p[1] - vm) for p in pts) / den
                       if den > 0 else 0.0)
        return delta, slope_per_s * 60.0

    parts = [x for x in (axis(lambda s: s[1]), axis(lambda s: s[2]))
             if x is not None]
    if not parts:
        return {'n': len(series), 'delta_mb': None,
                'slope_mb_min': None, 'verdict': 'empty'}
    delta = max(p[0] for p in parts)
    slope = max(p[1] for p in parts)
    verdict = 'leak?' if (slope >= slope_mb_min
                          and delta >= delta_mb) else 'ok'
    return {'n': len(series), 'delta_mb': round(delta, 1),
            'slope_mb_min': round(slope, 1), 'verdict': verdict}


# ------------------------------------------------------------- sampling

def rss_mb(pid):
    try:
        import psutil
        return float(psutil.Process(pid).memory_info().rss) / 2 ** 20
    except Exception:
        pass
    try:  # windows fallback, no extra deps
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x0400, False, pid)
        if not h:
            return None
        class PMC(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD),
                        ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t),
                        ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t),
                        ('PeakPagefileUsage', ctypes.c_size_t)]
        buf = PMC()
        buf.cb = ctypes.sizeof(PMC)
        ok = psapi = None
        try:
            psapi = ctypes.windll.psapi
            ok = psapi.GetProcessMemoryInfo(h, ctypes.byref(buf), buf.cb)
        except Exception:
            ok = 0
        k32.CloseHandle(h)
        if ok:
            return buf.WorkingSetSize / 2 ** 20
    except Exception:
        return None
    return None


def vram_mb(pid):
    """GPU memory of one process via nvidia-smi (None if unavailable)."""
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory',
             '--format=csv,noheader,nounits'],
            capture_output=True, timeout=10).stdout.decode('utf-8', 'replace')
    except Exception:
        return None
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 2 and parts[0] == str(pid):
            try:
                return float(parts[1])
            except ValueError:
                return None
    return None


def watch(pid, interval, out_path, log=None):
    rows = []
    t0 = time.time()
    need_hdr = not os.path.exists(out_path) or os.path.getsize(out_path) == 0
    with open(out_path, 'a', newline='', encoding='utf-8') as fh:
        wr = csv.writer(fh)
        if need_hdr:
            wr.writerow(['t_s', 'rss_mb', 'vram_mb'])
        while True:
            t = time.time() - t0
            r = rss_mb(pid)
            v = vram_mb(pid)
            if r is None:
                break  # process gone
            wr.writerow(['%.0f' % t, '%.1f' % r,
                         '' if v is None else '%.1f' % v])
            fh.flush()
            rows.append((t, r, v))
            if log:
                log('t=%ds rss=%.0fMB vram=%s' %
                    (t, r, '-' if v is None else '%.0fMB' % v))
            if len(rows) % 6 == 0:
                tr = trend(rows)
                if tr['verdict'] != 'empty':
                    log('  trend: %+.1f MB/min (%s)' %
                        (tr['slope_mb_min'] or 0, tr['verdict']))
            if _done(pid):
                break
            time.sleep(interval)
    return rows


def _done(pid):
    try:
        import psutil
        psutil.Process(pid)
        return False
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser(description='watch RSS/VRAM growth')
    ap.add_argument('--interval', type=float, default=10.0)
    ap.add_argument('--out', default='memwatch.csv')
    ap.add_argument('--pid', type=int, default=None,
                    help='existing process (else spawn the command)')
    ap.add_argument('cmd', nargs='*',
                    help='command line after -- to watch (spawned)')
    a = ap.parse_args()
    if a.pid:
        pid = a.pid
        proc = None
    elif a.cmd:
        proc = subprocess.Popen(a.cmd)
        pid = proc.pid
    else:
        ap.error('need --pid or a command after --')
        return
    print('watching pid %d -> %s (every %.0fs)' % (pid, a.out, a.interval))

    def log(s):
        print(s, flush=True)

    try:
        rows = watch(pid, a.interval, a.out, log=log)
    finally:
        if proc and proc.poll() is None:
            pass  # let the child finish; watcher exits when it dies
    tr = trend(rows)
    print('verdict: %s  delta=%s MB  slope=%s MB/min  samples=%d'
          % (tr['verdict'], tr['delta_mb'], tr['slope_mb_min'], tr['n']))
    return 0 if tr['verdict'] != 'leak?' else 2


if __name__ == '__main__':
    sys.exit(main() or 0)
