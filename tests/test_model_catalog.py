"""The on-demand model catalog stays consistent with the download map.

Every catalog entry must have a URL and vice versa; URLs are direct
GitHub release assets (https). Weights are NOT stored locally - only
this catalog + the loader - so a drift between the two silently breaks
the GUI download buttons.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gui'))
import server  # noqa: E402


def test_catalog_and_urls_are_in_sync():
    names_cat = {n for (n, _f, _l, _m) in server.MODEL_CATALOG}
    names_url = set(server.MODEL_URLS)
    assert names_cat == names_url, (
        'catalog without URL: %s; URL without catalog entry: %s'
        % (sorted(names_cat - names_url), sorted(names_url - names_cat)))


def test_all_urls_are_https_release_assets():
    for name, url in server.MODEL_URLS.items():
        assert url.startswith('https://'), (name, url)
        assert '/releases/download/' in url, (name, url)
        assert url.endswith(('.model', '.pt')), (name, url)


def test_catalog_metadata_is_sane():
    seen = set()
    for name, family, label, mb in server.MODEL_CATALOG:
        assert name not in seen, 'duplicate: ' + name
        seen.add(name)
        assert family and label
        assert mb > 10, 'suspiciously small model: %s (%s MB)' % (name, mb)


def test_deps_payload_exposes_models(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'resolve_python', lambda: sys.executable)
    monkeypatch.setattr(server, 'GPU_DIR', str(tmp_path))
    monkeypatch.setattr(server, '_DEPS_CACHE',
                        {'t': 0.0, 'data': None})
    data = server.collect_deps(refresh=True)
    assert 'models' in data
    assert any(m['name'] == 'mace-omat-0-medium.model'
               for m in data['models'])
    # a model dropped into the folder disappears from the download list
    (tmp_path / 'mace-mpa-0-medium.model').write_bytes(b'x')
    monkeypatch.setattr(server, '_DEPS_CACHE',
                        {'t': 0.0, 'data': None})
    data = server.collect_deps(refresh=True)
    assert not any(m['name'] == 'mace-mpa-0-medium.model'
                   for m in data['models'])
