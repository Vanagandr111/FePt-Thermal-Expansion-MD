"""memwatch.trend: leak verdict from an RSS/VRAM series (pure logic)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import memwatch  # noqa: E402


def _flat(n=12, rss=1000.0, vram=400.0, step=0.0):
    return [(i * 60.0, rss + step * i, vram) for i in range(n)]


def test_empty_and_tiny_series():
    assert memwatch.trend([])['verdict'] == 'empty'
    assert memwatch.trend([(0, 1, 1)])['verdict'] == 'empty'


def test_plateau_is_ok():
    tr = memwatch.trend(_flat())
    assert tr['verdict'] == 'ok'
    assert tr['delta_mb'] == 0.0


def test_noisy_plateau_is_ok():
    # +-40MB wander (allocator noise) must NOT be called a leak
    ser = [(i * 60.0, 1000 + (40 if i % 2 else -40), 400.0)
           for i in range(12)]
    assert memwatch.trend(ser)['verdict'] == 'ok'


def test_linear_growth_is_leak():
    ser = _flat(n=15, step=50.0)          # +50 MB every minute
    tr = memwatch.trend(ser)
    assert tr['verdict'] == 'leak?'
    assert tr['slope_mb_min'] >= 45


def test_growth_below_both_thresholds_is_ok():
    # 10 MB/min and +140 MB total: too small to call a leak
    ser = _flat(n=15, step=10.0)
    assert memwatch.trend(ser)['verdict'] == 'ok'


def test_slow_growth_below_threshold_is_ok():
    # 5 MB/min (+300 MB per hour): gradual drift is NOT flagged - the
    # alarm is reserved for >=20 MB/min sustained growth
    ser = _flat(n=61, step=5.0)
    tr = memwatch.trend(ser)
    assert tr['verdict'] == 'ok'
    assert tr['slope_mb_min'] < 20 and tr['delta_mb'] >= 140


def test_short_series_is_marked_short_not_leak():
    # a 60-second run is all warm-up: no alarm AND no all-clear
    ser = [(i * 5.0, 700 + 100.0 * i, None) for i in range(13)]  # 60s
    assert memwatch.trend(ser)['verdict'] == 'short'
    flat_short = [(i * 5.0, 1000.0, 400.0) for i in range(8)]
    assert memwatch.trend(flat_short)['verdict'] == 'short'


def test_vram_only_growth_detected():
    ser = [(i * 60.0, 1000.0, 400.0 + 60.0 * i) for i in range(15)]
    tr = memwatch.trend(ser)
    assert tr['verdict'] == 'leak?'


def test_missing_vram_values_ignored():
    ser = [(i * 60.0, 1000.0, None) for i in range(15)]
    tr = memwatch.trend(ser)
    assert tr['verdict'] == 'ok'
    # rss absent but vram present -> still judged
    ser2 = [(i * 60.0, None, 400.0 + 60.0 * i) for i in range(15)]
    assert memwatch.trend(ser2)['verdict'] == 'leak?'
    # everything missing -> empty
    ser3 = [(i * 60.0, None, None) for i in range(6)]
    assert memwatch.trend(ser3)['verdict'] == 'empty'


# ---- pick_target: the spawned cmd may be a thin wrapper ----

def test_pick_target_real_process_kept():
    assert memwatch.pick_target(100, 1500.0, [(200, 900.0)]) == 100


def test_pick_target_switches_to_biggest_child():
    kids = [(200, 120.0), (201, 1650.0), (202, 8.0)]
    assert memwatch.pick_target(100, 3.0, kids) == 201


def test_pick_target_no_children_stays():
    assert memwatch.pick_target(100, 3.0, []) == 100
    assert memwatch.pick_target(100, 3.0, None) == 100
    # only tiny children: never guess
    assert memwatch.pick_target(100, 3.0, [(200, 12.0)]) == 100


def test_pick_target_missing_rss_values():
    assert memwatch.pick_target(100, None, [(200, None)]) == 100
    # child rss unknown but mine is big enough -> mine
    assert memwatch.pick_target(100, 800.0, [(200, None)]) == 100
