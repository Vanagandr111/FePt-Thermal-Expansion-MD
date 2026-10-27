# -*- coding: utf-8 -*-
"""install_lib / _pip_stream: живой вывод, честная плашка, таймаут.

Регресс бага заказчика v2.2.2: pip ставил 2.8 ГБ torch, ВЕСЬ вывод
прятался в capture_output (показывались 4 строки stdout / 400 символов
stderr), а плашка писала «pip install завершён» ДАЖЕ при ошибке и
таймауте — failed install выглядел успехом.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import server as srv


class _FakeManifest(object):
    def __init__(self):
        self.calls = []

    def __call__(self, name, info):
        self.calls.append((name, info))


def _env(monkeypatch, tmp_path, body):
    """fake pip module on PYTHONPATH: `python -m pip install ...` runs it."""
    (tmp_path / 'pip.py').write_text(body, encoding='utf-8')
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    monkeypatch.setattr(srv, 'ensure_engine_python',
                        lambda: (sys.executable, False))
    fake = _FakeManifest()
    monkeypatch.setattr(srv, 'manifest_note', fake)
    return fake


def test_pip_stream_full_output_and_total(monkeypatch, tmp_path):
    """Every pip line lands in the console (incl. >400-char stderr),
    the wheel size becomes the bar total, rc is the real verdict."""
    _env(monkeypatch, tmp_path, (
        "import sys\n"
        "sys.stderr.write('Collecting torch\\n')\n"
        "sys.stderr.write('  Downloading torch-2.11.0+cu128-cp314.whl "
        "(2.77 GB)\\n')\n"
        "sys.stderr.write('Installing collected packages: torch\\n')\n"
        "sys.stderr.write('ERROR: ' + 'x' * 500 + '\\n')\n"
        "sys.stderr.flush()\n"
        "sys.exit(3)\n"))
    srv.INSTALL_SPECS['fakepkg'] = ['fakepkg']
    monkeypatch.setattr(srv, 'PIP_TIMEOUT', 120)
    srv.RUN['lines'][:] = []
    try:
        srv.install_lib('fakepkg')
        lines = srv.RUN['lines']
        assert any('Collecting torch' in l for l in lines), lines[-10:]
        assert any(l.startswith('[pip] ERROR: ') and len(l) > 400
                   for l in lines), 'long stderr was cut'
        assert srv.DL['total'] == int(2.77e9), srv.DL['total']
        assert srv.DL['mode'] == 'bytes'
        assert any('pip finished: rc=3' in l for l in lines), lines[-5:]
        assert srv.DL['done_msg'].startswith('УСТАНОВКА НЕ УДАЛАСЬ: fakepkg')
        assert '(код 3)' in srv.DL['done_msg']
        assert srv.DL['active'] is False
    finally:
        srv.INSTALL_SPECS.pop('fakepkg', None)


def test_install_timeout_honest_message(monkeypatch, tmp_path):
    """A hung pip is killed after PIP_TIMEOUT and the bar says
    ПРЕРВАНА (the old code said 'завершён' after the kill)."""
    _env(monkeypatch, tmp_path, (
        "import sys, time\n"
        "sys.stderr.write('Collecting torch\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(60)\n"))
    monkeypatch.setattr(srv, 'PIP_TIMEOUT', 2)
    srv.INSTALL_SPECS['fakepkg'] = ['fakepkg']
    srv.RUN['lines'][:] = []
    try:
        t0 = time.time()
        srv.install_lib('fakepkg')
        assert time.time() - t0 < 30
        assert any('pip killed: exceeded' in l for l in srv.RUN['lines'])
        assert srv.DL['done_msg'].startswith('УСТАНОВКА ПРЕРВАНА: fakepkg')
        assert 'лимит' in srv.DL['done_msg']
        assert srv.DL['active'] is False
    finally:
        srv.INSTALL_SPECS.pop('fakepkg', None)


def test_torch_mirror_chain_and_success_msg(monkeypatch):
    """Failed mirror N -> next mirror; success writes завершена + manifest."""
    calls = []

    def fake_stream(py, spec_args, tag='pip'):
        calls.append(list(spec_args))
        return 1 if len(calls) == 1 else 0

    monkeypatch.setattr(srv, '_pip_stream', fake_stream)
    monkeypatch.setattr(srv, 'ensure_engine_python',
                        lambda: (sys.executable, False))
    monkeypatch.setattr(srv, '_triton_present', lambda py: True)
    fake = _FakeManifest()
    monkeypatch.setattr(srv, 'manifest_note', fake)
    srv.RUN['lines'][:] = []
    srv.install_lib('torch')
    assert len(calls) == 2, calls  # 1st mirror failed, 2nd succeeded
    joined = '\n'.join(srv.RUN['lines'])
    assert 'mirror 1 failed (rc=1)' in joined
    assert 'pip OK: torch' in joined
    assert srv.DL['done_msg'].startswith('установка завершена: torch')
    assert fake.calls and fake.calls[0][0] == 'torch'
    assert fake.calls[0][1]['index'] == srv.TORCH_MIRRORS[1][2]
    assert srv.DL['active'] is False


def test_all_mirrors_fail_message(monkeypatch):
    """Every mirror down -> честная плашка с кодом последней попытки."""
    monkeypatch.setattr(srv, '_pip_stream', lambda py, a, tag='pip': 1)
    monkeypatch.setattr(srv, 'ensure_engine_python',
                        lambda: (sys.executable, False))
    monkeypatch.setattr(srv, 'manifest_note', _FakeManifest())
    srv.RUN['lines'][:] = []
    srv.install_lib('torch')
    assert srv.DL['done_msg'].startswith('УСТАНОВКА НЕ УДАЛАСЬ: torch')
    assert '(код 1)' in srv.DL['done_msg']
    assert srv.DL['active'] is False
