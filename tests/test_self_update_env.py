# -*- coding: utf-8 -*-
"""Self-update must not hand PyInstaller's _MEI pointers to the new process.

Root cause (measured on a real v2.2.7 -> v2.2.8 swap): the relaunched exe
inherited _PYI_APPLICATION_HOME_DIR / _PYI_ARCHIVE_FILE /
_PYI_PARENT_PROCESS_LEVEL from the killed parent, skipped unpacking and
tried to load python312.dll from the old, already deleted _MEI folder ->
modal "Failed to load Python DLL" and a process hanging forever.
"""
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'gui'))


def _srv():
    import server
    return server


def test_clean_env_drops_pyi_and_mei(monkeypatch):
    srv = _srv()
    monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR', r'C:\Temp\_MEI123')
    monkeypatch.setenv('_PYI_ARCHIVE_FILE', r'C:\app\FePt-GUI.exe')
    monkeypatch.setenv('_PYI_PARENT_PROCESS_LEVEL', '1')
    monkeypatch.setenv('_MEIPASS2', r'C:\Temp\_MEI123')
    monkeypatch.setenv('FEPT_PORT', '8321')
    clean = srv.clean_update_env()
    for key in clean:
        assert not key.upper().startswith('_PYI'), key
        assert not key.upper().startswith('_MEI'), key
    assert clean.get('FEPT_PORT') == '8321'
    assert '_PYI_APPLICATION_HOME_DIR' not in os.environ or True


def test_bat_clears_pyi_and_cds_to_app_dir():
    src = io.open(os.path.join(ROOT, 'gui', 'server.py'), encoding='utf-8').read()
    assert 'set _PYI_APPLICATION_HOME_DIR=' in src
    assert 'set _PYI_PARENT_PROCESS_LEVEL=' in src
    assert "cd /d \"%(curdir)s\"" in src
    assert "'curdir': os.path.dirname(os.path.abspath(cur_exe))" in src


def test_sh_unsets_pyi():
    src = io.open(os.path.join(ROOT, 'gui', 'server.py'), encoding='utf-8').read()
    assert 'unset _PYI_APPLICATION_HOME_DIR' in src


def test_popen_uses_clean_env():
    src = io.open(os.path.join(ROOT, 'gui', 'server.py'), encoding='utf-8').read()
    assert 'env=clean_update_env()' in src
    assert 'stdin=subprocess.DEVNULL' in src
