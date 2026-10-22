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

# fcc seed lattice constants (Angstrom). Fe: MACE-MP-0 EOS fit matches
# experiment (3.56); Pt: EXPERIMENTAL 3.9242 (fcc, 293K) - the old
# 4.0065 MACE-MP-0 EOS fit carried +2.21% error straight into every
# starting structure (client complaint: 'нечёткое, большая погрешность').
DEFAULT_ELEMENTS = [
    {'symbol': 'Fe', 'label': 'Железо (fcc)', 'lc': 3.5647},
    {'symbol': 'Pt', 'label': 'Платина', 'lc': 3.9242},
]

_SYMBOL_RE = re.compile(r'^[A-Z][a-z]?$')

# atomic number -> symbol (for legacy EAM headers that start with Z)
_Z2SYM = ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr '
          'Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd '
          'Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er '
          'Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th '
          'Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr').split()


# ---------------------------------------------------------------------------
# Element encyclopedia: symbol -> {ru name, atomic number, atomic mass}.
# Generated from ase.data (verified masses) + curated Russian names;
# lets the UI confirm that the system actually RECOGNIZES the atom that
# was typed ('Fe - железо, 55.845 а.е.м.') instead of a silent typo.
SYMBOL_INFO = {
    'H': {'ru': 'Водород', 'z': 1, 'mass': 1.00800},
    'He': {'ru': 'Гелий', 'z': 2, 'mass': 4.00260},
    'Li': {'ru': 'Литий', 'z': 3, 'mass': 6.94000},
    'Be': {'ru': 'Бериллий', 'z': 4, 'mass': 9.01218},
    'B': {'ru': 'Бор', 'z': 5, 'mass': 10.81000},
    'C': {'ru': 'Углерод', 'z': 6, 'mass': 12.01100},
    'N': {'ru': 'Азот', 'z': 7, 'mass': 14.00700},
    'O': {'ru': 'Кислород', 'z': 8, 'mass': 15.99900},
    'F': {'ru': 'Фтор', 'z': 9, 'mass': 18.99840},
    'Ne': {'ru': 'Неон', 'z': 10, 'mass': 20.17970},
    'Na': {'ru': 'Натрий', 'z': 11, 'mass': 22.98977},
    'Mg': {'ru': 'Магний', 'z': 12, 'mass': 24.30500},
    'Al': {'ru': 'Алюминий', 'z': 13, 'mass': 26.98154},
    'Si': {'ru': 'Кремний', 'z': 14, 'mass': 28.08500},
    'P': {'ru': 'Фосфор', 'z': 15, 'mass': 30.97376},
    'S': {'ru': 'Сера', 'z': 16, 'mass': 32.06000},
    'Cl': {'ru': 'Хлор', 'z': 17, 'mass': 35.45000},
    'Ar': {'ru': 'Аргон', 'z': 18, 'mass': 39.94800},
    'K': {'ru': 'Калий', 'z': 19, 'mass': 39.09830},
    'Ca': {'ru': 'Кальций', 'z': 20, 'mass': 40.07800},
    'Sc': {'ru': 'Скандий', 'z': 21, 'mass': 44.95591},
    'Ti': {'ru': 'Титан', 'z': 22, 'mass': 47.86700},
    'V': {'ru': 'Ванадий', 'z': 23, 'mass': 50.94150},
    'Cr': {'ru': 'Хром', 'z': 24, 'mass': 51.99610},
    'Mn': {'ru': 'Марганец', 'z': 25, 'mass': 54.93804},
    'Fe': {'ru': 'Железо', 'z': 26, 'mass': 55.84500},
    'Co': {'ru': 'Кобальт', 'z': 27, 'mass': 58.93319},
    'Ni': {'ru': 'Никель', 'z': 28, 'mass': 58.69340},
    'Cu': {'ru': 'Медь', 'z': 29, 'mass': 63.54600},
    'Zn': {'ru': 'Цинк', 'z': 30, 'mass': 65.38000},
    'Ga': {'ru': 'Галлий', 'z': 31, 'mass': 69.72300},
    'Ge': {'ru': 'Германий', 'z': 32, 'mass': 72.63000},
    'As': {'ru': 'Мышьяк', 'z': 33, 'mass': 74.92159},
    'Se': {'ru': 'Селен', 'z': 34, 'mass': 78.97100},
    'Br': {'ru': 'Бром', 'z': 35, 'mass': 79.90400},
    'Kr': {'ru': 'Криптон', 'z': 36, 'mass': 83.79800},
    'Rb': {'ru': 'Рубидий', 'z': 37, 'mass': 85.46780},
    'Sr': {'ru': 'Стронций', 'z': 38, 'mass': 87.62000},
    'Y': {'ru': 'Иттрий', 'z': 39, 'mass': 88.90584},
    'Zr': {'ru': 'Цирконий', 'z': 40, 'mass': 91.22400},
    'Nb': {'ru': 'Ниобий', 'z': 41, 'mass': 92.90637},
    'Mo': {'ru': 'Молибден', 'z': 42, 'mass': 95.95000},
    'Tc': {'ru': 'Технеций', 'z': 43, 'mass': 97.90721},
    'Ru': {'ru': 'Рутений', 'z': 44, 'mass': 101.07000},
    'Rh': {'ru': 'Родий', 'z': 45, 'mass': 102.90550},
    'Pd': {'ru': 'Палладий', 'z': 46, 'mass': 106.42000},
    'Ag': {'ru': 'Серебро', 'z': 47, 'mass': 107.86820},
    'Cd': {'ru': 'Кадмий', 'z': 48, 'mass': 112.41400},
    'In': {'ru': 'Индий', 'z': 49, 'mass': 114.81800},
    'Sn': {'ru': 'Олово', 'z': 50, 'mass': 118.71000},
    'Sb': {'ru': 'Сурьма', 'z': 51, 'mass': 121.76000},
    'Te': {'ru': 'Теллур', 'z': 52, 'mass': 127.60000},
    'I': {'ru': 'Иод', 'z': 53, 'mass': 126.90447},
    'Xe': {'ru': 'Ксенон', 'z': 54, 'mass': 131.29300},
    'Cs': {'ru': 'Цезий', 'z': 55, 'mass': 132.90545},
    'Ba': {'ru': 'Барий', 'z': 56, 'mass': 137.32700},
    'La': {'ru': 'Лантан', 'z': 57, 'mass': 138.90547},
    'Ce': {'ru': 'Церий', 'z': 58, 'mass': 140.11600},
    'Pr': {'ru': 'Празеодим', 'z': 59, 'mass': 140.90766},
    'Nd': {'ru': 'Неодим', 'z': 60, 'mass': 144.24200},
    'Pm': {'ru': 'Прометий', 'z': 61, 'mass': 144.91276},
    'Sm': {'ru': 'Самарий', 'z': 62, 'mass': 150.36000},
    'Eu': {'ru': 'Европий', 'z': 63, 'mass': 151.96400},
    'Gd': {'ru': 'Гадолиний', 'z': 64, 'mass': 157.25000},
    'Tb': {'ru': 'Тербий', 'z': 65, 'mass': 158.92535},
    'Dy': {'ru': 'Диспрозий', 'z': 66, 'mass': 162.50000},
    'Ho': {'ru': 'Гольмий', 'z': 67, 'mass': 164.93033},
    'Er': {'ru': 'Эрбий', 'z': 68, 'mass': 167.25900},
    'Tm': {'ru': 'Тулий', 'z': 69, 'mass': 168.93422},
    'Yb': {'ru': 'Иттербий', 'z': 70, 'mass': 173.05400},
    'Lu': {'ru': 'Лютеций', 'z': 71, 'mass': 174.96680},
    'Hf': {'ru': 'Гафний', 'z': 72, 'mass': 178.49000},
    'Ta': {'ru': 'Тантал', 'z': 73, 'mass': 180.94788},
    'W': {'ru': 'Вольфрам', 'z': 74, 'mass': 183.84000},
    'Re': {'ru': 'Рений', 'z': 75, 'mass': 186.20700},
    'Os': {'ru': 'Осмий', 'z': 76, 'mass': 190.23000},
    'Ir': {'ru': 'Иридий', 'z': 77, 'mass': 192.21700},
    'Pt': {'ru': 'Платина', 'z': 78, 'mass': 195.08400},
    'Au': {'ru': 'Золото', 'z': 79, 'mass': 196.96657},
    'Hg': {'ru': 'Ртуть', 'z': 80, 'mass': 200.59200},
    'Tl': {'ru': 'Таллий', 'z': 81, 'mass': 204.38000},
    'Pb': {'ru': 'Свинец', 'z': 82, 'mass': 207.20000},
    'Bi': {'ru': 'Висмут', 'z': 83, 'mass': 208.98040},
    'Po': {'ru': 'Полоний', 'z': 84, 'mass': 208.98243},
    'At': {'ru': 'Астат', 'z': 85, 'mass': 209.98715},
    'Rn': {'ru': 'Радон', 'z': 86, 'mass': 222.01758},
    'Fr': {'ru': 'Франций', 'z': 87, 'mass': 223.01974},
    'Ra': {'ru': 'Радий', 'z': 88, 'mass': 226.02541},
    'Ac': {'ru': 'Актиний', 'z': 89, 'mass': 227.02775},
    'Th': {'ru': 'Торий', 'z': 90, 'mass': 232.03770},
    'Pa': {'ru': 'Протактиний', 'z': 91, 'mass': 231.03588},
    'U': {'ru': 'Уран', 'z': 92, 'mass': 238.02891},
    'Np': {'ru': 'Нептуний', 'z': 93, 'mass': 237.04817},
    'Pu': {'ru': 'Плутоний', 'z': 94, 'mass': 244.06421},
    'Am': {'ru': 'Америций', 'z': 95, 'mass': 243.06138},
    'Cm': {'ru': 'Кюрий', 'z': 96, 'mass': 247.07035},
    'Bk': {'ru': 'Берклий', 'z': 97, 'mass': 247.07031},
    'Cf': {'ru': 'Калифорнийий', 'z': 98, 'mass': 251.07959},
    'Es': {'ru': 'Эйнштейний', 'z': 99, 'mass': 252.08300},
    'Fm': {'ru': 'Фермий', 'z': 100, 'mass': 257.09511},
    'Md': {'ru': 'Менделевий', 'z': 101, 'mass': 258.09843},
    'No': {'ru': 'Нобелий', 'z': 102, 'mass': 259.10100},
    'Lr': {'ru': 'Лоуренсий', 'z': 103, 'mass': 262.11000},
    'Rf': {'ru': 'Резерфордий', 'z': 104, 'mass': 267.12200},
    'Db': {'ru': 'Дубний', 'z': 105, 'mass': 268.12600},
    'Sg': {'ru': 'Сиборгий', 'z': 106, 'mass': 271.13400},
    'Bh': {'ru': 'Борий', 'z': 107, 'mass': 270.13300},
    'Hs': {'ru': 'Хассий', 'z': 108, 'mass': 269.13380},
    'Mt': {'ru': 'Мейтнерий', 'z': 109, 'mass': 278.15600},
    'Ds': {'ru': 'Дармштадтий', 'z': 110, 'mass': 281.16500},
    'Rg': {'ru': 'Рентгений', 'z': 111, 'mass': 281.16600},
    'Cn': {'ru': 'Коперниций', 'z': 112, 'mass': 285.17700},
    'Nh': {'ru': 'Нихоний', 'z': 113, 'mass': 286.18200},
    'Fl': {'ru': 'Флеровий', 'z': 114, 'mass': 289.19000},
    'Mc': {'ru': 'Московий', 'z': 115, 'mass': 289.19400},
    'Lv': {'ru': 'Ливерморий', 'z': 116, 'mass': 293.20400},
    'Ts': {'ru': 'Теннессин', 'z': 117, 'mass': 293.20800},
    'Og': {'ru': 'Оганесон', 'z': 118, 'mass': 294.21400},
}

# canonical (case-insensitive) -> symbol, so 'fe' / 'FE' still resolve
_SYM_BY_UPPER = {k.upper(): k for k in SYMBOL_INFO}


def symbol_info(sym):
    """Known element -> {'ok': True, 'symbol', 'ru', 'z', 'mass'}.

    Unknown/empty -> {'ok': False, 'input': <raw>} so the UI can say
    'the system does not see this atom' instead of guessing.
    """
    raw = (sym or '').strip()
    canon = _SYM_BY_UPPER.get(raw.upper()) if raw else None
    if not canon:
        return {'ok': False, 'input': raw}
    info = SYMBOL_INFO[canon]
    return {'ok': True, 'symbol': canon, 'ru': info['ru'],
            'z': info['z'], 'mass': info['mass']}


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
