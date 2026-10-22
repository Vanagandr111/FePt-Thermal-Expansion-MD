# -*- coding: utf-8 -*-
"""TDD for alloyFormula() in gui/static/index.html (node-based extraction).

The formula function is pure JS embedded in the page; this test pulls it
out of the inline <script> and asserts the alloy-stoichiometry rules in
node, so a regression in the HTML breaks pytest too.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'gui' / 'static' / 'index.html'

NODE_ASSERTS = r"""
const fe = alloyFormula;
const eq = (got, want, label) => {
  if (got !== want) { console.error('FAIL', label, 'got=' + got, 'want=' + want); process.exit(1); }
  console.log('ok', label, '=', got);
};
eq(fe('Fe','Pt',0),    'Fe',      'pure A');
eq(fe('Fe','Pt',1),    'Pt',      'pure B');
eq(fe('Fe','Pt',0.5),  'FePt',    '1:1');
eq(fe('Fe','Pt',0.25), 'Fe₃Pt',   'A3B');
eq(fe('Fe','Pt',0.75), 'FePt₃',   'AB3');
eq(fe('Fe','Pt',0.3),  'Fe₇Pt₃',  'reduced 14:6');
eq(fe('Fe','Pt',0.6),  'Fe₂Pt₃',  'reduced 2:3 via k=5');
eq(fe('Fe','Pt',0.05), 'Fe₁₉Pt',  'edge 19:1');
eq(fe('Cu','Al',0.25), 'Cu₃Al',   'generic elements');
eq(fe('Fe','Pt',0.33), null,      'non-multiple stays bare');
console.log('ALL OK');
"""


def _extract_function(src: str) -> str:
    m = re.search(r'function alloyFormula\(.*?\n\}', src, re.S)
    assert m, 'alloyFormula() not found in index.html'
    return m.group(0)


def test_alloy_formula_rules():
    assert shutil.which('node'), 'node required for this test'
    src = HTML.read_text(encoding='utf-8')
    fn = _extract_function(src)
    js = fn + '\n' + NODE_ASSERTS
    proc = subprocess.run(['node', '-e', js], capture_output=True,
                          text=True, timeout=30, encoding='utf-8')
    out = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode == 0, 'alloy formula assertions failed:\n' + out
    assert 'ALL OK' in out


def test_calculator_markup_present():
    src = HTML.read_text(encoding='utf-8')
    # calculator block + formula hook in the live updater
    assert 'id="compcalc"' in src
    assert 'alloyFormula(' in src
    assert 'comp-calc' in src


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']) if False else 0)
