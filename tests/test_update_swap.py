# -*- coding: utf-8 -*-
"""Self-update swap scripts: retry mechanics + step report + versioning."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import server  # noqa: E402


def test_bat_swaps_with_retries_and_reports():
    bat = server.build_update_bat(1234, r'C:\p\FePt-GUI.exe.new',
                                  r'C:\p\FePt-GUI.exe')
    # the swap loops until the staging file is gone (AV can hold the exe)
    assert ':swap' in bat
    assert 'goto :swap' in bat
    assert 'if exist' in bat
    # every step leaves a trace for post-mortem diagnosis
    assert 'update_report.txt' in bat
    assert 'bat-start' in bat and 'swapped' in bat and 'relaunched' in bat
    # the version we upgrade FROM is recorded
    assert server.APP_VERSION in bat
    assert 'taskkill /F /PID 1234' in bat
    assert 'start "" "C:\\p\\FePt-GUI.exe"' in bat
    assert 'del "%~f0"' in bat


def test_sh_swaps_with_retries_and_reports():
    sh = server.build_update_sh(1234, '/opt/FePt-GUI.new', '/opt/FePt-GUI')
    assert 'while ! mv' in sh
    assert 'swap-retry' in sh
    assert 'swap-gave-up' in sh
    assert 'update_report.txt' in sh
    assert 'nohup' in sh and 'chmod +x' in sh
    # sh must never carry CRs (a windows-built file would break sh parsing)
    assert '\r' not in sh
    assert server.APP_VERSION in sh


def test_sh_report_path_is_posix_even_on_windows():
    sh = server.build_update_sh(1, '/opt/FePt-GUI.new', '/opt/FePt-GUI')
    m = re.search(r"report='([^']+)'", sh)
    assert m, 'report variable must be defined'
    assert '\\' not in m.group(1)
