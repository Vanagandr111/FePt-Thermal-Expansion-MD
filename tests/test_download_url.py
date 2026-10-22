# -*- coding: utf-8 -*-
"""download_url: releases DL['active'] on failure and retries.

Regression: a WinError 10054 reset used to leave DL['active']=True
forever -> every later download answered "another transfer is already
active" until a server restart (reproduced live on the release exe).
"""
import io
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))


def _load_server():
    import server
    return server


class _FakeResp(object):
    def __init__(self, payload, fail_after=None):
        self._payload = payload
        self._pos = 0
        self._fail_after = fail_after
        self.headers = {'Content-Length': str(len(payload))}

    def read(self, n=-1):
        if self._fail_after is not None and self._pos >= self._fail_after:
            raise OSError('[WinError 10054] connection reset')
        if self._pos >= len(self._payload):
            return b''
        chunk = self._payload[self._pos:self._pos + (n if n > 0 else 1024)]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_url_releases_active_flag_and_retries(monkeypatch, tmp_path):
    srv = _load_server()
    dest = str(tmp_path / 'm.model')

    calls = {'n': 0}

    def fake_urlopen(req, timeout=None):
        calls['n'] += 1
        if calls['n'] == 1:
            # first attempt dies mid-stream like the client's 10054
            return _FakeResp(b'X' * 10, fail_after=0)
        return _FakeResp(b'payload-bytes')

    monkeypatch.setattr(srv.urllib.request, 'urlopen', fake_urlopen)
    # keep the test fast: no real sleeps between retries
    monkeypatch.setattr(srv.time, 'sleep', lambda s: None)

    srv.DL['active'] = False
    out = srv.download_url('https://example.invalid/m.model', dest, 'm.model')

    assert calls['n'] == 2, 'first failure must be retried'
    assert io.open(out, 'rb').read() == b'payload-bytes'
    assert srv.DL['active'] is False, 'active must be False after success'


def test_download_url_gives_up_but_unblocks_the_ui(monkeypatch, tmp_path):
    srv = _load_server()
    dest = str(tmp_path / 'm.model')

    def fake_urlopen(req, timeout=None):
        raise OSError('[WinError 10054] connection reset')

    monkeypatch.setattr(srv.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(srv.time, 'sleep', lambda s: None)

    srv.DL['active'] = False
    try:
        srv.download_url('https://example.invalid/m.model', dest, 'm.model')
        raised = False
    except OSError:
        raised = True

    assert raised, 'final error must propagate to the caller'
    assert srv.DL['active'] is False, (
        'after a dead transfer the UI must NOT stay locked in '
        '"another transfer is already active"')
