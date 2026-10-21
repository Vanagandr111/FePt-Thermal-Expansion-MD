"""Pure-stdlib parser for atomic-style LAMMPS data files.

Single source of truth for the structure format: the MD runner
(run_main_mace) and the GUI structure endpoint both go through here, so
the visualized structure is by construction the structure that was
simulated. No numpy/ase at this layer — ase conversion lives in
`read_lammps_data()` and is imported lazily.

Format written by gen_structure.py / lmp_helper.gen_structure:
    <n> atoms
    ...
    <xlo> <xhi> xlo xhi
    <ylo> <yhi> ylo yhi
    <zlo> <zhi> zlo zhi

    Atoms

    <id> <type> <x> <y> <z>
    ...
"""
import os

# LAMMPS type id -> chemical symbol (Fe/Pt binary, project convention)
TYPE_SYMBOLS = {1: 'Fe', 2: 'Pt'}
SYMBOL_Z = {'Fe': 26, 'Pt': 78}


class DataFileError(ValueError):
    """Raised when the file does not match the expected structure format."""


def parse_data(path):
    """Parse a data file into a plain dict (JSON-friendly).

    Returns:
        {
          'natoms': int,
          'box': [[xlo, xhi], [ylo, yhi], [zlo, zhi]],
          'cell': [[lx, 0, 0], [0, ly, 0], [0, 0, lz]],
          'positions': [[x, y, z], ...]      # sorted by atom id,
          'types': [1|2, ...],               # same order,
          'symbols': ['Fe'|'Pt', ...],       # same order,
          'counts': {'Fe': n, 'Pt': m},
        }

    Raises DataFileError on anything unexpected (never a bare KeyError,
    so the GUI can answer with a clear message instead of a traceback).
    """
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    natoms = None
    box = [None] * 6
    atom_rows = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.endswith('atoms'):
            natoms = int(ln.split()[0])
        elif ln.endswith('xlo xhi'):
            box[0], box[1] = map(float, ln.split()[:2])
        elif ln.endswith('ylo yhi'):
            box[2], box[3] = map(float, ln.split()[:2])
        elif ln.endswith('zlo zhi'):
            box[4], box[5] = map(float, ln.split()[:2])
        elif ln == 'Atoms':
            i += 1
            while i < len(lines) and len(lines[i].split()) >= 5:
                p = lines[i].split()
                atom_rows.append((int(p[0]), int(p[1]),
                                  float(p[2]), float(p[3]), float(p[4])))
                i += 1
            break
        i += 1

    if natoms is None or any(b is None for b in box):
        raise DataFileError('missing header (atoms/box): {}'.format(path))
    if len(atom_rows) != natoms:
        raise DataFileError('declared {} atoms, found {} in {}'.format(
            natoms, len(atom_rows), path))

    atom_rows.sort(key=lambda r: r[0])
    types = [r[1] for r in atom_rows]
    unknown = sorted({t for t in types if t not in TYPE_SYMBOLS})
    if unknown:
        raise DataFileError('unknown atom type(s) {} in {}'.format(
            unknown, path))
    symbols = [TYPE_SYMBOLS[t] for t in types]
    positions = [[r[2], r[3], r[4]] for r in atom_rows]
    lx = box[1] - box[0]
    ly = box[3] - box[2]
    lz = box[5] - box[4]
    counts = {'Fe': symbols.count('Fe'), 'Pt': symbols.count('Pt')}
    return {
        'natoms': natoms,
        'box': [[box[0], box[1]], [box[2], box[3]], [box[4], box[5]]],
        'cell': [[lx, 0.0, 0.0], [0.0, ly, 0.0], [0.0, 0.0, lz]],
        'positions': positions,
        'types': types,
        'symbols': symbols,
        'counts': counts,
    }


def read_lammps_data(path):
    """Parse into ase.Atoms (same rules as parse_data, shared code path).

    (ase.io.read with style='atomic' cannot infer elements without a
    Masses section — that was one of the crash sources.)
    """
    import numpy as np
    from ase import Atoms

    d = parse_data(path)
    numbers = [SYMBOL_Z[s] for s in d['symbols']]
    atoms = Atoms(numbers=numbers,
                  positions=np.array(d['positions']),
                  cell=d['cell'], pbc=True)
    return atoms


def newest_data_file(*dirs):
    """Newest *.lmp structure file in the given dirs, or None.

    Used by /api/structure so the Results tab can show the structure of
    the most recent run (or of the last calibration) with no form state.
    """
    best = None
    best_mtime = -1.0
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            if not fn.endswith('.lmp'):
                continue
            p = os.path.join(d, fn)
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if m > best_mtime:
                best, best_mtime = p, m
    return best
