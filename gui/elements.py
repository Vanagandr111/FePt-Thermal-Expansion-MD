"""Chemical element catalogue for the run system (A-B alloy).

Owns: the executor-editable element list (symbol + human label + seed
lattice constant), its persistence, validation, and reading which
elements a given potential file supports (EAM/MEAM text formats and
universal MACE weights).

Purity: no GUI/framework imports — unit-tested in tests/test_elements.py.
"""
import json
import os
import re
import tempfile

# fcc seed lattice constants (Angstrom), from our own MACE-MP-0 EOS fits
DEFAULT_ELEMENTS = [
    {'symbol': 'Fe', 'label': 'Железо (fcc)', 'lc': 3.5647},
    {'symbol': 'Pt', 'label': 'Платина', 'lc': 4.0065},
]

_SYMBOL_RE = re.compile(r'^[A-Z][a-z]?$')

# atomic number -> symbol (for legacy EAM headers that start with Z)
_Z2SYM = ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr '
          'Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd '
          'Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er '
          'Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th '
          'Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr').split()


def _default_path():
    here = os.path.dirname(os.path.abspath(__file__))
    proj = os.path.dirname(here) if os.path.basename(here) == 'gui' else here
    return os.path.join(proj, 'data', 'elements.json')


def load_elements(path=None):
    """Saved catalogue, else the Fe/Pt default."""
    path = path or _default_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            items = json.load(f)
        if isinstance(items, list) and items:
            return items
    except (OSError, ValueError):
        pass
    return [dict(e) for e in DEFAULT_ELEMENTS]


def save_elements(items, path=None):
    path = path or _default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # atomic write: tmp file next to the target, then replace
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


def normalize_symbol(symbol):
    s = str(symbol or '').strip()
    return s[:1].upper() + s[1:].lower() if s else ''


def validate_element(item):
    """(ok, error).  lc is optional but must be a sane length if given."""
    if not isinstance(item, dict):
        return False, 'element must be an object'
    sym = normalize_symbol(item.get('symbol'))
    if not _SYMBOL_RE.match(sym):
        return False, ('symbol: chemical notation like Fe / Cu / Pt '
                       '(one capital + optional lowercase letter)')
    lc = item.get('lc')
    if lc not in (None, ''):
        try:
            lc = float(lc)
        except (TypeError, ValueError):
            return False, 'seed lattice constant: a number in Angstrom, e.g. 3.615 (or empty)'
        if not (0.5 <= lc <= 100.0):
            return False, 'seed lattice constant out of range 0.5..100 A'
    label = item.get('label') or ''
    if len(str(label)) > 80:
        return False, 'label: max 80 characters'
    return True, None


def clean_element(item):
    sym = normalize_symbol(item.get('symbol'))
    out = {'symbol': sym, 'label': str(item.get('label') or '').strip()}
    lc = item.get('lc')
    out['lc'] = round(float(lc), 6) if lc not in (None, '') else None
    return out


def upsert_element(items, item):
    """Add or update (case-insensitive by symbol); returns (list, index)."""
    clean = clean_element(item)
    items = list(items)
    for i, e in enumerate(items):
        if normalize_symbol(e.get('symbol')) == clean['symbol']:
            items[i] = {**e, **clean}
            return items, i
    items.append(clean)
    return items, len(items) - 1


def remove_element(items, symbol):
    sym = normalize_symbol(symbol)
    return [e for e in items
            if normalize_symbol(e.get('symbol')) != sym]


# ------------------------------------------------------------ potentials --
def potential_elements(path):
    """Which elements a potential file supports.

    Returns {'kind': ..., 'elements': [...] | None}.
    elements is None when the file is universal (MACE weights) or
    unreadable — the UI then shows no restriction (MACE) / no info."""
    base = os.path.basename(path).lower()
    if base.endswith(('.model', '.pt')):
        return {'kind': 'mace', 'elements': None}
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            head = ''.join(f.readline() for _ in range(60))
    except OSError:
        return {'kind': 'unreadable', 'elements': None}

    # meam library: lines like  'Pt'\t'fcc'\t12... (file case varies)
    found = re.findall(r"^'([A-Za-z]{1,2})'", head, re.M)
    # meam alloy file: "# Element 1 = Fe, Element 2 = Pt"
    found += re.findall(r'Element\s+\d+\s*=\s*([A-Z][a-z]?)', head)
    # setfl/alloy header: "16 Cu Ag Au Ni ..."
    m = re.search(r'^\s*(\d+)((?:\s+[A-Z][a-z]?)+)\s*$', head, re.M)
    if m:
        found += re.findall(r'[A-Z][a-z]?', m.group(2))
    # old EAM element blocks: "1  Fe" (index + symbol lines)
    found += re.findall(r'^\s*\d+\s+([A-Z][a-z]?)\s*$', head, re.M)
    # legacy EAM: second line starts with atomic number "78 195.09 ... FCC"
    if not found:
        m = re.search(r'^\s*(\d{1,3})\s+[\d.]+\s+[\d.]+\s+(?:FCC|BCC|HCP)',
                      head, re.M)
        if m:
            z = int(m.group(1))
            if 1 <= z <= len(_Z2SYM):
                found.append(_Z2SYM[z - 1])
    out = []
    for s in found:
        s = normalize_symbol(s)
        if s and s not in out:
            out.append(s)
    if not out:
        return {'kind': 'unknown', 'elements': None}
    kind = 'meam' if base.endswith('.meam') else 'eam'
    return {'kind': kind, 'elements': out}


def compatibility(elements, pot_path):
    """Does the potential support the chosen elements?  status in
    universal / ok / partial / none / unknown."""
    pe = potential_elements(pot_path)
    syms = [normalize_symbol(e.get('symbol')) for e in elements]
    if pe['elements'] is None:
        status = 'universal' if pe['kind'] == 'mace' else 'unknown'
        return {'status': status, 'kind': pe['kind'],
                'potential_elements': None, 'missing': []}
    have_l = [s.lower() for s in pe['elements']]
    have = [s for s in syms if s.lower() in have_l]
    missing = [s for s in syms if s.lower() not in have_l]
    if not missing:
        status = 'ok'
    elif have:
        status = 'partial'
    else:
        status = 'none'
    return {'status': status, 'kind': pe['kind'],
            'potential_elements': pe['elements'], 'missing': missing}
