# -*- coding: utf-8 -*-
"""Precision modes (fp16 default / bf16 / fp32): estimate, form, CLI."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'gui'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import estimator as est  # noqa: E402


def _prof():
    return {
        'points': [
            {'mode': 'mace', 'device': 'cuda', 'grid': 4, 'natoms': 256,
             'ms_per_step': 61.9, 'vram_mb': 2536.0, 'rss_mb': 1716.0},
        ],
        'overhead': 1.6,
    }


def test_estimate_default_is_fp16():
    base = est.estimate(_prof(), 'mace', 'cuda', 4, '300 1200', 500, 1000)
    fp16 = est.estimate(_prof(), 'mace', 'cuda', 4, '300 1200', 500, 1000,
                        precision='fp16')
    assert base['precision'] == 'fp16'
    assert base['vram_mb'] == fp16['vram_mb']
    assert base['seconds'] == fp16['seconds']


def test_estimate_memory_and_time_follow_precision():
    fp16 = est.estimate(_prof(), 'mace', 'cuda', 4, '300 1200', 500, 1000,
                        precision='fp16')
    fp32 = est.estimate(_prof(), 'mace', 'cuda', 4, '300 1200', 500, 1000,
                        precision='fp32')
    bf16 = est.estimate(_prof(), 'mace', 'cuda', 4, '300 1200', 500, 1000,
                        precision='bf16')
    # fp32 must show MORE memory and MORE time than the fast modes
    assert fp32['vram_mb'] > fp16['vram_mb']
    assert fp32['seconds'] > fp16['seconds']
    assert fp32['vram_mb'] > bf16['vram_mb']
    # fp16 recommended = the cheapest
    assert fp16['vram_mb'] <= bf16['vram_mb']
    assert fp16['seconds'] <= fp32['seconds']
    # unknown value falls back to fp16
    weird = est.estimate(_prof(), 'mace', 'cuda', 4, '300 1200', 500, 1000,
                         precision='int4')
    assert weird['precision'] == 'fp16'


def test_server_form_defaults_to_fp16():
    import server
    assert server.FORM.get('precision') == 'fp16'


def test_engine_cli_exposes_precision():
    py = os.path.join(ROOT, '.venv-mace', 'Scripts', 'python.exe')
    proc = subprocess.run(
        [py, os.path.join(ROOT, 'scripts', 'run_main_mace.py'), '--help'],
        capture_output=True, text=True, timeout=120, encoding='utf-8')
    out = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode == 0, out[-800:]
    assert '--precision' in out
    assert 'fp16' in out and 'bf16' in out and 'fp32' in out
