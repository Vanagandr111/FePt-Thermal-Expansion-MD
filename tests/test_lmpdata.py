"""lmpdata: the shared structure parser (TDD, stdlib layer)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import lmpdata  # noqa: E402

GOOD = """3 atoms

2 atom types

0.0 14.46 xlo xhi
0.0 14.46 ylo yhi
0.0 14.46 zlo zhi

Atoms

1 1 1.0 2.0 3.0
2 2 4.0 5.0 6.0
3 1 7.0 8.0 9.0
"""


def _write(tmp_path, text):
    p = os.path.join(tmp_path, 'd.lmp')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p


def test_parse_basic(tmp_path):
    p = _write(tmp_path, GOOD)
    d = lmpdata.parse_data(p)
    assert d['natoms'] == 3
    assert d['cell'] == [[14.46, 0, 0], [0, 14.46, 0], [0, 0, 14.46]]
    assert d['positions'][0] == [1.0, 2.0, 3.0]
    assert d['symbols'] == ['Fe', 'Pt', 'Fe']
    assert d['types'] == [1, 2, 1]
    assert d['counts'] == {'Fe': 2, 'Pt': 1}
    # JSON-serializable (this is what /api/structure returns)
    import json
    json.dumps(d)


def test_parse_sorts_by_atom_id(tmp_path):
    p = _write(tmp_path, """3 atoms

0.0 10.0 xlo xhi
0.0 10.0 ylo yhi
0.0 10.0 zlo zhi

Atoms

3 1 7.0 7.0 7.0
1 2 1.0 1.0 1.0
2 1 4.0 4.0 4.0
""")
    d = lmpdata.parse_data(p)
    assert d['types'] == [2, 1, 1]
    assert d['positions'][0] == [1.0, 1.0, 1.0]


def test_missing_atoms_header(tmp_path):
    p = _write(tmp_path, "0.0 10.0 xlo xhi\nAtoms\n1 1 0 0 0\n")
    try:
        lmpdata.parse_data(p)
        raise AssertionError('expected DataFileError')
    except lmpdata.DataFileError:
        pass


def test_count_mismatch(tmp_path):
    p = _write(tmp_path, """5 atoms

0.0 10.0 xlo xhi
0.0 10.0 ylo yhi
0.0 10.0 zlo zhi

Atoms

1 1 0.0 0.0 0.0
2 2 1.0 1.0 1.0
""")
    try:
        lmpdata.parse_data(p)
        raise AssertionError('expected DataFileError')
    except lmpdata.DataFileError as e:
        assert 'declared 5' in str(e)


def test_unknown_type(tmp_path):
    p = _write(tmp_path, """1 atoms

0.0 10.0 xlo xhi
0.0 10.0 ylo yhi
0.0 10.0 zlo zhi

Atoms

1 7 0.0 0.0 0.0
""")
    try:
        lmpdata.parse_data(p)
        raise AssertionError('expected DataFileError')
    except lmpdata.DataFileError as e:
        assert '7' in str(e)


def test_newest_data_file(tmp_path):
    a = os.path.join(tmp_path, 'a.lmp')
    b = os.path.join(tmp_path, 'b.lmp')
    with open(a, 'w') as f:
        f.write(GOOD)
    with open(b, 'w') as f:
        f.write(GOOD)
    os.utime(a, (1000, 1000))
    os.utime(b, (2000, 2000))
    assert lmpdata.newest_data_file(tmp_path, None) == b
    assert lmpdata.newest_data_file(None) is None
    assert lmpdata.newest_data_file(
        os.path.join(tmp_path, 'nope')) is None


def test_read_lammps_data_ase_roundtrip(tmp_path):
    """The ase wrapper must agree with the plain parser (same file)."""
    pytest = __import__('pytest')
    pytest.importorskip('ase')
    p = _write(tmp_path, GOOD)
    atoms = lmpdata.read_lammps_data(p)
    d = lmpdata.parse_data(p)
    assert len(atoms) == d['natoms']
    assert atoms.get_chemical_symbols() == d['symbols']
    assert list(atoms.cell.lengths()) == [
        round(v, 10) for v in
        [d['cell'][0][0], d['cell'][1][1], d['cell'][2][2]]]
    assert atoms.pbc.all()
