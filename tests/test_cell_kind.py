# -*- coding: utf-8 -*-
"""Ячейка: бокс по осям, A1/L1_0, шлюзы формы.

Регресс бага v2.2.5: `gen_structure` писал max(nx,ny,nz)*lc во ВСЕ три оси,
поэтому при nx!=ny!=nz получался куб с вакуумными слоями и заниженной
плотностью (NPT потом схлопывал объём). Плюс новые опции: вид ячейки
A1 (случайный fcc-раствор) / L1_0 (упорядоченные слои Fe-Pt) и поля
nx/ny/nz вместо одного grid.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'gui'))

import gen_structure as gs          # noqa: E402
import lmp_helper as lmp            # noqa: E402
import estimator                    # noqa: E402


def _read(path):
    """(header, box dict, list of (id, type, x, y, z)) from a data file."""
    lines = open(path, encoding='utf-8').read().splitlines()
    header = lines[0]
    box = {}
    for ln in lines:
        m = re.match(r'0\.0\s+([\d.]+)\s+(xlo xhi|ylo yhi|zlo zhi)', ln)
        if m:
            box[m.group(2)[0]] = float(m.group(1))
    i = lines.index('Atoms')
    rows = [ln.split() for ln in lines[i + 2:] if ln.strip()]
    atoms = [(int(r[0]), int(r[1]), float(r[2]), float(r[3]), float(r[4]))
             for r in rows]
    return header, box, atoms


# ── seed lattice constants ───────────────────────────────────────────
def test_lattice_constant_table():
    assert gs.lattice_constant(1.0)[0] == pytest.approx(3.9242)
    assert gs.lattice_constant(0.0)[0] == pytest.approx(3.5647)
    assert gs.lattice_constant(0.5)[0] == pytest.approx(3.615)
    a, c, note = gs.lattice_constant(0.5, kind='l10')
    assert a == pytest.approx(3.85)
    assert c == pytest.approx(3.717)
    assert c / a == pytest.approx(0.9655, abs=1e-3)
    assert 'CuAu' in note


def test_lattice_constant_explicit_override():
    a, c, _ = gs.lattice_constant(0.5, lc_override=3.7)
    assert (a, c) == (pytest.approx(3.7), pytest.approx(3.7))


# ── A1: cubic and orthorhombic boxes ─────────────────────────────────
def test_a1_cubic_box(tmp_path):
    out = str(tmp_path / 'cubic.lmp')
    gs.generate_structure(4, 4, 4, 0.5, out)
    header, box, atoms = _read(out)
    assert len(atoms) == 4 * 4 ** 3
    assert box['x'] == pytest.approx(box['y']) == pytest.approx(box['z'])
    assert box['x'] == pytest.approx(4 * 3.615, abs=1e-6)
    # every atom lies inside the box
    assert max(a[2] for a in atoms) < box['x'] + 1e-9
    assert max(a[4] for a in atoms) < box['z'] + 1e-9


def test_orthorhombic_box_per_axis(tmp_path):
    """Bug regression: box must be nx*a x ny*a x nz*a, not a cube."""
    out = str(tmp_path / 'ortho.lmp')
    gs.generate_structure(2, 3, 4, 0.5, out)
    header, box, atoms = _read(out)
    a = 3.615
    assert len(atoms) == 4 * 2 * 3 * 4
    assert box['x'] == pytest.approx(2 * a, abs=1e-6)
    assert box['y'] == pytest.approx(3 * a, abs=1e-6)
    assert box['z'] == pytest.approx(4 * a, abs=1e-6)
    # no vacuum: number density equals the fcc density 4/a^3
    vol = box['x'] * box['y'] * box['z']
    assert len(atoms) / vol == pytest.approx(4 / a ** 3, rel=1e-6)
    assert max(a_[2] for a_ in atoms) < box['x']
    assert max(a_[3] for a_ in atoms) < box['y']
    assert max(a_[4] for a_ in atoms) < box['z']


def test_a1_composition_follows_x_pt(tmp_path):
    out = str(tmp_path / 'c30.lmp')
    gs.generate_structure(2, 2, 2, 0.25, out)
    _, _, atoms = _read(out)
    n_pt = sum(1 for a in atoms if a[1] == 2)
    assert n_pt == 8          # 32 atoms * 0.25
    assert len(atoms) - n_pt == 24


# ── L1_0: ordered tetragonal ─────────────────────────────────────────
def test_l10_tetragonal_layers_alternate(tmp_path):
    out = str(tmp_path / 'l10.lmp')
    gs.generate_structure(2, 2, 2, 0.5, out, kind='l10')
    header, box, atoms = _read(out)
    assert 'L1_0' in header
    assert len(atoms) == 32
    # tetragonal box: a in-plane, c = 3.717 along z
    assert box['x'] == pytest.approx(2 * 3.85, abs=1e-6)
    assert box['y'] == pytest.approx(2 * 3.85, abs=1e-6)
    assert box['z'] == pytest.approx(2 * 3.717, abs=1e-6)
    assert box['z'] < box['x']
    # Fe/Pt planes alternate along z: z=0 Fe, z=c/2 Pt, ...
    layers = {}
    for a in atoms:
        layers.setdefault(round(a[4], 3), set()).add(a[1])
    zs = sorted(layers)
    assert len(zs) == 4                      # nz=2 -> 2 planes per cell
    assert layers[zs[0]] == {1}
    assert layers[zs[1]] == {2}
    assert layers[zs[2]] == {1}
    assert layers[zs[3]] == {2}
    n_fe = sum(1 for a in atoms if a[1] == 1)
    assert n_fe == 16                      # exactly x_Pt = 0.5


def test_l10_requires_half_composition(tmp_path):
    out = str(tmp_path / 'bad.lmp')
    with pytest.raises(ValueError, match='x_Pt = 0.5'):
        gs.generate_structure(2, 2, 2, 0.3, out, kind='l10')
    assert not os.path.exists(out)


def test_unknown_kind_rejected(tmp_path):
    with pytest.raises(ValueError, match='unknown cell kind'):
        gs.generate_structure(2, 2, 2, 0.5, str(tmp_path / 'x.lmp'),
                              kind='b2')


def test_zero_replication_rejected(tmp_path):
    with pytest.raises(ValueError, match='>= 1'):
        gs.generate_structure(0, 2, 2, 0.5, str(tmp_path / 'x.lmp'))


# ── lmp_helper cache keys ────────────────────────────────────────────
def test_lmp_helper_filename_encodes_cell(monkeypatch, tmp_path):
    monkeypatch.setattr(lmp, 'DATA_DIR', str(tmp_path))
    p_a1 = lmp.gen_structure(0.5, nx=2, ny=2, nz=2, force=True, kind='a1')
    p_l10 = lmp.gen_structure(0.5, nx=2, ny=2, nz=2, force=True, kind='l10')
    p_ortho = lmp.gen_structure(0.5, nx=2, ny=3, nz=4, force=True, kind='a1')
    names = {os.path.basename(p) for p in (p_a1, p_l10, p_ortho)}
    assert len(names) == 3                 # a cached cell is never reused
    assert 'l10' in os.path.basename(p_l10)
    assert '2x3x4' in os.path.basename(p_ortho)
    # second call with force=False returns the same file untouched
    mtime = os.path.getmtime(p_l10)
    again = lmp.gen_structure(0.5, nx=2, ny=2, nz=2, kind='l10')
    assert again == p_l10
    assert os.path.getmtime(p_l10) == mtime


# ── estimator atoms for an orthorhombic cell ─────────────────────────
def test_estimator_orthorhombic_natoms():
    assert estimator.natoms_of(4) == 256
    assert estimator.natoms_of(2) == 32
    assert estimator.natoms_of(2, 3, 4) == 96
    est = estimator.estimate({}, 'mace', 'cuda', 2, '300 1200', 500, 1000,
                             ny=3, nz=4)
    assert est['natoms'] == 96
    est2 = estimator.estimate({}, 'mace', 'cuda', 2, '300', 500, 1000)
    assert est2['natoms'] == 32


# ── server form gates ────────────────────────────────────────────────
def test_form_exposes_cell_fields():
    import server as srv
    for k in ('cell_kind', 'nx', 'ny', 'nz'):
        assert k in srv.FORM_KEYS, k
        assert k in srv.FORM, k
    assert srv.FORM['cell_kind'] == 'a1'
    assert srv.FORM['nx'] == 4


def test_build_estimate_uses_orthorhombic_shape():
    import server as srv
    est = srv.build_estimate({'mode': 'mace', 'device': 'cuda',
                              'nx': 2, 'ny': 3, 'nz': 4, 'temps': '300',
                              'eq': 10, 'prod': 20, 'precision': 'fp16'})
    assert est['natoms'] == 96
