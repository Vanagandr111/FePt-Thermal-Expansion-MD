# -*- coding: utf-8 -*-
"""Fast tests: element hint encyclopedia, exact Pt lattice, run progress
card math, app status summary and the self-update batch file."""
import os
import subprocess
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


# ---------------- installer must ship triton ---------------------------
def test_gui_installer_ships_triton_spec():
    # customer machines install deps ONLY from this tab: without this
    # entry their triton stayed missing ('dead') and compile never worked
    spec = server.INSTALL_SPECS.get('triton')
    assert spec, 'triton missing from INSTALL_SPECS'
    if os.name == 'nt':
        assert spec == ['triton-windows']   # fork with ptxas.exe
    # the deps probe must report triton AND the ptxas binary
    assert "'triton'" in server._PROBE_CODE
    assert 'ptxas' in server._PROBE_CODE


def test_triton_present_helper_sees_engine_triton():
    # True in our engine venv (triton-windows installed via bootstrap)
    assert server._triton_present(sys.executable) is True


# ---- v2.4.8: bar must move INSIDE the first point --------------------
def test_progress_summary_counts_current_point_steps():
    """[PROG] markers from the engine fill the gap before the first
    point finishes - the bar sat at 0% for the whole pre-equilibration
    (customer complaint)."""
    srv = server
    old = {k: srv.RUN.get(k) for k in
           ('plan_total', 'done_points', 'start', 'running',
            'last_exit', 'prog_step', 'prog_total', 'prog_phase')}
    try:
        srv.RUN['plan_total'] = 4
        srv.RUN['done_points'] = 0
        srv.RUN['start'] = time.time() - 60.0
        srv.RUN['running'] = True
        srv.RUN['last_exit'] = None
        srv.RUN['prog_phase'] = 'pre-eq'
        srv.RUN['prog_step'] = 300
        srv.RUN['prog_total'] = 600          # half of the first point
        p = srv.progress_summary()
        assert p['done'] == 0
        assert abs(p['pct'] - 12.5) < 0.01   # 0.5 of 4 points
        assert p['eta_s'] is not None        # ETA exists before point 1
        assert p['prog_phase'] == 'pre-eq'
        assert p['prog_step'] == 300 and p['prog_total'] == 600
        # a finished point resets the in-point position
        srv.RUN['prog_step'] = 0
        srv.RUN['prog_total'] = 0
        p2 = srv.progress_summary()
        assert p2['pct'] == 0.0
    finally:
        srv.RUN.update(old)


# ---- v2.4.8: deps probe must not block the HTTP thread ---------------
def test_deps_stale_cache_answers_now_without_probe(monkeypatch):
    """A stale cache is served immediately and refreshed in the
    background: the fresh probe imports torch (~60 s) and used to hang
    the deps tab / drop the connection (customer)."""
    old_cache = dict(server._DEPS_CACHE)
    old_bg = dict(server._DEPS_BG)
    calls = {'probe': 0, 'bg': 0}
    snapshot = {'marker': 'previous-snapshot'}

    def _no_probe(eng):
        calls['probe'] += 1
        return {}

    def _no_bg():
        calls['bg'] += 1

    monkeypatch.setattr(server, '_probe_libs', _no_probe)
    monkeypatch.setattr(server, '_deps_refresh_bg', _no_bg)
    try:
        server._DEPS_CACHE['data'] = snapshot
        server._DEPS_CACHE['t'] = 0.0         # long stale
        out = server.collect_deps(refresh=False)
        assert out is snapshot                # served the old snapshot
        assert calls['probe'] == 0            # NO heavy probe inline
        assert calls['bg'] == 1               # refresh moved to background
    finally:
        server._DEPS_CACHE.clear()
        server._DEPS_CACHE.update(old_cache)
        server._DEPS_BG.clear()
        server._DEPS_BG.update(old_bg)


# ---- v2.4.8: `cmd /c start` must not linger --------------------------
def test_reap_cmd_kills_lingering_cmd():
    """The browser opener stayed alive after the URL was handed over
    and kept the install folder undeletable (customer)."""

    class FakeProc:
        def __init__(self):
            self.killed = False

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd='cmd', timeout=timeout)

        def kill(self):
            self.killed = True

    p = FakeProc()
    server._reap_cmd(p, limit=0.01)
    assert p.killed is True

    class OkProc:
        def __init__(self):
            self.killed = False

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    q = OkProc()
    server._reap_cmd(q, limit=0.01)
    assert q.killed is False                   # exits on its own: leave it
