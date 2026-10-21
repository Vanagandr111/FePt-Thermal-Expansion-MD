"""System metrics: parsing/derivation are pure functions (unit-tested).

The live collectors (GetSystemTimes / GlobalMemoryStatusEx / nvidia-smi)
are Windows/OS glue on top of these; tests never touch real hardware.
"""
import ctypes
import subprocess
import time


def cpu_from_times(t0, t1):
    """CPU utilization (%) from two GetSystemTimes triples.

    Kernel time INCLUDES idle time (Windows convention), so
    busy% = 1 - didle / d(kernel+user).
    t* are (idle, kernel, user) 100-ns counter triples.
    Returns None if the delta is degenerate (no time passed).
    """
    didle = t1[0] - t0[0]
    dtotal = (t1[1] - t0[1]) + (t1[2] - t0[2])
    if dtotal <= 0:
        return None
    busy = 1.0 - (didle / dtotal)
    return max(0.0, min(100.0, busy * 100.0))


def parse_gpu_csv(line):
    """Parse one `nvidia-smi --format=csv,noheader,nounits` line.

    Order: memory.used, memory.total, utilization.gpu, temperature.gpu,
    power.draw, power.limit   (all unit-less numbers).
    Returns dict with vram/gpu fields, or {'available': False}.
    """
    if not line or not line.strip():
        return {'available': False}
    parts = [p.strip() for p in line.split(',')]
    if len(parts) < 4:
        return {'available': False}

    def num(s, default=None):
        try:
            return float(s)
        except (TypeError, ValueError):
            return default

    used, total = num(parts[0]), num(parts[1])
    out = {
        'available': used is not None and total is not None and total > 0,
        'vram_used_mb': used,
        'vram_total_mb': total,
        'vram_percent': (round(100.0 * used / total, 1)
                         if used is not None and total else None),
        'gpu_util': num(parts[2]),
        'temp_c': num(parts[3]),
        'power_w': num(parts[4]) if len(parts) > 4 else None,
    }
    return out


def ram_from_stats(dw_memory_load, total_phys, avail_phys):
    """RAM dict from GlobalMemoryStatusEx fields (bytes for phys)."""
    total_mb = round(total_phys / 2 ** 20) if total_phys else 0
    avail_mb = round(avail_phys / 2 ** 20) if avail_phys else 0
    load = int(dw_memory_load) if dw_memory_load is not None else None
    if load is None and total_mb:
        load = round(100.0 * (total_mb - avail_mb) / total_mb)
    return {
        'available': total_mb > 0,
        'used_mb': max(0, total_mb - avail_mb),
        'total_mb': total_mb,
        'percent': load,
    }


def level(percent):
    """Traffic-light level for an utilization percentage."""
    if percent is None:
        return 'off'
    if percent >= 85:
        return 'bad'
    if percent >= 70:
        return 'warn'
    return 'ok'


def cell_level(natoms, fits_percent):
    """Level for the supercell-fit hint: fits_percent of VRAM used.

    Over ~100% the cell does NOT fit (bad), 87%+ is the documented
    thrashing zone on the reference card, 70%+ warn.
    """
    if fits_percent is None:
        return 'off'
    if fits_percent >= 100:
        return 'bad'
    if fits_percent >= 87:
        return 'bad'
    if fits_percent >= 70:
        return 'warn'
    return 'ok'


# ── live collectors (Windows stdlib only; no psutil dependency) ─────────
class _FT(ctypes.Structure):
    _fields_ = [('lo', ctypes.c_uint32), ('hi', ctypes.c_uint32)]


def _filetime_value(ft):
    return (ft.hi << 32) | ft.lo


def _get_system_times():
    idle, kernel, user = _FT(), _FT(), _FT()
    ok = ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    if not ok:
        return None
    return (_filetime_value(idle), _filetime_value(kernel),
            _filetime_value(user))


def cpu_percent(sample_s=0.25):
    """CPU utilization over a short real sample (blocking ~sample_s)."""
    try:
        t0 = _get_system_times()
        if t0 is None:
            return None
        time.sleep(max(0.02, float(sample_s)))
        t1 = _get_system_times()
        if t1 is None:
            return None
        return cpu_from_times(t0, t1)
    except Exception:
        return None


def ram_info():
    """System RAM via GlobalMemoryStatusEx (bytes -> MB)."""
    class MSMEM(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_uint32),
            ('dwMemoryLoad', ctypes.c_uint32),
            ('ullTotalPhys', ctypes.c_uint64),
            ('ullAvailPhys', ctypes.c_uint64),
            ('ullTotalPageFile', ctypes.c_uint64),
            ('ullAvailPageFile', ctypes.c_uint64),
            ('ullTotalVirtual', ctypes.c_uint64),
            ('ullAvailVirtual', ctypes.c_uint64),
            ('ullAvailExtendedVirtual', ctypes.c_uint64)]

    ms = MSMEM()
    ms.dwLength = ctypes.sizeof(MSMEM)
    ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    if not ok:
        return {'available': False}
    return ram_from_stats(ms.dwMemoryLoad, ms.ullTotalPhys,
                          ms.ullAvailPhys)


def gpu_info():
    """GPU via nvidia-smi CSV (one fast query, ~50 ms)."""
    try:
        r = subprocess.run(
            ['nvidia-smi',
             '--query-gpu=memory.used,memory.total,utilization.gpu,'
             'temperature.gpu,power.draw',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return {'available': False}
        return parse_gpu_csv((r.stdout or '').splitlines()[0]
                             if r.stdout else '')
    except Exception:
        return {'available': False}


def sample(cpu_sample_s=0.25):
    """One metrics snapshot for the GUI header."""
    cpu = {'percent': cpu_percent(cpu_sample_s), 'available': True}
    ram = ram_info()
    gpu = gpu_info()
    return {
        'cpu': cpu,
        'ram': ram,
        'gpu': gpu,
        # traffic-light levels from the tested level() function, so the
        # thresholds live on exactly one side (the server)
        'levels': {
            'cpu': level(cpu['percent']),
            'ram': level(ram.get('percent')),
            'vram': level(gpu.get('vram_percent')),
        },
        'ts': time.time(),
    }
