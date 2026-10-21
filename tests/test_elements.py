"""Element catalogue: CRUD, validation, and potential-compatibility.

The GUI lets the executor manage the chemical elements of the system
(add / edit / delete with hints); this module owns the data rules and
the "does this potential support these elements" reading."""
import os

import elements as el


def _mk(sym, label='x', lc=None):
    return {'symbol': sym, 'label': label, 'lc': lc}


# ------------------------------------------------------------------ data --
def test_default_system_is_fe_pt_with_labels():
    syms = [e['symbol'] for e in el.DEFAULT_ELEMENTS]
    assert syms == ['Fe', 'Pt']
    for e in el.DEFAULT_ELEMENTS:
        assert e['label']          # human label present
        assert isinstance(e['lc'], (int, float))  # seed lattice const


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / 'elements.json'
    items = [_mk('Cu', 'Медь', 3.61), _mk('Ni', 'Никель')]
    el.save_elements(items, str(p))
    assert el.load_elements(str(p)) == items


def test_load_missing_file_gives_default(tmp_path):
    assert el.load_elements(str(tmp_path / 'nope.json')) == el.DEFAULT_ELEMENTS


# ------------------------------------------------------------- validation --
def test_validate_ok():
    ok, err = el.validate_element(_mk('Fe', 'Железо', 3.5647))
    assert ok and err is None


def test_validate_accepts_missing_lc_and_label():
    ok, err = el.validate_element({'symbol': 'Cu'})
    assert ok, err


def test_validate_rejects_bad_symbol():
    for bad in ('', 'Xyz', 'Fe2', '  ', '1', 'Fe 3'):
        ok, err = el.validate_element(_mk(bad))
        assert not ok and err, bad


def test_validate_rejects_bad_lc():
    ok, err = el.validate_element(_mk('Fe', lc=0.0))
    assert not ok
    ok, err = el.validate_element(_mk('Fe', lc='big'))
    assert not ok


# -------------------------------------------------------------------- CRUD --
def test_upsert_adds_new_and_updates_old():
    items = [_mk('Fe')]
    items, idx = el.upsert_element(items, _mk('Cu', 'Медь'))
    assert idx == 1 and [e['symbol'] for e in items] == ['Fe', 'Cu']
    items, idx = el.upsert_element(items, {'symbol': 'cu', 'label': 'Медь (fcc)'})
    assert idx == 1
    assert items[1]['label'] == 'Медь (fcc)'
    assert items[1]['symbol'] == 'Cu'  # normalized


def test_remove_element_case_insensitive():
    items = [_mk('Fe'), _mk('Pt')]
    out = el.remove_element(items, 'pt')
    assert [e['symbol'] for e in out] == ['Fe']


def test_remove_missing_is_noop():
    items = [_mk('Fe')]
    assert el.remove_element(items, 'Zn') == items


# ------------------------------------------------------- potential reading --
def test_potential_eam_fs_lists_elements(tmp_path):
    p = tmp_path / 'a.eam.fs'
    p.write_text('DATE: 2007 header line\ncomments here\n####\n1  Fe\n')
    out = el.potential_elements(str(p))
    assert out['kind'] == 'eam'
    assert out['elements'] == ['Fe']


def test_potential_eam_alloy_setfl_header(tmp_path):
    p = tmp_path / 'z.eam.alloy'
    p.write_text('  DATE: 2018 header\n  generated\n  fixes\n'
                 '16 Cu Ag Au Ni Pd Pt Al Pb Fe Mo Ta W Mg Co Ti Zr\n')
    out = el.potential_elements(str(p))
    assert out['elements'][:3] == ['Cu', 'Ag', 'Au']
    assert 'Fe' in out['elements'] and 'Pt' in out['elements']


def test_potential_meam_library(tmp_path):
    p = tmp_path / 'library.meam'
    p.write_text("# elt lat z\n'Pt'\t'fcc'\t12\t1\t195.080\n"
                 "'Fe'\t'bcc'\t8\t1\t55.847\n")
    out = el.potential_elements(str(p))
    assert sorted(out['elements']) == ['Fe', 'Pt']


def test_potential_meam_alloy_comment(tmp_path):
    p = tmp_path / 'PtFe.meam'
    p.write_text('rc = 4.4\n# Element 1 = Fe, Element 2 = Pt\n')
    out = el.potential_elements(str(p))
    assert sorted(out['elements']) == ['Fe', 'Pt']


def test_potential_eam_legacy_z(tmp_path):
    p = tmp_path / 'pt.eam'
    p.write_text('DATE: 2007 COMMENT: Pt functions (universal 3)\n'
                 '   78     195.09         3.9200    FCC\n500 5.0e-04\n')
    out = el.potential_elements(str(p))
    assert out['elements'] == ['Pt']


def test_mace_weights_are_universal(tmp_path):
    p = tmp_path / 'm.model'
    p.write_bytes(b'\x80\x02}q')
    out = el.potential_elements(str(p))
    assert out['kind'] == 'mace'
    assert out['elements'] is None  # universal — no restriction


def test_broken_download_is_unreadable(tmp_path):
    p = tmp_path / 'broken.eam.alloy'
    p.write_text('404: Not Found\n')
    out = el.potential_elements(str(p))
    assert out['elements'] in (None, [])  # nothing usable to match


# ------------------------------------------------------------ compatibility --
def test_compat_full_support(tmp_path):
    p = tmp_path / 'lib.meam'
    p.write_text("'Fe'\t'fcc'\n'Pt'\t'fcc'\n")
    out = el.compatibility(el.DEFAULT_ELEMENTS, str(p))
    assert out['status'] == 'ok' and out['missing'] == []


def test_compat_partial_reports_missing(tmp_path):
    p = tmp_path / 'fe.eam.fs'
    p.write_text('header\n1  Fe\n')
    out = el.compatibility(el.DEFAULT_ELEMENTS, str(p))
    assert out['status'] == 'partial'
    assert out['missing'] == ['Pt']


def test_compat_none_supported(tmp_path):
    p = tmp_path / 'cu.eam.fs'
    p.write_text('header\n1  Cu\n')
    out = el.compatibility(el.DEFAULT_ELEMENTS, str(p))
    assert out['status'] == 'none'


def test_compat_mace_is_universal(tmp_path):
    p = tmp_path / 'm.pt'
    p.write_bytes(b'x')
    out = el.compatibility(el.DEFAULT_ELEMENTS, str(p))
    assert out['status'] == 'universal'


def test_compat_case_insensitive_matching(tmp_path):
    p = tmp_path / 'lib.meam'
    p.write_text("'fe'\t'fcc'\n'PT'\t'fcc'\n")
    out = el.compatibility(el.DEFAULT_ELEMENTS, str(p))
    assert out['status'] == 'ok'
