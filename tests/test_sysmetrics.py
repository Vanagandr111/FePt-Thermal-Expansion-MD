"""sysmetrics: pure derivation functions (TDD, no hardware touched)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import sysmetrics as sm  # noqa: E402


def test_cpu_from_times_basic():
    # idle/kernel/user triples, kernel INCLUDES idle (Windows semantics)
    t0 = (1000, 5000, 2000)          # idle=1000, kernel=5000, user=2000
    t1 = (1100, 5200, 2200)          # +100 idle, +200 kernel, +200 user
    # dtotal = 200+200=400; didle=100 -> busy = 1-100/400 = 75%
    assert sm.cpu_from_times(t0, t1) == 75.0


def test_cpu_from_times_degenerate():
    assert sm.cpu_from_times((5, 5, 5), (5, 5, 5)) is None


def test_cpu_from_times_backwards():
    # counters moving backwards (counter reset) -> no valid measurement
    assert sm.cpu_from_times((100, 200, 100), (50, 150, 50)) is None


def test_parse_gpu_csv_ok():
    line = '1637, 8192, 73, 61, 45.2, 150.0'
    g = sm.parse_gpu_csv(line)
    assert g['available'] is True
    assert g['vram_used_mb'] == 1637
    assert g['vram_total_mb'] == 8192
    assert g['vram_percent'] == 20.0
    assert g['gpu_util'] == 73.0
    assert g['temp_c'] == 61.0
    assert g['power_w'] == 45.2


def test_parse_gpu_csv_unavailable():
    assert sm.parse_gpu_csv('')['available'] is False
    assert sm.parse_gpu_csv('N/A is not running')['available'] is False
    assert sm.parse_gpu_csv('[N/A], [N/A], 0 %')['available'] is False


def test_ram_from_stats():
    r = sm.ram_from_stats(45, 16 * 2 ** 30, 8 * 2 ** 30)
    assert r['available'] is True
    assert r['total_mb'] == 16384
    assert r['used_mb'] == 8192
    assert r['percent'] == 45


def test_level_traffic_light():
    assert sm.level(None) == 'off'
    assert sm.level(40) == 'ok'
    assert sm.level(75) == 'warn'
    assert sm.level(90) == 'bad'
    assert sm.level(85) == 'bad'
    assert sm.level(70) == 'warn'


def test_cell_level_fit_thresholds():
    assert sm.cell_level(256, 40.0) == 'ok'
    assert sm.cell_level(1024, 80.0) == 'warn'
    assert sm.cell_level(4096, 95.0) == 'bad'   # thrashing zone (>=87)
    assert sm.cell_level(8192, 120.0) == 'bad'  # does not fit
    assert sm.cell_level(0, None) == 'off'


def test_sample_shape_without_gpu():
    # sample() runs on the live machine; only validate its keys cheaply
    s = sm.sample(cpu_sample_s=0.03)
    assert set(s) >= {'cpu', 'ram', 'gpu', 'ts'}
    assert set(s['ram']) >= {'used_mb', 'total_mb', 'percent'}
