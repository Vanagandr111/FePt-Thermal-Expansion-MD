# -*- coding: utf-8 -*-
"""Pure-copper system: generator, data-file header, parser, server gate."""
import io
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import lmpdata  # noqa: E402

PY = sys.executable
GEN = os.path.join(ROOT, 'scripts', 'gen_structure.py')


def gen(tmp_path, *args):
    out = str(tmp_path / 'cu.lmp')
    p = subprocess.run([PY, GEN, '2', '2', '2', '1.0', out] + list(args),
                       capture_output=True, text=True, timeout=120)
    return p, out


def test_cu_cell_geometry_and_symbols(tmp_path):
    p, out = gen(tmp_path, '--system', 'cu')
    assert p.returncode == 0, p.stderr
    d = lmpdata.parse_data(out)
    assert d['natoms'] == 32
    assert set(d['symbols']) == {'Cu'}
    assert d['counts']['Cu'] == 32
    # 2 x 2 x 2 cells of the 3.615 A copper lattice
    lx = d['box'][0][1] - d['box'][0][0]
    assert abs(lx - 2 * 3.615) < 1e-6


def test_cu_rejects_ordering(tmp_path):
    p, _ = gen(tmp_path, '--system', 'cu', '--kind', 'l10')
    assert p.returncode != 0
    assert 'Cu' in (p.stderr + p.stdout)


def test_cu_explicit_abc(tmp_path):
    p, out = gen(tmp_path, '--system', 'cu', '--a-ang', '3.7')
    assert p.returncode == 0, p.stderr
    d = lmpdata.parse_data(out)
    lx = d['box'][0][1] - d['box'][0][0]
    assert abs(lx - 2 * 3.7) < 1e-6


def test_legacy_file_without_elements_header(tmp_path):
    """Old cached Fe-Pt files have no `elements:` line - must still parse."""
    out = tmp_path / 'legacy.lmp'
    out.write_text(
        'Fe-Pt A1\n\n4 atoms\n2 atom types\n\n'
        '0.0 7.2 xlo xhi\n0.0 7.2 ylo yhi\n0.0 7.2 zlo zhi\n\n'
        'Atoms\n\n'
        '1 1 0.0 0.0 0.0\n2 1 1.8 1.8 0.0\n'
        '3 2 1.8 0.0 1.8\n4 2 0.0 1.8 1.8\n', encoding='utf-8')
    d = lmpdata.parse_data(str(out))
    assert d['counts']['Fe'] == 2
    assert d['counts']['Pt'] == 2


def test_server_accepts_cu_and_forces_a1():
    src = io.open(os.path.join(ROOT, 'gui', 'server.py'),
                  encoding='utf-8').read()
    assert "'system': 'fept'" in src
    assert "if system == 'cu':" in src
    assert "comp = 0.0" in src and "cell_kind = 'a1'" in src
    assert "'--system', system" in src
