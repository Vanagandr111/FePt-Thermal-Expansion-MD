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


def test_q6_fcc_reference_exact():
    """Ideal fcc at 0 K must hit the textbook Lechner-Dellago values:
    q6 = 0.5745 +- 0.005 and q4 = 0.1909 +- 0.005 - at ANY supercell
    size (the old implementation used bond vectors without periodic
    image shifts, so q6 drifted with the cell size and exceeded the
    reference when heated: 0.673 at 1600 K)."""
    from ase.build import bulk
    for k in (2, 3, 4):
        cell = bulk('Cu', 'fcc', a=3.615, cubic=True) * (k, k, k)
        q6 = op.steinhardt_q(cell, 6)
        q4 = op.steinhardt_q(cell, 4)
        assert abs(q6 - 0.5745) < 0.005, 'k=%d q6=%.4f' % (k, q6)
        assert abs(q4 - 0.1909) < 0.005, 'k=%d q4=%.4f' % (k, q4)


def test_invariant_s_over_all_sublattices():
    """S is the maximum over all equivalent sublattices, clipped to
    [0, 1]:

    * a perfect L1_2 cell reads 1.0 (not -1/3);
    * an INVERTED L1_2 cell (order moved to the face sublattices)
      still reads 1.0 - the crystal is ordered either way;
    * a random A1 cell reads ~0;
    * a drifted centre of mass cannot change S (it is defined on the
      generated sublattices and only the symbols count).
    """
    import numpy as np
    out = os.path.join(os.environ.get('TEMP', '/tmp'), 't_inv.lmp')

    def cell(comp, kind='l12'):
        gs.generate_structure(3, 3, 3, comp, out, kind=kind,
                              system='fept')
        return lmpdata.read_lammps_data(out)

    def s_of(atoms, comp):
        sc = atoms.get_scaled_positions(wrap=True)
        return op.long_range_order(atoms, 'l12', comp, sc, 3, 3, 3)

    # 1) perfect cells at both compositions
    assert abs(s_of(cell(0.25), 0.25) - 1.0) < 1e-6
    assert abs(s_of(cell(0.75), 0.75) - 1.0) < 1e-6

    # 2) inverted ordering: minority moves off the corner sublattice
    #    onto the three face sublattices -> still perfectly ordered
    a = cell(0.75)
    sc = a.get_scaled_positions(wrap=True)
    sites = op.sublattice_sites('l12', sc, 3, 3, 3)
    corners = sites[0]
    faces = np.concatenate(sites[1:])
    sym = a.get_chemical_symbols()
    for i in corners:
        sym[int(i)] = 'Pt'
    for i in faces:
        sym[int(i)] = 'Fe'
    a.set_chemical_symbols(sym)
    assert abs(s_of(a, 0.75) - 1.0) < 1e-6, 'inverted order must read 1.0'

    # 3) random A1: S ~ 0 (never negative, never -1/3)
    b = cell(0.25, kind='a1')
    assert 0.0 <= s_of(b, 0.25) < 0.2, s_of(b, 0.25)

    # 4) centre-of-mass drift cannot move S: the sublattices are those
    #    of the AS-GENERATED cell (that is what run_point keeps in
    #    _init_scaled), only the symbols decide
    c = cell(0.25)
    sc0 = c.get_scaled_positions(wrap=True)
    c.set_scaled_positions(c.get_scaled_positions() + 0.13)
    assert abs(op.long_range_order(c, 'l12', 0.25, sc0, 3, 3, 3)
               - 1.0) < 1e-6


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
