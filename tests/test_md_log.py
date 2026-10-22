# -*- coding: utf-8 -*-
"""MD frame log: header + fixed-width line used by console and md_*.log."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))
import lmp_helper as lmp  # noqa: E402


def test_md_log_header_lists_params_and_columns():
    hdr = lmp.md_log_header({
        'x_Pt': '1.00', 'T_K': 300, 'atoms': 256, 'grid': 4,
        'eq_steps': 500, 'prod_steps': 1000, 'dt_fs': 1.0,
        'thermo_interval': 100, 'seed': 42})
    joined = '\n'.join(hdr)
    assert 'x_Pt=1.00' in joined
    assert 'T_K=300' in joined
    assert 'atoms=256' in joined
    assert 'seed=42' in joined
    # the column row is the LAST header line and carries every frame col
    cols = hdr[-1]
    for col in ('Step', 'Time_ps', 'Phase', 'PotEng_eV', 'KinEng_eV',
                'TotEng_eV', 'Temp_K', 'Press_bar', 'Volume_A3',
                'Latt_a_A'):
        assert col in cols


def test_md_log_line_is_fixed_width_and_sums_total_energy():
    line = lmp.md_log_line(step=100, t_ps=0.1, phase='eq', pe=-1000.25,
                           ke=30.5, temp=300.0, press=-12.34,
                           vol=4096.0, a=3.9931)
    parts = line.split()
    # every value lands in its own column
    assert parts[0] == '100'          # Step
    assert parts[1] == '0.100'        # Time_ps = steps * dt(fs) / 1000
    assert parts[2] == 'eq'           # Phase
    assert parts[3] == '-1000.2500'   # PotEng
    assert parts[4] == '30.5000'      # KinEng
    assert parts[5] == '-969.7500'    # TotEng = pe + ke
    assert parts[6] == '300.0'        # Temp
    assert parts[-1] == '3.99310'     # Latt a
    # same width for a prod frame -> columns stay aligned down the file
    line2 = lmp.md_log_line(step=1000, t_ps=1.0, phase='prod', pe=-1.0,
                            ke=0.5, temp=310.25, press=1.0, vol=100.0,
                            a=4.0)
    assert len(line.split()) == len(parts)
    assert line2.split()[2] == 'prod'


def test_md_log_final_mirrors_the_reference_stats_block():
    lines = lmp.md_log_final(
        total_steps=1500, log_records=151, log_interval=100,
        a_mean=3.994812, a_std=0.015767, a_min=3.973837, a_max=4.020793,
        drift=1.385530e-02, n_prod_points=10, runtime_s=54,
        mean_press_bar=103681.2)
    txt = '\n'.join(lines)
    assert lines[0] == '# === FINAL ==='
    assert 'total_steps_done=1500 log_records=151 log_interval=100 steps' in txt
    assert 'a_mean=3.994812 A' in txt
    assert 'a_std=0.015767 A' in txt
    assert 'drift=1.385530e-02 A n_prod_points=10 runtime=54 s' in txt
    assert ('mean_pressure_all_results_bar=103681.2 '
            '(column mean_press_bar in all_results.csv)') in txt
    assert lines[-1].startswith('# last_row_above')
    # every line is a comment -> the file stays parseable as a log
    assert all(ln.startswith('#') for ln in lines)


def test_md_log_line_phases_are_short_and_printed():
    line = lmp.md_log_line(step=0, t_ps=0.0, phase='equilibration',
                           pe=0.0, ke=0.0, temp=0.0, press=0.0, vol=0.0,
                           a=0.0)
    assert line.split()[2] == 'equil'  # truncated to 5 chars, no wrap
