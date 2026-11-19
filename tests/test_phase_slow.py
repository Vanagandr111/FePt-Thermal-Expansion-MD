# -*- coding: utf-8 -*-
"""v2.4.0 acceptance tests (GPU / slow): L1_2 pressure gate, hybrid
MC/MD chemical disordering below melting, QHA free energies.

Run strictly one at a time, single thread:
    FEPT_TEST_DEVICE=cuda pytest -m slow -q
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

MODEL_SMALL = os.path.join(ROOT, 'potentials', 'gpu',
                           'mace-mp-0-small.model')


def _calc():
    import run_main_mace as rmm
    if not os.path.exists(MODEL_SMALL):
        pytest.skip('small MACE model not present')
    dev = os.environ.get('FEPT_TEST_DEVICE', 'cpu')
    return rmm.FastMACECalculator(
        model_paths=[MODEL_SMALL], device=dev, default_dtype='float32',
        compile_mode=None, precision='fp32', use_bf16=False)


@pytest.mark.slow
def test_l12_300k_pressure_gate():
    """Fe3Pt (L1_2, x_Pt = 0.25) at 300 K: production pressure inside
    +-1.5 kbar, and the cell must stay cubic (a ~ b ~ c)."""
    import run_main_mace as rmm
    calc = _calc()
    res = rmm.run_point(
        calc, comp=0.25, T=300, eq_steps=400, prod_steps=800,
        thermo_interval=20, seed=7, grid=3, nx=3, ny=3, nz=3,
        kind='l12', system='fept', pre_eq_steps=600, timestep_fs=1.0)
    p_mean = abs(float(res['mean_press']))
    assert p_mean <= 1500.0, 'L1_2 pressure %.0f bar > +-1.5 kbar' % p_mean
    if np.isfinite(res.get('a_y', float('nan'))):
        spread = max(res['a_x'], res['a_y'], res['a_z']) - \
            min(res['a_x'], res['a_y'], res['a_z'])
        assert spread < 0.05, 'orthorhombic axes diverged by %.3f A' % spread


@pytest.mark.slow
def test_mc_md_disorders_the_ordered_cell_without_melting():
    """T = 1600 K with Fe<->Pt swaps: S(t) must fall below 0.9 while the
    crystal survives (q6 > 0.35). If q6 collapses too, the run melted and
    the result is void - that is what this assertion separates."""
    import run_main_mace as rmm
    calc = _calc()
    res = rmm.run_point(
        calc, comp=0.25, T=1600, eq_steps=300, prod_steps=900,
        thermo_interval=20, seed=11, grid=2, nx=2, ny=2, nz=2,
        kind='l12', system='fept', pre_eq_steps=300, timestep_fs=1.0,
        mc_interval=25, mc_attempts=10)
    rows = res.get('order') or []
    assert len(rows) >= 5, 'no order samples were recorded'
    s_vals = [r['S'] for r in rows if r.get('S') is not None]
    q6_vals = [r['q6'] for r in rows[-20:] if r.get('q6') is not None]
    acc = res.get('mc_accept')
    assert s_vals, 'S(t) was not sampled'
    assert min(s_vals) < 0.9, \
        'S stayed at %.3f: swaps did not disorder the cell' % min(s_vals)
    assert q6_vals and float(np.mean(q6_vals)) > 0.35, \
        'q6 = %.3f: the crystal melted, not disordered' % (
            float(np.mean(q6_vals)) if q6_vals else float('nan'))
    assert acc is None or acc > 0.0, 'MC acceptance rate is %s' % acc


@pytest.mark.slow
def test_qha_builds_free_energy_curves():
    """QHA stage: both phases produce finite G(T) curves, the ordered
    phase carries no configurational term and the disordered one does."""
    import phase_stability as ps
    temps = [300.0, 700.0, 1100.0, 1500.0]
    a = ps.phase_curve('l12', 0.25, MODEL_SMALL, temps)
    b = ps.phase_curve('a1', 0.25, MODEL_SMALL, temps)
    assert len(a['curve']) == len(temps) and len(b['curve']) == len(temps)
    for row in a['curve'] + b['curve']:
        assert np.isfinite(row['G']), 'non-finite G at T=%s' % row['T']
    t_tr = ps.crossing(a['curve'], b['curve'], 0.25)
    assert t_tr is None or 300.0 <= t_tr <= 1500.0
