# -*- coding: utf-8 -*-
"""Fast tests: element hint encyclopedia, exact Pt lattice, run progress
card math, app status summary and the self-update batch file."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import elements  # noqa: E402
import gen_structure  # noqa: E402
import server  # noqa: E402


# ---------------- element encyclopedia (UI atom hint) -----------------
def test_symbol_info_recognizes_common_metals():
    fe = elements.symbol_info('Fe')
    assert fe['ok'] and fe['ru'] == 'Железо' and fe['z'] == 26
    assert abs(fe['mass'] - 55.845) < 0.01
    pt = elements.symbol_info('Pt')
    assert pt['ok'] and pt['ru'] == 'Платина' and abs(pt['mass'] - 195.084) < 0.02


def test_symbol_info_is_case_insensitive_and_rejects_junk():
    assert elements.symbol_info('fe')['ok']  # typed lowercase
    assert elements.symbol_info('FE')['ok']
    assert not elements.symbol_info('Xx')['ok']
    assert not elements.symbol_info('')['ok']
    assert not elements.symbol_info(None)['ok']


def test_symbol_info_covers_every_chemical_element():
    assert len(elements.SYMBOL_INFO) == 118


# ---------------- exact starting lattice for Pt -----------------------
def test_pt_seed_lattice_is_experimental_39242():
    # client complaint: the old 4.0065 (MACE-MP-0 EOS) is +2.21% off
    assert abs(gen_structure.LC_TABLE['pt'] - 3.9242) < 1e-9
    fe = [e for e in elements.DEFAULT_ELEMENTS if e['symbol'] == 'Fe'][0]
    pt = [e for e in elements.DEFAULT_ELEMENTS if e['symbol'] == 'Pt'][0]
    assert abs(pt['lc'] - 3.9242) < 1e-9


# ---------------- current-run progress card --------------------------
def test_progress_summary_rate_eta_and_pct():
    srv = server
    srv.RUN['plan_total'] = 4
    srv.RUN['done_points'] = 2
    srv.RUN['start'] = time.time() - 60.0
    srv.RUN['running'] = True
    srv.RUN['last_exit'] = None
    p = srv.progress_summary()
    assert p['running'] is True
    assert p['total'] == 4 and p['done'] == 2
    assert abs(p['pct'] - 50.0) < 0.01
    assert abs(p['rate_per_min'] - 2.0) < 0.2          # 2 pts / minute
    assert abs(p['eta_s'] - 60.0) < 1.0                # 2 left at 30 s/pt


def test_progress_summary_before_first_point_has_no_eta():
    srv = server
    srv.RUN['plan_total'] = 7
    srv.RUN['done_points'] = 0
    srv.RUN['start'] = time.time() - 5.0
    srv.RUN['running'] = True
    p = srv.progress_summary()
    assert p['done'] == 0 and p['pct'] == 0.0
    assert p['eta_s'] is None and p['rate_per_min'] == 0.0


# ---------------- app status summary ---------------------------------
def test_status_summary_error_when_last_run_failed():
    old_cache = dict(server.UPDATE_CACHE)
    server.UPDATE_CACHE.update(latest='0.0.1', err=None,
                               checked_at=time.time())
    server.RUN['last_exit'] = 1
    j = server.status_summary()
    server.RUN['last_exit'] = None
    server.UPDATE_CACHE.clear()
    server.UPDATE_CACHE.update(old_cache)
    assert j['level'] == 'error'
    assert j['text'] == 'status: error'


def test_status_summary_ok_and_update_levels():
    old_cache = dict(server.UPDATE_CACHE)
    server.RUN['last_exit'] = 0
    server.FORM['mode'] = 'mace'
    server.FORM['model'] = os.path.abspath(__file__)
    # no newer release -> ok
    server.UPDATE_CACHE.update(latest='0.0.1', err=None,
                               checked_at=time.time())
    ok = server.status_summary()
    # newer release -> update badge
    server.UPDATE_CACHE.update(latest='99.0.0', err=None,
                               checked_at=time.time())
    upd = server.status_summary()
    server.RUN['last_exit'] = None
    server.UPDATE_CACHE.clear()
    server.UPDATE_CACHE.update(old_cache)
    assert ok['level'] == 'ok', ok
    assert upd['level'] == 'update', upd
    assert upd['update_available'] is True


def test_version_compare_handles_two_digit_minor():
    assert server._ver_tuple('1.10.0') > server._ver_tuple('1.8.0')
    assert server._ver_tuple('v1.9') > server._ver_tuple('1.8.0')
    assert server._ver_tuple('1.8.0') == server._ver_tuple('1.8')


# ---------------- self-update batch file -----------------------------
def test_update_bat_kills_moves_and_relaunches():
    bat = server.build_update_bat(
        4242, r'C:\\p\\update_staging\\FePt-GUI.exe.new',
        r'C:\\p\\FePt-GUI.exe')
    assert 'taskkill /F /PID 4242' in bat
    assert 'move /Y "C:\\\\p\\\\update_staging\\\\FePt-GUI.exe.new" ' \
           '"C:\\\\p\\\\FePt-GUI.exe"' in bat
    assert 'start "" "C:\\\\p\\\\FePt-GUI.exe"' in bat
    assert bat.strip().endswith('del "%~f0"')


# ---------------- torch.compile switch (FEPT_COMPILE) ------------------
def test_compile_disabled_by_default_and_opt_in_via_env(monkeypatch):
    # GUI default (client-side fix): no torch.compile for engine runs
    monkeypatch.delenv('FEPT_COMPILE', raising=False)
    assert server.compile_enabled() is False
    for v in ('0', '', 'false', 'no'):
        monkeypatch.setenv('FEPT_COMPILE', v)
        assert server.compile_enabled() is False
    # working machines opt back in
    for v in ('1', 'true', 'yes', 'on'):
        monkeypatch.setenv('FEPT_COMPILE', v)
        assert server.compile_enabled() is True
