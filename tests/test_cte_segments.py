# -*- coding: utf-8 -*-
"""Segmental CTE columns: engine writes them, server reads them back."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'gui'))

from run_main_mace import write_cte_full  # noqa: E402
import server  # noqa: E402


def _synthetic_parsed():
    # 4-point grid, a(T) almost linear -> segments close to the fit
    vals = {300: 3.8366, 600: 3.8496, 900: 3.8636, 1200: 3.8743}
    return {(0.5, T): {'a_mean': a} for T, a in vals.items()}


def test_write_cte_full_has_filled_segments():
    parsed = _synthetic_parsed()
    with tempfile.TemporaryDirectory() as out:
        path = write_cte_full(parsed, [0.5], [300, 600, 900, 1200], out)
        with open(path, encoding='utf-8') as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
        header = lines[0].split(';')
        data = lines[1].split(';')
        row = dict(zip(header, data))
        # headers present
        for k in ('seg_300_600', 'seg_600_900', 'seg_900_1200'):
            assert k in header, k
            assert row[k] != '', '%s empty' % k
            assert float(row[k]) > 0
        # sanity: segments bracket the fit value (~1.09e-05)
        fit = float(row['CTE_fit'])
        for k in ('seg_300_600', 'seg_600_900', 'seg_900_1200'):
            assert abs(float(row[k]) - fit) / fit < 0.2, (k, row[k], fit)


def test_server_collect_results_exposes_segments():
    parsed = _synthetic_parsed()
    with tempfile.TemporaryDirectory() as out:
        write_cte_full(parsed, [0.5], [300, 600, 900, 1200], out)
        # collect_results also wants all_results.csv; write a minimal one
        with open(os.path.join(out, 'all_results.csv'), 'w',
                  encoding='utf-8') as fh:
            fh.write('x_Pt;T_K;a_mean\n0.5;300;3.8366\n')
        res = server.collect_results(out)
        cte = res['cte'][0]
        for k in ('seg_300_600', 'seg_600_900', 'seg_900_1200'):
            assert cte[k] is not None, '%s is None' % k
            assert cte[k] > 0
        # overall fit still present
        assert cte['alpha_fit'] is not None
