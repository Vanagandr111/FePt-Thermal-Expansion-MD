"""mcp_server: registry/dispatch contract (no GUI needed, http mocked).

Catches the classic MCP bug: a tool registered in TOOLS but missing from
call_tool (agent gets 'unknown tool'), or vice versa.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import mcp_server as m  # noqa: E402


def _default_args(tool):
    """Minimal valid arguments for a tool schema (fill required props)."""
    args = {}
    for key, spec in (tool['inputSchema'].get('properties') or {}).items():
        if 'enum' in spec:
            args[key] = spec['enum'][0]
        elif spec.get('type') == 'integer':
            args[key] = 4
        elif spec.get('type') == 'number':
            args[key] = 0.5
        elif spec.get('type') == 'boolean':
            args[key] = False
        elif isinstance(spec.get('type'), list):     # e.g. ['number','null']
            args[key] = None
        else:
            args[key] = 'x'
    return args


def test_tool_names_unique():
    names = [t['name'] for t in m.TOOLS]
    assert len(names) == len(set(names))
    assert all(n.startswith('gui_') for n in names)


def test_every_tool_has_dispatch_branch(monkeypatch):
    """Registering a tool without wiring it must fail the test."""
    seen = []
    monkeypatch.setattr(m, 'require_gui', lambda: None)

    def fake_http(method, path, body=None, timeout=30):
        seen.append(path)
        # keys accessed by various branches: ['form'], ['elements'], ...
        return {'form': {}, 'elements': [], 'ok': True, 'path': path}

    monkeypatch.setattr(m, 'http', fake_http)
    for tool in m.TOOLS:
        result = m.call_tool(tool['name'], _default_args(tool))
        assert isinstance(result, dict)
    assert len(seen) == len(m.TOOLS)


def test_no_stray_dispatch_branches():
    """Every 'gui_*' branch name in call_tool must be in TOOLS."""
    import re
    src = open(m.__file__, encoding='utf-8').read()
    branch_names = set(re.findall(r"name == '(gui_[a-z_]+)'", src))
    registered = {t['name'] for t in m.TOOLS}
    assert branch_names <= registered, registered ^ branch_names
    assert registered <= branch_names, registered ^ branch_names


def test_new_agents_tools_present():
    registered = {t['name'] for t in m.TOOLS}
    for need in ('gui_metrics', 'gui_estimate', 'gui_calibrate',
                 'gui_structure', 'gui_add_potential', 'gui_get_elements',
                 'gui_save_element', 'gui_delete_element'):
        assert need in registered, need


def test_form_keys_include_seed():
    assert 'seed' in m.form_keys({'seed': 7, 'grid': 4})
    assert m.form_keys({'seed': 7}) == {'seed': 7}
    # unknown keys are dropped
    assert 'bogus' not in m.form_keys({'bogus': 1})


def test_set_form_and_start_run_schemas_allow_seed():
    by_name = {t['name']: t for t in m.TOOLS}
    for tool in ('gui_set_form', 'gui_start_run'):
        props = by_name[tool]['inputSchema']['properties']
        assert 'seed' in props, tool


def test_estimate_tool_override_goes_through_post(monkeypatch):
    """With arguments -> POST {form:...}; without -> GET."""
    monkeypatch.setattr(m, 'require_gui', lambda: None)
    calls = []
    monkeypatch.setattr(
        m, 'http',
        lambda method, path, body=None, timeout=30:
            calls.append((method, path, body)) or {'ok': True})
    m.call_tool('gui_estimate', {'grid': 8, 'prod': 5000})
    assert calls[-1][0] == 'POST'
    assert calls[-1][2]['form'] == {'grid': 8, 'prod': 5000}
    m.call_tool('gui_estimate', {})
    assert calls[-1][0] == 'GET'


def test_structure_tool_strips_positions_by_default(monkeypatch):
    monkeypatch.setattr(m, 'require_gui', lambda: None)
    big = {'ok': True, 'natoms': 256, 'positions': [[0, 0, 0]],
           'types': [1], 'cell': [[1, 0, 0]], 'box': [[0, 1]],
           'lengths': [14.4, 14.4, 14.4]}
    monkeypatch.setattr(m, 'http', lambda *a, **k: dict(big))
    out = m.call_tool('gui_structure', {})
    assert 'positions' not in out and 'lengths' in out
    out2 = m.call_tool('gui_structure', {'include_positions': True})
    assert 'positions' in out2
