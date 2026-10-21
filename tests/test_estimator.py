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
    assert r['vram_mb'] == 1360
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
    assert r['vram_mb'] == 1360
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
