"""Shared form state: the browser and the MCP agent edit the SAME dict,
and every agent touch is logged into the console stream."""
import server as gui


def _reset(monkeypatch):
    monkeypatch.setattr(gui, 'FORM',
                        {'mode': 'mace', 'model': '', 'device': 'cuda',
                         'comp': 0.5, 'grid': 4, 'temps': '300 1200',
                         'eq': 500, 'prod': 1000})
    with gui.COND:
        gui.RUN['lines'] = []
        gui.RUN['state_n'] = 0


def test_state_update_merges_only_known_keys(monkeypatch):
    _reset(monkeypatch)
    gui.state_update({'comp': 0.75, 'bogus': 1}, source='agent')
    assert gui.FORM['comp'] == 0.75
    assert 'bogus' not in gui.FORM


def test_agent_touch_is_logged_and_bumps_state(monkeypatch):
    _reset(monkeypatch)
    n0 = gui.RUN['state_n']
    gui.state_update({'mode': 'lammps'}, source='agent')
    assert gui.FORM['mode'] == 'lammps'
    assert gui.RUN['state_n'] == n0 + 1
    with gui.COND:
        assert '[agent] mode <- lammps' in gui.RUN['lines']


def test_ui_change_does_not_log_agent_line(monkeypatch):
    _reset(monkeypatch)
    gui.state_update({'eq': 700}, source='ui')
    with gui.COND:
        assert not any(l.startswith('[agent]') for l in gui.RUN['lines'])
    assert gui.FORM['eq'] == 700


def test_noop_update_is_silent(monkeypatch):
    _reset(monkeypatch)
    n0 = gui.RUN['state_n']
    gui.state_update({'eq': gui.FORM['eq']}, source='agent')
    assert gui.RUN['state_n'] == n0


def test_scan_potentials_indexes_by_extension(tmp_path, monkeypatch):
    gpu = tmp_path / 'gpu'
    cpu = tmp_path / 'cpu'
    gpu.mkdir()
    cpu.mkdir()
    (gpu / 'a.model').write_text('x')
    (gpu / 'b.pt').write_text('x')
    (gpu / 'notes.txt').write_text('skip me')
    (cpu / 'c.eam.alloy').write_text('x')
    (cpu / 'd.meam').write_text('x')
    monkeypatch.setattr(gui, 'GPU_DIR', str(gpu))
    monkeypatch.setattr(gui, 'CPU_DIR', str(cpu))
    out = gui.scan_potentials()
    assert [p['name'] for p in out['gpu']] == ['a.model', 'b.pt']
    assert [p['name'] for p in out['cpu']] == ['c.eam.alloy', 'd.meam']


def test_scan_potentials_handles_missing_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, 'GPU_DIR', str(tmp_path / 'nope'))
    monkeypatch.setattr(gui, 'CPU_DIR', str(tmp_path / 'nada'))
    out = gui.scan_potentials()
    assert out == {'gpu': [], 'cpu': []}
