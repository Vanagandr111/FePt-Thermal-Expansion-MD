# -*- coding: utf-8 -*-
"""L1_2 (Cu3Au) generator + finite-size / convergence guards of the engine."""
import inspect
import os
import subprocess
import sys

import pytest

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJ, 'scripts'))

import gen_structure as gs          # noqa: E402
import lmp_helper as lmp            # noqa: E402
import run_main_mace as eng         # noqa: E402


def _types(path):
    counts = {}
    body = False
    for ln in open(path, encoding='utf-8'):
        if ln.startswith('Atoms'):
            body = True
            continue
        if body and ln.strip():
            parts = ln.split()
            if len(parts) == 5:
                counts[parts[1]] = counts.get(parts[1], 0) + 1
    return counts


def _box(path):
    lo, hi = {}, {}
    for ln in open(path, encoding='utf-8'):
        for ax in ('x', 'y', 'z'):
            if ln.endswith('{}lo {}hi\n'.format(ax, ax)):
                lo[ax], hi[ax] = (float(v) for v in ln.split()[:2])
    return (hi['x'] - lo['x'], hi['y'] - lo['y'], hi['z'] - lo['z'])


# ── L1_2 ────────────────────────────────────────────────────────────
def test_l12_fe3pt_corner_is_platinum(tmp_path):
    """x_Pt=0.25 -> Fe3Pt: 8 Pt on the corners, 24 Fe on face centres."""
    out = str(tmp_path / 'l12a.lmp')
    gs.generate_structure(2, 2, 2, 0.25, out, kind='l12')
    c = _types(out)
    assert c.get('1') == 24 and c.get('2') == 8
    assert 'L1_2' in open(out, encoding='utf-8').readline()


def test_l12_fept3_is_the_mirror_composition(tmp_path):
    out = str(tmp_path / 'l12b.lmp')
    gs.generate_structure(2, 2, 2, 0.75, out, kind='l12')
    c = _types(out)
    assert c.get('1') == 8 and c.get('2') == 24


def test_l12_is_cubic_and_vegard_seeded(tmp_path):
    out = str(tmp_path / 'l12.lmp')
    gs.generate_structure(2, 2, 2, 0.25, out, kind='l12')
    bx, by, bz = _box(out)
    assert abs(bx - by) < 1e-9 and abs(by - bz) < 1e-9
    a = bx / 2.0
    vegard = 3.5647 + 0.25 * (3.9242 - 3.5647)
    assert abs(a - vegard) < 5e-3


@pytest.mark.parametrize('comp', [0.3, 0.5, 0.6])
def test_l12_rejects_non_stoichiometric(comp, tmp_path):
    with pytest.raises(ValueError):
        gs.generate_structure(2, 2, 2, comp, str(tmp_path / 'x.lmp'),
                              kind='l12')


def test_l12_cli_roundtrip(tmp_path):
    out = str(tmp_path / 'cli.lmp')
    r = subprocess.run(
        [sys.executable, os.path.join(PROJ, 'scripts', 'gen_structure.py'),
         '1', '1', '1', '0.25', out, '--kind', 'l12'],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert _types(out) == {'1': 3, '2': 1}


# ── finite-size / convergence guards ────────────────────────────────
def test_model_r_max_reads_the_neighbour_cutoff():
    class _M:
        r_max = 6.0

    class _Calc:
        model = _M()

    assert eng._model_r_max(_Calc()) == pytest.approx(6.0)


def test_model_r_max_unknown_returns_zero():
    class _Calc:
        pass

    assert eng._model_r_max(_Calc()) == 0.0


def test_run_point_has_volume_pre_equilibration():
    """Default warm-up must be on: eq=500 alone leaves the volume drifting."""
    p = inspect.signature(eng.run_point).parameters
    assert 'pre_eq_steps' in p
    assert p['pre_eq_steps'].default >= 1000


def test_worker_accepts_pre_eq():
    p = inspect.signature(eng._mp_worker).parameters
    assert 'pre_eq_steps' in p


def test_pre_eq_budget_scales_with_atom_count():
    """Warm-up must not cost 17 min per point on a 256-atom cell."""
    assert eng.pre_eq_budget(4000, 32) == 4000
    assert eng.pre_eq_budget(4000, 256) == 1562
    assert eng.pre_eq_budget(4000, 512) == 1200      # floor
    assert eng.pre_eq_budget(0, 32) == 0             # explicitly off
    assert eng.pre_eq_budget(2000, 32) == 2000       # user's own value kept


def test_cli_exposes_pre_eq_and_l12():
    src = open(os.path.join(PROJ, 'scripts', 'run_main_mace.py'),
               encoding='utf-8').read()
    assert "'--pre-eq'" in src
    assert "choices=['a1', 'l10', 'l12']" in src


# ── gates ───────────────────────────────────────────────────────────
def test_server_rejects_l12_wrong_composition():
    sys.path.insert(0, PROJ)
    import gui.server as srv
    r = srv.start_run({'mode': 'mace', 'cell_kind': 'l12', 'comp': 0.3,
                       'nx': 2, 'ny': 2, 'nz': 2, 'temps': '300'})
    assert r.get('ok') is False
    assert '0.25' in str(r.get('error'))


def test_mcp_schema_offers_l12():
    src = open(os.path.join(PROJ, 'gui', 'mcp_server.py'),
               encoding='utf-8').read()
    assert src.count("'l12'") >= 2


def test_ui_offers_l12(tmp_path):
    html = open(os.path.join(PROJ, 'gui', 'static', 'index.html'),
                encoding='utf-8').read()
    assert '<option value="l12">' in html
    assert "d.kind === 'l12'" in html
