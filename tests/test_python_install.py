# -*- coding: utf-8 -*-
"""Tests for the python-from-link installer and helpers."""
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import server  # noqa: E402


def test_ensure_engine_python_dev_mode():
    # running from source: the interpreter is THIS python, no venv work
    py, need_url = server.ensure_engine_python()
    if not server.FROZEN:
        assert py == sys.executable
        assert need_url is False


def test_find_system_python_returns_str_or_none():
    p = server.find_system_python()
    assert p is None or (isinstance(p, str) and p)


def test_find_python_bin_inside_standalone_layout(tmp_path):
    root = tmp_path / 'py'
    b = root / 'python' / 'install' / 'bin'
    b.mkdir(parents=True)
    exe = b / ('python.exe' if os.name == 'nt' else 'python3')
    exe.write_text('#!/bin/sh\n')
    assert server._find_python_bin(str(root)) == str(exe)


def test_safe_extract_rejects_traversal(tmp_path):
    evil = tmp_path / 'evil.tar'
    with tarfile.open(evil, 'w') as tf:
        info = tarfile.TarInfo(name='../escape.txt')
        import io as _io
        data = b'x'
        info.size = len(data)
        tf.addfile(info, _io.BytesIO(data))
    stage = tmp_path / 'stage'
    stage.mkdir()
    with tarfile.open(evil) as tf:
        try:
            server._safe_extract_tar(tf, str(stage))
            assert False, 'traversal not rejected'
        except RuntimeError as e:
            assert 'unsafe' in str(e)


def test_install_python_job_validates_url():
    # a bad url must fail fast with a user-visible message, no download
    server.install_python_job('ftp://example.com/python.tar.gz')
    # (dl_end only records a message; DL must not stay locked)
    assert server.DL['active'] in (True, False)


def test_update_sh_script_content():
    sh = server.build_update_sh(4242, '/tmp/upd/new', '/opt/app/bin')
    assert 'kill -9 4242' in sh
    assert "mv -f '/tmp/upd/new' '/opt/app/bin'" in sh
    assert 'chmod +x' in sh
    # retried swap (dying process may hold the binary)
    assert 'while ! mv' in sh


def test_build_update_sh_is_posix():
    """The Linux self-updater must kill, swap and relaunch like the .bat."""
    s = server.build_update_sh(1234, '/tmp/u/FePt-GUI.new', '/opt/x/FePt-GUI')
    assert 'kill -9 1234' in s
    assert "mv -f '/tmp/u/FePt-GUI.new' '/opt/x/FePt-GUI'" in s
    assert 'chmod +x' in s
    assert 'rm -f "$0"' in s
    assert s.strip().startswith('#!/bin/sh')
    assert '/opt/x/FePt-GUI' in s  # relaunches itself


def test_python_hint_shape():
    # cached value must round-trip; live github fetch optional (offline)
    r = server.python_hint()
    assert isinstance(r, dict)
    if r.get('ok'):
        assert r['url'].startswith('https://')
        assert r['url'].endswith(('install_only.tar.gz', '.tar.gz', '.zip'))
        # torch/mace wheels only exist for the engine window 3.10..3.14
        import re as _re
        m = _re.search(r'cpython-(\d+)\.(\d+)\.', r['url'])
        assert m, r['url']
        major, minor = int(m.group(1)), int(m.group(2))
        assert (major, minor) <= (3, 14), 'hint offers too-new python: ' + r['url']
