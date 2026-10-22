"""Engine interpreter resolution — the frozen-vs-dev contract.

Frozen builds must NEVER resolve to themselves (that relaunches the exe
and hangs the deps tab); dev mode must resolve to its own python."""
import os
import sys

import pytest

import server as gui


@pytest.fixture
def proj(tmp_path, monkeypatch):
    # isolate ALL resolution roots: the new multi-root search checks
    # PROJ, cwd, GUI_DIR and its parent - a stray .venv-mace in the
    # real cwd would leak into the test
    monkeypatch.setattr(gui, 'PROJ', str(tmp_path))
    monkeypatch.setattr(gui, 'GUI_DIR', str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv('FEPT_PYTHON', '/opt/custom/python')
    assert gui.resolve_python() == '/opt/custom/python'


def test_dev_mode_uses_own_interpreter(monkeypatch):
    monkeypatch.delenv('FEPT_PYTHON', raising=False)
    monkeypatch.setattr(gui, 'FROZEN', False)
    assert gui.resolve_python() == sys.executable


def test_frozen_without_any_venv_returns_none(proj, monkeypatch):
    monkeypatch.delenv('FEPT_PYTHON', raising=False)
    monkeypatch.setattr(gui, 'FROZEN', True)
    assert gui.resolve_python() is None


def test_frozen_finds_dev_venv_next_to_exe(proj, monkeypatch):
    monkeypatch.delenv('FEPT_PYTHON', raising=False)
    monkeypatch.setattr(gui, 'FROZEN', True)
    py = proj / '.venv-mace' / 'Scripts' / 'python.exe'
    py.parent.mkdir(parents=True)
    py.write_text('x')
    assert gui.resolve_python() == str(py)


def test_frozen_exe_in_dist_finds_venv_one_level_up(proj, monkeypatch):
    """Release layout: exe in dist/, .venv-mace in the project root."""
    monkeypatch.delenv('FEPT_PYTHON', raising=False)
    monkeypatch.setattr(gui, 'FROZEN', True)
    dist = proj / 'dist'
    dist.mkdir()
    monkeypatch.setattr(gui, 'PROJ', str(dist))
    monkeypatch.setattr(gui, 'GUI_DIR', str(dist))
    monkeypatch.chdir(dist)
    py = proj / '.venv-mace' / 'Scripts' / 'python.exe'
    py.parent.mkdir(parents=True)
    py.write_text('x')
    assert gui.resolve_python() == str(py)


def test_frozen_prefers_libs_venv_over_dev_venv(proj, monkeypatch):
    monkeypatch.delenv('FEPT_PYTHON', raising=False)
    monkeypatch.setattr(gui, 'FROZEN', True)
    for rel in ('libs/venv/Scripts/python.exe', '.venv-mace/Scripts/python.exe'):
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('x')
    assert gui.resolve_python() == str(proj / 'libs' / 'venv' / 'Scripts' / 'python.exe')


def test_probe_refuses_none():
    out = gui._probe_libs(None)
    assert 'no engine interpreter' in out['error']


def test_probe_refuses_self_only_when_frozen(monkeypatch):
    monkeypatch.setattr(gui, 'FROZEN', True)
    out = gui._probe_libs(sys.executable)
    assert 'GUI itself' in out['error']
    # dev mode: same interpreter is the normal engine, must NOT refuse
    monkeypatch.setattr(gui, 'FROZEN', False)
    runs = []

    class _CP:
        stdout = b'PROBE_JSON:{"ok": 1}'
        stderr = b''

    def fake_run(cmd, **kw):
        runs.append(cmd)
        return _CP()

    monkeypatch.setattr(gui.subprocess, 'run', fake_run)
    out = gui._probe_libs(sys.executable)
    assert runs and runs[0][0] == sys.executable
    assert out.get('ok') == 1
