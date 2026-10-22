"""estimator: pure estimation/interpolation math (TDD, no hardware)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import estimator as est  # noqa: E402


def test_natoms_of():
    assert est.natoms_of(2) == 32
    assert est.natoms_of(3) == 108
    assert est.natoms_of(4) == 256
    assert est.natoms_of(1) == 4


def test_interp_inside():
    v, ext = est.interp([(32, 25.0), (256, 54.4)], 144)
    assert not ext
    assert abs(v - (25.0 + (54.4 - 25.0) * (144 - 32) / (256 - 32))) < 1e-9


def test_interp_edges_and_extrap():
    v, ext = est.interp([(32, 25.0), (256, 54.4)], 32)
    assert v == 25.0 and ext is False
    v, ext = est.interp([(32, 25.0), (256, 54.4)], 512)
    assert ext is True
    # extrapolation continues the last segment slope
    slope = (54.4 - 25.0) / (256 - 32)
    assert abs(v - (54.4 + slope * (512 - 256))) < 1e-9


def test_interp_empty_and_single():
    assert est.interp([], 100) == (None, False)
    v, ext = est.interp([(256, 54.4)], 256)
    assert v == 54.4 and ext is False


def _prof(points, overhead=1.6):
    return {'points': points, 'overhead': overhead,
            'machine': {'gpu': 'TestGPU 1 GB'}, 'calibrated_at': 'now'}


def test_estimate_uncalibrated_guess_mace_cuda():
    r = est.estimate({}, 'mace', 'cuda', 4, '300 1200', 500, 1000)
    assert r['confidence'] == 'guess'
    assert r['natoms'] == 256
    assert r['points'] == 2
    assert r['steps'] == 2 * 1500
    # guess: 54.4 ms/step * 3000 steps * 1.6 overhead + 2 * 60 s compile
    assert abs(r['seconds'] - (3000 * 54.4 / 1000 * 1.6 + 120)) < 1.0
    # guess too is topped up: it must never under-report memory
    assert r['vram_mb'] == round(1360 * est.VRAM_SAFETY, 0)
    assert r['ram_mb'] == 1850


def test_estimate_calibrated_linear_time():
    prof = _prof([{'mode': 'mace', 'device': 'cuda', 'grid': 2,
                   'natoms': 32, 'ms_per_step': 25.0, 'vram_mb': 1200.0,
                   'rss_mb': 1500.0},
                  {'mode': 'mace', 'device': 'cuda', 'grid': 4,
                   'natoms': 256, 'ms_per_step': 54.4, 'vram_mb': 1360.0,
                   'rss_mb': 1850.0}])
    r = est.estimate(prof, 'mace', 'cuda', 4, '300', 0, 1000)
    assert r['confidence'] == 'calibrated'
    assert r['ms_step'] == 54.4
    # safety margin on top of the profile: full NPT peaks exceed the
    # simplified calibration cycle (1358 vs 2536 measured) - the estimate
    # must never UNDER-report memory
    assert r['vram_mb'] == round(1360 * est.VRAM_SAFETY, 0)
    assert r['machine_gpu'] == 'TestGPU 1 GB'
    # interpolation between points
    r2 = est.estimate(prof, 'mace', 'cuda', 3, '300', 0, 1000)  # 108 atoms
    assert 25.0 < r2['ms_step'] < 54.4
    assert r2['confidence'] == 'calibrated'


def test_estimate_extrapolation_flagged():
    prof = _prof([{'mode': 'mace', 'device': 'cuda', 'grid': 2,
                   'natoms': 32, 'ms_per_step': 25.0, 'vram_mb': 1200.0,
                   'rss_mb': 1500.0},
                  {'mode': 'mace', 'device': 'cuda', 'grid': 4,
                   'natoms': 256, 'ms_per_step': 54.4, 'vram_mb': 1360.0,
                   'rss_mb': 1850.0}])
    r = est.estimate(prof, 'mace', 'cuda', 8, '300', 0, 1000)   # 2048 atoms
    assert r['confidence'] == 'extrapolated'
    assert r['ms_step'] > 54.4


def test_estimate_lammps_forces_cpu():
    r = est.estimate({}, 'lammps', 'cuda', 8, '300 600', 2000, 5000)
    assert r['confidence'] == 'guess'
    # lammps has no compile cost and forces device=cpu
    assert r['vram_mb'] == 0
    # 2 points * 7000 steps * 2 ms = 28 s (no overhead applied twice)
    assert abs(r['md_seconds'] - 28.0) < 0.01


def test_fits_memory_thresholds():
    assert est.fits_memory(1360, 8192)['level'] == 'ok'
    assert est.fits_memory(1360, 8192)['percent'] == 16.6
    assert est.fits_memory(6200, 8192)['level'] == 'warn'   # 75.8%
    assert est.fits_memory(7300, 8192)['level'] == 'bad'    # 89%
    assert est.fits_memory(9000, 8192)['ok'] is False       # >100%
    assert est.fits_memory(100, 0)['level'] == 'off'


def test_update_point_merges_and_reports_change():
    prof = {'points': []}
    assert est.update_point(prof, 'mace', 'cuda', 4, 54.4) is True
    assert est.update_point(prof, 'mace', 'cuda', 4, 54.4) is False  # same
    assert est.update_point(prof, 'mace', 'cuda', 4, 51.0) is True   # changed
    assert len(prof['points']) == 1
    assert prof['points'][0]['ms_per_step'] == 51.0
    assert est.update_point(prof, 'mace', 'cuda', 2, 25.0) is True
    assert len(prof['points']) == 2


# ---- max_atoms_for_vram: "how many atoms fit on this machine" ----

def _vprof(points, mode='mace', device='cuda'):
    return {'points': [dict(p, mode=mode, device=device) for p in points]}


_LINEAR_PTS = [
    {'natoms': 100, 'vram_mb': 700.0},
    {'natoms': 300, 'vram_mb': 1500.0},
]


def test_max_atoms_exact_linear_inversion():
    # slope 4.0, intercept 300; 90% of 8000 = 7200 -> (7200-300)/4 = 1725
    got = est.max_atoms_for_vram(_vprof(_LINEAR_PTS), total_mb=8000,
                                 use_fraction=0.9)
    assert got == 1725


def test_max_atoms_needs_at_least_two_points():
    assert est.max_atoms_for_vram(_vprof([]), 8192) is None
    assert est.max_atoms_for_vram(
        _vprof([{'natoms': 32, 'vram_mb': 400.0}]), 8192) is None


def test_max_atoms_requires_card_and_positive_slope():
    assert est.max_atoms_for_vram(_vprof(_LINEAR_PTS), total_mb=None) is None
    assert est.max_atoms_for_vram(_vprof(_LINEAR_PTS), total_mb=0) is None
    falling = [{'natoms': 32, 'vram_mb': 900.0},
               {'natoms': 256, 'vram_mb': 400.0}]
    assert est.max_atoms_for_vram(_vprof(falling), 8192) is None


def test_max_atoms_only_for_gpu_mace():
    assert est.max_atoms_for_vram(_vprof(_LINEAR_PTS), 8192,
                                  mode='lammps') is None
    assert est.max_atoms_for_vram(_vprof(_LINEAR_PTS), 8192,
                                  device='cpu') is None


def test_max_atoms_uses_steepest_recent_segment():
    # VRAM grows nonlinearly (390 -> 584 -> 2536): the least-squares fit
    # would UNDER-report the steep tail and OVER-report the atom budget.
    # Conservative rule: invert on the LAST (steepest-capable) segment.
    pts = [{'natoms': 32, 'vram_mb': 390.0},
           {'natoms': 108, 'vram_mb': 584.0},
           {'natoms': 256, 'vram_mb': 2536.0}]
    got = est.max_atoms_for_vram(_vprof(pts), total_mb=8192)
    # last segment: slope (2536-584)/148 = 13.19 MB/atom
    slope = (2536.0 - 584.0) / (256 - 108)
    intercept = 584.0 - slope * 108
    expect = int((8192 * 0.9 - intercept) // slope)
    assert got == expect
    # ...and it must be FAR below the naive full-fit answer (~748)
    assert got < 700


def test_max_atoms_budget_never_overruns_card():
    # even if fit says a huge number, the budget line is use_fraction*total
    pts = [{'natoms': 32, 'vram_mb': 400.0},
           {'natoms': 256, 'vram_mb': 1358.0}]
    got = est.max_atoms_for_vram(_vprof(pts), total_mb=8192)
    assert got is not None and got > 256
    # the estimate at that count must stay below 95% of the card
    slope = (1358.0 - 400.0) / (256 - 32)
    interp_vram = 400.0 + slope * (got - 32)
    assert interp_vram < 8192 * 0.95
