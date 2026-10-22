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


def test_facet_segments_on_dense_grid():
    """7-point sweeps fill the 300-600/600-900/900-1200 columns.

    Adjacent-pair labels (300-450K, ...) never match the CSV lookups;
    facet_seg bridges the canonical grid nodes instead.
    """
    import lmp_helper
    pts = [(300, 3.993), (450, 4.001), (600, 4.006), (750, 4.016),
           (900, 4.024), (1050, 4.030), (1200, 4.038)]
    rep = lmp_helper.calc_cte_report(pts)
    f = rep['facet_seg']
    assert set(f) == {'300-600K', '600-900K', '900-1200K'}
    # each facet CTE is close to the chord over its node pair
    for lo, hi in ((300, 600), (600, 900), (900, 1200)):
        a_lo = pts[[p[0] for p in pts].index(lo)][1]
        a_hi = pts[[p[0] for p in pts].index(hi)][1]
        chord = (a_hi - a_lo) / a_lo / (hi - lo)
        assert abs(f['%d-%dK' % (lo, hi)] - chord) < 3e-6, (lo, hi)


def test_facet_segments_respect_sweep_span():
    """A sweep that stops at 600 K does not fabricate 600-900/900-1200."""
    import lmp_helper
    rep = lmp_helper.calc_cte_report(
        [(300, 3.993), (400, 4.000), (500, 4.004), (600, 4.006)])
    assert set(rep['facet_seg']) == {'300-600K'}


def test_print_trends_judges_against_the_plan(capsys):
    """No hardcoded "/4": a complete 2-point run is a success.

    The old code printed "INCOMPLETE (2/4)" for a perfectly finished
    2-temperature plan and "INCOMPLETE (1/4)" when the plan itself was
    one point - both read like failures in the console.
    """
    import lmp_helper

    def _pt(T, a):
        return {'a_mean': a, 'a_std': 0.0, 'a_min': a, 'a_max': a}

    # 1) full 2-point plan -> success, no INCOMPLETE anywhere
    parsed = {(1.0, 300): _pt(300, 3.993), (1.0, 1200): _pt(1200, 4.038)}
    lmp_helper.print_trends(parsed, [1.0], [300, 1200], seed=42)
    out = capsys.readouterr().out
    assert 'INCOMPLETE' not in out
    assert 'a300=3.993000' in out and 'a1200=4.038000' in out
    assert 'a_fit=' in out and 'R2=' in out

    # 2) plan of 4, only one delivered -> honest count + missing list
    parsed = {(1.0, 300): _pt(300, 3.993)}
    lmp_helper.print_trends(parsed, [1.0], [300, 600, 900, 1200])
    out = capsys.readouterr().out
    assert 'INCOMPLETE (1/4)' in out
    assert 'missing T=[600, 900, 1200]' in out

    # 3) plan of 1, delivered -> not a failure
    parsed = {(1.0, 300): _pt(300, 3.993)}
    lmp_helper.print_trends(parsed, [1.0], [300])
    out = capsys.readouterr().out
    assert 'INCOMPLETE' not in out
    assert 'single planned point' in out
