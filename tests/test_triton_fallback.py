# -*- coding: utf-8 -*-
"""Fast tests: triton/ptxas block detection and the auto-fallback."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import run_main_mace as rm  # noqa: E402


def test_detects_winerror5_on_ptxas():
    exc = PermissionError(
        5, 'Access is denied',
        r'C:\\Users\\u\\AppData\\Local\\Temp\\triton\\ptxas.exe')
    assert rm.is_ptxas_block(exc)


def test_detects_block_via_traceback_frame_only():
    # denial message is bare, but the traceback frame points into
    # torch\\_inductor\\runtime\\triton_heuristics.py (as in client logs)
    src = 'def boom():\n    raise PermissionError(5, "Access is denied")\n'
    code = compile(src,
                   r'C:\fake\torch\_inductor\runtime\triton_heuristics.py',
                   'exec')
    ns = {}
    exec(code, ns)
    caught = None
    try:
        ns['boom']()
    except PermissionError as e:
        caught = e
    assert caught is not None
    assert rm.is_ptxas_block(caught)


def test_ignores_unrelated_errors():
    assert not rm.is_ptxas_block(ValueError('triton is great'))
    assert not rm.is_ptxas_block(FileNotFoundError('ptxas missing'))
    assert not rm.is_ptxas_block(PermissionError(5, 'Access is denied',
                                                 'results/out.csv'))


def test_rescue_only_when_compile_was_on():
    blocked = PermissionError(
        5, 'Access is denied', r'C:\\t\\triton\\ptxas.exe')
    assert rm.rescue_or_raise(blocked, True) is True      # fallback path
    assert rm.rescue_or_raise(blocked, False) is False    # already off
    assert rm.rescue_or_raise(ValueError('bad shape'), True) is False


def test_preflight_returns_a_boolean_pair():
    ok, why = rm.triton_preflight()
    assert isinstance(ok, bool) and isinstance(why, str)
