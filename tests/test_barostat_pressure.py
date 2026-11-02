# -*- coding: utf-8 -*-
"""Barostat / pressure-convention regression tests.

Pinned here:
  * ASE stress is tensile-positive -> P = -trace(sigma)/3
  * the ideal-gas term NkT/V belongs to the pressure (ASE omits it by default)
  * end-to-end: the production window of a Cu run settles within +-1.5 kbar
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from ase import units  # noqa: E402


class _Dummy:
    """Minimal ASE-like object: potential stress only, no kinetic term."""

    def __init__(self, sxx):
        self._s = np.array([sxx, sxx, sxx, 0.0, 0.0, 0.0])

    def get_stress(self, voigt=True, **kw):
        return self._s


class _DummyGas(_Dummy):
    """Zero potential stress; the ideal-gas term appears only when asked."""

    def __init__(self, n, vol, T):
        super().__init__(0.0)
        self.n, self.vol, self.T = n, vol, T

    def __len__(self):
        return self.n

    def get_volume(self):
        return self.vol

    def get_temperature(self):
        return self.T

    def get_stress(self, voigt=True, include_ideal_gas=False, **kw):
        s = np.zeros(6)
        if include_ideal_gas:
            # ASE adds the kinetic term as a NEGATIVE (tensile) stress, so
            # that P = -trace(sigma)/3 comes out positive for a hot gas.
            s[:3] = -self.n * units.kB * self.T / self.vol     # eV/A^3
        return s


def test_pressure_sign_convention():
    """ASE stress is tensile-positive: P = -trace(sigma)/3.

    Verified against a static Cu scan (positions relaxed):
        a=3.50 (compressed) sigma_xx = -0.103
        a=3.90 (stretched)  sigma_xx = +0.116
    """
    import run_main_mace as rmm

    assert rmm.pressure_bar(_Dummy(-0.01)) > 0     # compressed -> P > 0
    assert rmm.pressure_bar(_Dummy(+0.01)) < 0     # stretched  -> P < 0
    # 0.01 eV/A^3 = 1.602 GPa = 16022 bar
    assert abs(abs(rmm.pressure_bar(_Dummy(0.01))) - 16022) < 200


def test_pressure_includes_ideal_gas():
    """NkT/V must be part of the pressure.

    ASE's get_stress() defaults to include_ideal_gas=False. At 300 K that
    missing term is ~3.5 kbar for a 108-atom cell - exactly the phantom
    "residual pressure" the barostat checks used to report as a failure
    while the cell was already at equilibrium.
    """
    import run_main_mace as rmm

    n, vol, T = 100, 1000.0, 300.0
    expected = n * units.kB * T / vol / units.bar
    got = rmm.pressure_bar(_DummyGas(n, vol, T))
    assert abs(got - expected) / expected < 0.02, (got, expected)


@pytest.mark.slow
def test_cu_production_pressure_within_1p5_kbar(tmp_path):
    """End-to-end: Cu 32 atoms, 300 K -> |mean P| <= 1.5 kbar in production."""
    import run_main_mace as rmm

    model = os.path.join(ROOT, 'potentials', 'gpu', 'mace-mp-0-small.model')
    if not os.path.exists(model):
        pytest.skip('small MACE model not present')

    # CPU by default: the acceptance test must run even when the GPU is busy
    # with a real calculation (CUDA OOM made this test flaky).
    dev = os.environ.get('FEPT_TEST_DEVICE', 'cpu')
    calc = rmm.FastMACECalculator(
        model_paths=[model], device=dev, default_dtype='float32',
        compile_mode=None, precision='fp32', use_bf16=False)
    res = rmm.run_point(
        calc, comp=0.0, T=300, eq_steps=400, prod_steps=600,
        thermo_interval=20, seed=42, grid=2, nx=2, ny=2, nz=2,
        kind='a1', system='cu', pre_eq_steps=4000, timestep_fs=1.0)

    p_mean = abs(float(res['mean_press']))
    assert p_mean <= 1500.0, 'production pressure %.0f bar exceeds +-1.5 kbar' % p_mean
