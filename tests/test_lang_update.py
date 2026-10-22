# -*- coding: utf-8 -*-
"""Language selector: default, persistence, unknown-code rejection."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import server  # noqa: E402


def _cleanup():
    try:
        os.remove(server.LANG_PATH)
    except OSError:
        pass


def test_default_language_is_russian():
    _cleanup()
    try:
        assert server.get_lang() == 'ru'
        assert server.LANGS[0][0] == 'ru', 'default must be current lang'
        codes = [c for c, _ in server.LANGS]
        assert 'ru' in codes
    finally:
        _cleanup()


def test_set_lang_persists_and_reads_back():
    _cleanup()
    try:
        assert server.set_lang('ru') is True
        assert server.get_lang() == 'ru'
    finally:
        _cleanup()


def test_unknown_language_rejected():
    _cleanup()
    try:
        before = server.get_lang()
        assert server.set_lang('de') is False
        assert server.set_lang(None) is False
        assert server.set_lang('<script>') is False
        # rejection must not clobber the saved value
        assert server.get_lang() == before
    finally:
        _cleanup()


def test_status_summary_carries_lang():
    st = server.status_summary()
    assert st['lang'] in [c for c, _ in server.LANGS]
