"""MCP server for the FePt GUI — agent-side control, stdlib only.

Lets an AI agent drive the *running* web GUI the way a human would:
every tool call goes through the GUI's own HTTP API, so the open
browser visibly reacts (fields pulse, console prints [agent] lines,
runs start with the AGENT marker).

Transport: MCP stdio (newline-delimited JSON-RPC 2.0).
Wiring (Hermes config.yaml):

    mcp_servers:
      fept_gui:
        command:
          - "C:/.../.venv-mace/Scripts/python.exe"
          - "D:/projects/Nikolay/gui/mcp_server.py"
        env:
          FEPT_GUI_URL: "http://127.0.0.1:8321"

The GUI itself must be running:  python gui/server.py
All tools fail with a clear message if it is not.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get('FEPT_GUI_URL', 'http://127.0.0.1:8321')
SERVER_NAME = 'fept-gui'
SERVER_VERSION = '1.0.0'
PROTOCOL = '2024-11-05'

TOOLS = [
    {
        'name': 'gui_status',
        'description': (
            'Current GUI state: whether a run is active, the shared form '
            '(mode/model/device/comp/grid/temps/eq/prod), output folder, '
            'console tail size. Call first to see what the GUI shows.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_get_form',
        'description': 'Read the GUI form values exactly as displayed.',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_set_form',
        'description': (
            'Set GUI form fields. The open GUI updates LIVE: the changed '
            'field pulses blue and the console prints "[agent] key <- value". '
            'Only provided keys change. Keys: mode (mace|lammps), model '
            '(path from potentials/gpu), device (cuda|cpu), comp (0..1), '
            'grid (int), temps ("300 1200"), eq (int), prod (int), '
            'seed (int, RNG seed of the NPT init).'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'mode': {'type': 'string', 'enum': ['mace', 'lammps']},
                'model': {'type': 'string'},
                'device': {'type': 'string', 'enum': ['cuda', 'cpu']},
                'comp': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'grid': {'type': 'integer', 'minimum': 2, 'maximum': 12},
                'temps': {'type': 'string',
                          'description': 'space-separated temperatures'},
                'eq': {'type': 'integer'},
                'prod': {'type': 'integer'},
                'seed': {'type': 'integer',
                         'description': 'RNG seed (reproduces the run)'},
            },
        },
    },
    {
        'name': 'gui_list_potentials',
        'description': (
            'Index model/force-field files: potentials/gpu (MACE weights) '
            'and potentials/cpu (EAM/MEAM).'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_check_dependencies',
        'description': (
            'Run the GUI dependency check: python/torch(+CUDA)/mace/ase/'
            'numpy versions, LAMMPS binary presence, folder layout. '
            'refresh=false uses the cached result.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'refresh': {'type': 'boolean', 'default': False}},
        },
    },
    {
        'name': 'gui_start_run',
        'description': (
            'Start an MD run from the GUI. Optional keys override the form '
            'for this run (same keys as gui_set_form); defaults come from '
            'the current form. The GUI console shows "[AGENT] === start ...". '
            'Fails if a run is already active.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'mode': {'type': 'string', 'enum': ['mace', 'lammps']},
                'model': {'type': 'string'},
                'device': {'type': 'string', 'enum': ['cuda', 'cpu']},
                'comp': {'type': 'number'},
                'grid': {'type': 'integer'},
                'temps': {'type': 'string'},
                'eq': {'type': 'integer'},
                'prod': {'type': 'integer'},
                'seed': {'type': 'integer'},
            },
        },
    },
    {
        'name': 'gui_stop_run',
        'description': 'Terminate the currently running MD process in the GUI.',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_read_log',
        'description': (
            'Tail of the GUI console: last N log lines plus running flag. '
            'Includes [agent]/[UI]/[AGENT] markers of who did what.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'last': {'type': 'integer', 'default': 40}},
        },
    },
    {
        'name': 'gui_get_results',
        'description': (
            'Parsed results of a run folder: a(T) series per composition '
            '(T, a_mean, std, runtime) and CTE table (alpha_fit in 1/K, '
            'R2, segments). Defaults to the newest run output.'),
        'inputSchema': {
            'type': 'object',
            'properties': {'outdir': {'type': 'string'}},
        },
    },
    {
        'name': 'gui_open_results_folder',
        'description': (
            'Open the current results folder in the OS file manager '
            '(visible to the human at the machine).'),
        'inputSchema': {
            'type': 'object',
            'properties': {'outdir': {'type': 'string'}},
        },
    },
    {
        'name': 'gui_download_lammps',
        'description': (
            'Ask the GUI to download+install the official LAMMPS binary '
            'into lammps/ (progress appears in the GUI console). Long op; '
            'poll gui_read_log.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_download_model',
        'description': (
            'Ask the GUI to fetch an extra MACE model into potentials/gpu/. '
            'Poll gui_read_log for progress.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'name': {
                    'type': 'string',
                    'enum': ['mace-mpa-0-medium.model',
                             'mace-mp-0b3-medium.model',
                             'mace-large-0b2.model'],
                },
            },
            'required': ['name'],
        },
    },
    {
        'name': 'gui_metrics',
        'description': (
            'Live system snapshot as the header gauges show it: CPU %, '
            'RAM used/total, VRAM used/total, GPU util/temp/power, each '
            'with a traffic-light level (ok/warn/bad) against thresholds '
            '(70/85 %). Use to check whether the machine is struggling.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_estimate',
        'description': (
            'Pre-run estimate: seconds, VRAM vs the card, RAM, per-step '
            'ms, confidence (calibrated/extrapolated/guess) for a form. '
            'Arguments are OPTIONAL: without them it estimates the form '
            'currently shown in the GUI; with them it answers '
            '"what if grid=8, prod=5000?" WITHOUT touching the form.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'mode': {'type': 'string', 'enum': ['mace', 'lammps']},
                'device': {'type': 'string', 'enum': ['cuda', 'cpu']},
                'grid': {'type': 'integer', 'minimum': 1},
                'temps': {'type': 'string'},
                'eq': {'type': 'integer'},
                'prod': {'type': 'integer'},
            },
        },
    },
    {
        'name': 'gui_calibrate',
        'description': (
            'Recalibrate the time/memory estimator on THIS machine: '
            'force+stress calls at 32/108/256 atoms (no MD), ~3-5 min, '
            'profile saved to data/estim_profile.json. Long op; poll '
            'gui_read_log for "[calib]" lines.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_structure',
        'description': (
            'Structure of the newest .lmp file (current run folder, else '
            'data/): atom counts by element, cell lengths, x_Pt, file '
            'name. include_positions=true also returns all [x,y,z] '
            '(large: ~10 KB per 256 atoms).'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'include_positions': {'type': 'boolean', 'default': False},
                'outdir': {'type': 'string'},
            },
        },
    },
    {
        'name': 'gui_add_potential',
        'description': (
            'Import a potential file that already exists on this machine '
            '(path readable by the GUI server) into potentials/gpu or '
            'potentials/cpu. Same sanitising as the browser dropzone: '
            'extension decides the folder, name is sanitised, write is '
            'atomic. Returns the fresh indexing.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string',
                         'description': 'absolute path of the file to import'},
            },
            'required': ['path'],
        },
    },
    {
        'name': 'gui_get_elements',
        'description': (
            'List the element/alloy registry (symbol, seed lattice '
            'constant lc, label) used by structure generation.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'gui_save_element',
        'description': (
            'Add or update one element in the registry (upsert by '
            'symbol, case-insensitive). symbol like Fe/Cu/Pt is required; '
            'lc (Angstrom, 0.5..100) and label (max 80 chars) optional. '
            'Invalid data returns ok:false with the reason, nothing saved.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'symbol': {'type': 'string'},
                'lc': {'type': ['number', 'null'],
                       'description': 'seed lattice constant, A'},
                'label': {'type': 'string'},
            },
            'required': ['symbol'],
        },
    },
    {
        'name': 'gui_delete_element',
        'description': 'Remove one element from the registry by symbol.',
        'inputSchema': {
            'type': 'object',
            'properties': {'symbol': {'type': 'string'}},
            'required': ['symbol'],
        },
    },
]


# ------------------------------------------------------------- HTTP glue --
def http(method, path, body=None, timeout=30):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def gui_alive():
    try:
        http('GET', '/api/form', timeout=5)
        return True
    except Exception:
        return False


def require_gui():
    if not gui_alive():
        raise RuntimeError(
            'The FePt web GUI is not running. Start it first: '
            '"<venv>/python.exe gui/server.py" in D:/projects/Nikolay '
            '(web UI at ' + BASE + ').')


def form_keys(args):
    keys = ('mode', 'model', 'device', 'comp', 'grid', 'temps', 'eq', 'prod',
            'seed')
    return {k: args[k] for k in keys if k in args and args[k] is not None}


# ------------------------------------------------------------ tool calls --
def call_tool(name, args):
    require_gui()
    if name == 'gui_status':
        form = http('GET', '/api/form')
        return form
    if name == 'gui_get_form':
        return http('GET', '/api/form')['form']
    if name == 'gui_set_form':
        upd = form_keys(args)
        if not upd:
            return {'ok': False, 'error': 'no known keys in arguments'}
        return http('POST', '/api/form',
                    {'form': upd, 'source': 'agent'})
    if name == 'gui_list_potentials':
        return http('GET', '/api/potentials')
    if name == 'gui_check_dependencies':
        refresh = 1 if args.get('refresh') else 0
        return http('GET', '/api/deps?refresh=%d' % refresh, timeout=120)
    if name == 'gui_start_run':
        body = form_keys(args)
        body['source'] = 'agent'
        return http('POST', '/api/run', body)
    if name == 'gui_stop_run':
        return http('POST', '/api/stop', {})
    if name == 'gui_read_log':
        n = int(args.get('last', 40))
        return http('GET', '/api/log?last=%d' % n)
    if name == 'gui_get_results':
        path = '/api/results'
        if args.get('outdir'):
            import urllib.parse
            path += '?outdir=' + urllib.parse.quote(args['outdir'], safe='')
        return http('GET', path, timeout=30)
    if name == 'gui_open_results_folder':
        body = {'source': 'agent'}
        if args.get('outdir'):
            body['path'] = args['outdir']
        return http('POST', '/api/open_folder', body)
    if name == 'gui_download_lammps':
        return http('POST', '/api/download_lammps', {})
    if name == 'gui_download_model':
        return http('POST', '/api/download_model',
                    {'name': args.get('name')})
    if name == 'gui_metrics':
        return http('GET', '/api/metrics', timeout=20)
    if name == 'gui_estimate':
        keys = ('mode', 'device', 'grid', 'temps', 'eq', 'prod')
        upd = {k: args[k] for k in keys
               if k in args and args[k] is not None}
        if upd:
            return http('POST', '/api/estimate', {'form': upd}, timeout=30)
        return http('GET', '/api/estimate', timeout=30)
    if name == 'gui_calibrate':
        return http('POST', '/api/calibrate', {}, timeout=30)
    if name == 'gui_structure':
        import urllib.parse
        q = []
        if args.get('outdir'):
            q.append('outdir=' + urllib.parse.quote(args['outdir'], safe=''))
        path = '/api/structure' + ('?' + '&'.join(q) if q else '')
        data = http('GET', path, timeout=30)
        if not args.get('include_positions') and isinstance(data, dict):
            data.pop('positions', None)
            data.pop('types', None)
            data.pop('cell', None)
            data.pop('box', None)
        return data
    if name == 'gui_add_potential':
        return http('POST', '/api/potentials/copy',
                    {'path': args.get('path')}, timeout=300)
    if name == 'gui_get_elements':
        return http('GET', '/api/elements')
    if name == 'gui_save_element':
        item = {'symbol': args.get('symbol'),
                'lc': args.get('lc'), 'label': args.get('label')}
        return http('POST', '/api/elements',
                    {'action': 'save', 'item': item, 'source': 'agent'})
    if name == 'gui_delete_element':
        return http('POST', '/api/elements',
                    {'action': 'delete', 'symbol': args.get('symbol'),
                     'source': 'agent'})
    raise ValueError('unknown tool: ' + name)


# ----------------------------------------------------------- json-rpc io --
def reply(msg_id, result):
    sys.stdout.write(json.dumps(
        {'jsonrpc': '2.0', 'id': msg_id, 'result': result},
        ensure_ascii=False) + '\n')
    sys.stdout.flush()


def reply_error(msg_id, code, message):
    sys.stdout.write(json.dumps(
        {'jsonrpc': '2.0', 'id': msg_id,
         'error': {'code': code, 'message': message}},
        ensure_ascii=False) + '\n')
    sys.stdout.flush()


def handle(msg):
    method = msg.get('method', '')
    msg_id = msg.get('id')
    params = msg.get('params') or {}

    if method == 'initialize':
        reply(msg_id, {
            'protocolVersion': params.get('protocolVersion', PROTOCOL),
            'capabilities': {'tools': {}},
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
        })
        return
    if method == 'notifications/initialized':
        return                                   # no response for notices
    if method == 'ping':
        reply(msg_id, {})
        return
    if method == 'tools/list':
        reply(msg_id, {'tools': TOOLS})
        return
    if method == 'tools/call':
        name = params.get('name', '')
        args = params.get('arguments') or {}
        try:
            result = call_tool(name, args)
            reply(msg_id, {
                'content': [{'type': 'text',
                             'text': json.dumps(result, ensure_ascii=False,
                                                indent=1)}],
                'isError': False,
            })
        except Exception as exc:
            reply(msg_id, {
                'content': [{'type': 'text',
                             'text': 'ERROR: {}'.format(exc)}],
                'isError': True,
            })
        return
    if msg_id is not None:
        reply_error(msg_id, -32601, 'method not found: ' + method)


def main():
    sys.stderr.write('{} {} listening on stdio (gui={})\n'.format(
        SERVER_NAME, SERVER_VERSION, BASE))
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(msg)


if __name__ == '__main__':
    main()
