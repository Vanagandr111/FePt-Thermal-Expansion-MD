# -*- coding: utf-8 -*-
"""JSON-каталог потенциалов согласован: у каждой записи — прямой https-URL
GitHub release asset, без дублей, метаданные вменяемы.

2026-10-28: источник — data/potentials_catalog.json (правится заказчиком
без пересборки), хардкод MODEL_CATALOG/MODEL_URLS удалён. Инварианты
старого теста сохранены: URL обязан быть https release-ассетом, каталог
и карта URL больше не разъезжаются (один файл).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gui'))
import server  # noqa: E402

REPO_JSON = (Path(__file__).resolve().parents[1] /
             'data' / 'potentials_catalog.json')


def _repo_catalog():
    return json.loads(REPO_JSON.read_text(encoding='utf-8'))


def test_repo_json_is_valid_shape():
    cat = _repo_catalog()
    for key in ('gpu', 'neural', 'cpu'):
        assert isinstance(cat.get(key), list), key
    assert cat['gpu'] and cat['neural'] and cat['cpu']


def test_gpu_urls_are_https_release_assets():
    for g in _repo_catalog()['gpu']:
        url = g.get('url') or ''
        assert url.startswith('https://'), (g['name'], url)
        assert '/releases/download/' in url, (g['name'], url)
        assert url.endswith(('.model', '.pt')), (g['name'], url)


def test_gpu_metadata_is_sane():
    seen = set()
    for g in _repo_catalog()['gpu']:
        name = g['name']
        assert name not in seen, 'duplicate: ' + name
        seen.add(name)
        assert g['family'] and g['label']
        assert g['mb'] > 10, 'suspiciously small model: %s (%s MB)' % (
            name, g['mb'])


def test_neural_entries_have_loader_key_and_repo():
    seen = set()
    for n in _repo_catalog()['neural']:
        assert n['key'] not in seen, 'duplicate: ' + n['key']
        seen.add(n['key'])
        assert n['url'].startswith('https://github.com/'), n


def test_cpu_links_are_https():
    for c in _repo_catalog()['cpu']:
        assert c['label'] and c['url'].startswith('https://'), c


def test_loader_serves_repo_json(monkeypatch, tmp_path):
    """load_catalog seeds the app folder from the bundled copy and the
    served models match the repo JSON names."""
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'potentials_catalog.json').write_bytes(REPO_JSON.read_bytes())
    monkeypatch.setattr(server, 'PROJ', str(tmp_path))
    monkeypatch.setattr(server, 'CATALOG_BUNDLED',
                        str(data / 'potentials_catalog.json'))
    monkeypatch.setattr(server, '_CATALOG', {'data': None})
    cat = server.load_catalog()
    repo = _repo_catalog()
    assert {g['name'] for g in cat['gpu']} == {g['name'] for g in repo['gpu']}
    assert (data / 'potentials_catalog.json').is_file()


def test_deps_payload_exposes_models(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'resolve_python', lambda: sys.executable)
    monkeypatch.setattr(server, 'GPU_DIR', str(tmp_path))
    monkeypatch.setattr(server, '_DEPS_CACHE',
                        {'t': 0.0, 'data': None})
    data = server.collect_deps(refresh=True)
    assert 'models' in data
    assert 'catalog' in data
    assert any(m['name'] == 'mace-omat-0-medium.model'
               for m in data['models'])
    # a model dropped into the folder disappears from the download list
    (tmp_path / 'mace-mpa-0-medium.model').write_bytes(b'x')
    monkeypatch.setattr(server, '_DEPS_CACHE',
                        {'t': 0.0, 'data': None})
    data = server.collect_deps(refresh=True)
    assert not any(m['name'] == 'mace-mpa-0-medium.model'
                   for m in data['models'])
