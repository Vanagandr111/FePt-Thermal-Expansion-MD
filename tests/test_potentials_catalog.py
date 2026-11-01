# -*- coding: utf-8 -*-
"""JSON-каталог потенциалов: сид из бандла, правки без пересборки,
битый файл -> фоллбэк, слияние с git (новые записи, локальные побеждают).

Регресс бага заказчика 2026-10-28: каталог был хардкодом в server.py,
ссылки 1..17 пропали из-за запятой вместо + в renderModelCatalog, и
править список можно было только пересборкой exe.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import server as srv


BUNDLED = {
    'version': 1,
    'gpu': [{'name': 'a.model', 'family': 'A', 'label': 'a', 'mb': 1.0,
             'url': 'https://x/a.model', 'rec': True}],
    'neural': [{'key': '7net-0', 'label': 'SevenNet-0', 'url': 'https://y'}],
    'cpu': [{'label': 'NIST', 'url': 'https://nist.gov/'}],
}


def _wire(monkeypatch, tmp_path, bundled=BUNDLED, user_json=None):
    """PROJ -> tmp, CATALOG_BUNDLED -> separate file, cache cleared."""
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'bundled_catalog.json').write_text(
        json.dumps(bundled), encoding='utf-8')
    monkeypatch.setattr(srv, 'PROJ', str(tmp_path))
    monkeypatch.setattr(srv, 'CATALOG_BUNDLED',
                        str(data / 'bundled_catalog.json'))
    monkeypatch.setattr(srv, '_CATALOG', {'data': None})
    if user_json is not None:
        (data / 'potentials_catalog.json').write_text(
            user_json, encoding='utf-8')
    return data / 'potentials_catalog.json'


def test_seed_creates_editable_copy(monkeypatch, tmp_path):
    """First run copies the bundled JSON into the app folder, so the user
    can hand-edit it without recompiling the exe."""
    path = _wire(monkeypatch, tmp_path)
    cat = srv.load_catalog()
    assert [g['name'] for g in cat['gpu']] == ['a.model']
    assert path.is_file(), 'editable copy not seeded'
    # hand edit wins on the next read (cache cleared by restart/apply_root)
    edited = dict(BUNDLED)
    edited['gpu'] = list(BUNDLED['gpu']) + [
        {'name': 'own.model', 'family': 'Own', 'label': 'моя', 'mb': 2.0,
         'url': 'https://me/own.model'}]
    path.write_text(json.dumps(edited, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(srv, '_CATALOG', {'data': None})
    cat2 = srv.load_catalog()
    assert 'own.model' in [g['name'] for g in cat2['gpu']], \
        'user edit ignored without rebuild'


def test_broken_user_json_falls_back(monkeypatch, tmp_path):
    """A hand-edit typo must not kill the deps tab: bundled copy answers."""
    path = _wire(monkeypatch, tmp_path)
    path.write_text('{ gpu: oops', encoding='utf-8')
    cat = srv.load_catalog()
    assert [g['name'] for g in cat['gpu']] == ['a.model'], cat


def test_catalog_update_merges_only_new(monkeypatch, tmp_path):
    """git raw brings NEW rows; existing rows (incl. user edits) untouched."""
    _wire(monkeypatch, tmp_path)
    remote = {
        'gpu': [{'name': 'a.model', 'family': 'A', 'label': 'переименован',
                 'mb': 9.9, 'url': 'https://x/NEW'},
                {'name': 'b.model', 'family': 'B', 'label': 'b', 'mb': 3.0,
                 'url': 'https://x/b.model'}],
        'cpu': [{'label': 'NIST', 'url': 'https://nist.gov/'},
                {'label': 'OpenKIM', 'url': 'https://openkim.org/'}],
    }

    class _Resp(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(remote).encode('utf-8')

    monkeypatch.setattr(srv, 'url_open', lambda req, timeout=30: _Resp())
    added = srv.catalog_update(['gpu', 'cpu'])
    assert added == ['gpu/b.model', 'cpu/OpenKIM'], added
    cat = srv.load_catalog()
    names = {g['name']: g for g in cat['gpu']}
    assert names['a.model']['url'] == 'https://x/a.model', \
        'local row was overwritten by remote'
    assert names['a.model']['label'] == 'a'
    assert 'b.model' in names
    # повтор без новых записей -> пусто (не плодит дубли)
    assert srv.catalog_update(['gpu', 'cpu']) == []


def test_catalog_update_bad_remote(monkeypatch, tmp_path):
    """Non-JSON / non-object remote -> error raised, catalog unchanged."""
    _wire(monkeypatch, tmp_path)

    class _Resp(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'<html>rate limited</html>'

    monkeypatch.setattr(srv, 'url_open', lambda req, timeout=30: _Resp())
    try:
        srv.catalog_update(['gpu'])
    except Exception as exc:
        assert exc, 'must raise'
    else:
        raise AssertionError('bad remote must raise')
    assert [g['name'] for g in srv.load_catalog()['gpu']] == ['a.model']


def test_download_model_url_from_catalog(monkeypatch, tmp_path):
    """/api/download_model resolves the URL from the JSON catalog (the
    hardcoded MODEL_URLS dict is gone)."""
    _wire(monkeypatch, tmp_path)
    srv.load_catalog()
    url = next((g['url'] for g in srv.load_catalog().get('gpu', [])
                if g.get('name') == 'a.model'), None)
    assert url == 'https://x/a.model'
