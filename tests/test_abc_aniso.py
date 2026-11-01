# -*- coding: utf-8 -*-
"""Explicit a/b/c and the anisotropic barostat: geometry + per-axis scaling."""
import os
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
sys.path.insert(0, SCRIPTS)

import gen_structure as gs          # noqa: E402


def _box(path):
    out = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            for axis in ('x', 'y', 'z'):
                if line.strip().endswith(axis + 'lo %s' % axis + 'hi'):
                    out[axis] = float(line.split()[1])
    return out


def test_explicit_axes_set_the_box(tmp_path):
    out = str(tmp_path / 'c.lmp')
    gs.generate_structure(2, 3, 4, 0.5, out, kind='a1',
                          a_ang=4.0, b_ang=4.5, c_ang=5.0)
    box = _box(out)
    assert box == pytest.approx({'x': 8.0, 'y': 13.5, 'z': 20.0})


def test_explicit_axes_scale_positions(tmp_path):
    out = str(tmp_path / 'c.lmp')
    gs.generate_structure(1, 1, 1, 0.5, out, kind='a1',
                          a_ang=4.0, b_ang=4.0, c_ang=4.0)
    xs = []
    started = False
    for line in open(out, encoding='utf-8'):
        if line.strip() == 'Atoms':
            started = True
            continue
        if started and len(line.split()) == 5:
            xs.append([float(v) for v in line.split()[2:]])
    arr = np.array(xs)
    assert arr.min() >= 0.0 and arr.max() <= 4.0
    # distinct coordinates only from the fcc basis fractions
    assert np.isclose(sorted(set(np.round(arr[:, 0], 6))), [0.0, 2.0]).all()


def test_axis_out_of_range_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        gs.generate_structure(2, 2, 2, 0.5, str(tmp_path / 'x.lmp'),
                              kind='a1', a_ang=40.0)


def test_zero_axis_falls_back_to_seed(tmp_path):
    out = str(tmp_path / 'c.lmp')
    gs.generate_structure(2, 2, 2, 0.5, out, kind='a1', a_ang=4.0,
                          b_ang=0, c_ang=0)
    box = _box(out)
    assert box['x'] == pytest.approx(8.0)
    assert box['y'] == pytest.approx(8.0)   # b falls back to a
    assert box['z'] == pytest.approx(8.0)


def test_cli_accepts_axes(tmp_path):
    out = str(tmp_path / 'c.lmp')
    subprocess.run([sys.executable, os.path.join(SCRIPTS, 'gen_structure.py'),
                    '2', '2', '2', '0.5', out, '--kind', 'a1',
                    '--a-ang', '3.9', '--b-ang', '4.1', '--c-ang', '4.3'],
                   check=True, capture_output=True, timeout=120)
    box = _box(out)
    assert box['x'] == pytest.approx(7.8, abs=1e-4)
    assert box['y'] == pytest.approx(8.2, abs=1e-4)
    assert box['z'] == pytest.approx(8.6, abs=1e-4)


def test_aniso_barostat_scales_only_the_load_axis():
    from ase.calculators.calculator import Calculator, all_changes
    from ase import Atoms
    import aniso_barostat as ab
    from ase import units

    class ConstStress(Calculator):
        implemented_properties = ['energy', 'forces', 'stress']

        def __init__(self, stress):
            super().__init__()
            self._s = np.array(stress, dtype=float)

        def calculate(self, atoms=None, properties=None,
                      system_changes=all_changes):
            super().calculate(atoms, properties, system_changes)
            n = len(atoms)
            self.results = {'energy': 0.0, 'forces': np.zeros((n, 3)),
                            'stress': self._s}

    # pressure along x only: ASE stress sign is opposite to pressure
    atoms = Atoms('H4', positions=[[0, 0, 0], [0.5, 0.5, 0],
                                   [0.5, 0, 0.5], [0, 0.5, 0.5]],
                  cell=[4, 4, 4], pbc=True)
    atoms.calc = ConstStress([-0.10, 0.0, 0.0, 0, 0, 0])  # P_x = +16 GPa
    baro = ab.AnisoBerendsen(atoms, 1.0 * units.fs,
                             taut_ps=1.0, bulk_modulus_gpa=150.0)
    before = np.array(atoms.cell.lengths())
    baro(atoms)
    after = np.array(atoms.cell.lengths())
    assert after[0] > before[0]           # compressed along x -> expands
    assert after[1] == pytest.approx(before[1])
    assert after[2] == pytest.approx(before[2])
    # fractions are preserved: affine scaling, not a shift of atoms
    assert np.allclose(atoms.get_scaled_positions(wrap=True)[0], [0, 0, 0])


def test_aniso_barostat_compresses_under_tension():
    from ase.calculators.calculator import Calculator, all_changes
    from ase import Atoms
    import aniso_barostat as ab
    from ase import units

    class Tens(Calculator):
        implemented_properties = ['energy', 'forces', 'stress']

        def calculate(self, atoms=None, properties=None,
                      system_changes=all_changes):
            super().calculate(atoms, properties, system_changes)
            self.results = {'energy': 0.0,
                            'forces': np.zeros((len(atoms), 3)),
                            'stress': np.array([0.10, 0, 0, 0, 0, 0])}

    atoms = Atoms('H2', positions=[[0, 0, 0], [0.5, 0.5, 0]],
                  cell=[4, 4, 4], pbc=True)
    atoms.calc = Tens()
    baro = ab.AnisoBerendsen(atoms, 1.0 * units.fs, taut_ps=1.0)
    before = atoms.cell.lengths()[0]
    baro(atoms)
    assert atoms.cell.lengths()[0] < before


def test_form_and_mcp_expose_new_keys():
    import io
    srv = io.open(os.path.join(ROOT, 'gui', 'server.py'), encoding='utf-8').read()
    for key in ('a_ang', 'b_ang', 'c_ang', 'aniso'):
        assert "'" + key + "'" in srv
    mcp = io.open(os.path.join(ROOT, 'gui', 'mcp_server.py'),
                  encoding='utf-8').read()
    assert 'a_ang' in mcp and 'aniso' in mcp
