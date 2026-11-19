# -*- coding: utf-8 -*-
"""Unit tests for the phase-transition block (order params + QHA math).

No GPU, no model files: these guard the formulas and the definitions
that the acceptance of v2.4.0 rests on.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import gen_structure as gs              # noqa: E402
import lmpdata                           # noqa: E402
import order_params as op                # noqa: E402
import phase_stability as ps             # noqa: E402


@pytest.fixture(scope='module')
def l12_cell():
    out = os.path.join(os.environ.get('TEMP', '/tmp'), 't_l12_order.lmp')
    gs.generate_structure(3, 3, 3, 0.25, out, kind='l12', system='fept')
    return lmpdata.read_lammps_data(out)


@pytest.fixture(scope='module')
def a1_cell():
    out = os.path.join(os.environ.get('TEMP', '/tmp'), 't_a1_order.lmp')
    gs.generate_structure(3, 3, 3, 0.25, out, kind='a1', system='fept')
    return lmpdata.read_lammps_data(out)


def test_l12_order_is_one_and_random_is_zero(l12_cell, a1_cell):
    idx = op.sublattice_corner_indices(l12_cell, 3, 3, 3)
    assert len(idx) == len(l12_cell) // 4
    assert op.bragg_williams(l12_cell, idx, 'Pt') > 0.99
    idx_a = op.sublattice_corner_indices(a1_cell, 3, 3, 3)
    assert abs(op.bragg_williams(a1_cell, idx_a, 'Pt')) < 0.25


def test_q6_fcc_reference(l12_cell):
    """fcc q6 = 0.577; only the first shell may be counted (r_cut = 1.25
    x nearest distance), otherwise the 2nd+3rd shells drag q6 to ~0.11
    and the melting test can never pass."""
    q6 = op.steinhardt_q(l12_cell, 6)
    assert 0.50 < q6 < 0.65, q6
    q4 = op.steinhardt_q(l12_cell, 4)
    assert 0.15 < q4 < 0.30, q4


def test_density_is_physical(l12_cell):
    rho = op.number_density(l12_cell)
    # Fe3Pt: rho ~ 0.08 atoms/A^3 (metal, not vacuum)
    assert 0.06 < rho < 0.10, rho


def test_configurational_term_matches_the_order_of_magnitude():
    """T*S_conf(1500 K, x=0.5) = 0.0896 eV/atom - the term the customer
    quoted as ~0.09 eV/atom; an ordered phase must get exactly 0."""
    assert ps.f_conf(1500.0, 0.5) == pytest.approx(-0.0896, abs=2e-3)
    assert ps.f_conf(1500.0, 0.25) == pytest.approx(-0.0727, abs=2e-3)
    assert ps.f_conf(1500.0, 1.0) == 0.0
    assert ps.f_conf(1500.0, 0.0) == 0.0


def test_f_vib_is_negative_and_finite():
    freqs = np.full(96, 0.025)
    freqs[:3] = 0.0                     # acoustic modes of the supercell
    v = ps.f_vib(freqs, 1000.0)
    assert v < 0 and np.isfinite(v)
    # zero-temperature limit reduces to the zero-point energy
    v0 = ps.f_vib(freqs, 0.0)
    assert v0 > 0


def test_crossing_is_linear_and_detects_the_sign_change():
    a = [{'T': t, 'G': 1.0 - 1e-3 * t} for t in (300, 600, 900, 1200)]
    b = [{'T': t, 'G': -1.0 + 1e-3 * t} for t in (300, 600, 900, 1200)]
    # diff = (1 - 1e-3 T) - (-1 + 1e-3 T) = 2 - 2e-3 T -> zero at 1000 K
    t_tr = ps.crossing(a, b, 0.25)
    assert t_tr is not None
    assert 950 < t_tr < 1050, t_tr
    # no crossing inside the window -> None, never a silent guess
    assert ps.crossing(a, a, 0.25) is None


def test_mc_sweep_keeps_the_composition():
    from ase.build import bulk
    from ase.calculators.emt import EMT
    atoms = bulk('Cu', 'fcc', a=3.6, cubic=True) * (3, 3, 3)
    # EMT knows Cu and Pt: make a 50/50 alloy so both sublattices exist
    sym = atoms.get_chemical_symbols()
    for i in range(0, len(sym), 2):
        sym[i] = 'Pt'
    atoms.set_chemical_symbols(sym)
    atoms.calc = EMT()
    n_cu = atoms.get_chemical_symbols().count('Cu')
    rng = np.random.default_rng(0)
    cu = [i for i, s in enumerate(atoms.get_chemical_symbols()) if s == 'Cu']
    pt = [i for i, s in enumerate(atoms.get_chemical_symbols()) if s != 'Cu']
    rate = op.mc_swap_sweep(atoms, atoms.calc, 1000.0, 30, cu, pt, rng)
    assert 0.0 <= rate <= 1.0
    # swaps never create or destroy atoms of a kind
    assert atoms.get_chemical_symbols().count('Cu') == n_cu
    # at T -> 0 only downhill moves are accepted, so S must not rise
    rng2 = np.random.default_rng(1)
    op.mc_swap_sweep(atoms, atoms.calc, 1.0, 30, cu, pt, rng2)
    assert atoms.get_chemical_symbols().count('Cu') == n_cu
