#!/usr/bin/env python
"""gen_structure.py - построить суперъячейку Fe-Pt для LAMMPS/ASE.

Два вида решётки (`--kind`):
  a1  - ГЦК (fcc) случайный твёрдый раствор, кубическая или орторомбическая
        ячейка (зависит от nx, ny, nz), 4 атома на ячейку;
  l10 - упорядоченная L1_0 (CuAu-I): чередование плоскостей Fe и Pt вдоль
        z, тетрагональная ячейка a x a x c (c/a ~ 0.965), только x_Pt = 0.5;
  l12 - упорядоченная L1_2 (Cu3Au): кубическая ячейка, угол занят меньшинством
        (x_Pt = 0.25 -> Fe3Pt, x_Pt = 0.75 -> FePt3).

Бокс пишется ПО КАЖДОЙ ОСИ: xhi = nx*a, yhi = ny*a, zhi = nz*c. Раньше
стояло `max(nx,ny,nz)*lc` во все три оси - при nx != ny != nz это давало
вакуумные слои и заниженную плотность (бокс-куб вокруг орторомбической
структуры), из-за чего NPT схлопывал объём, а расчёт был мусорным.

# module-purpose: Generate A1 / L1_0 Fe-Pt lattice data files for LAMMPS/ASE
# entry-points: generate_structure(), lattice_constant()
# related-modules: lmp_helper.gen_structure (caller), run_main_mace.run_point
"""
import argparse
import math
import os
import random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ── Seed lattice constants, one explicit table (no silent hardcode) ─────
# NOTE: v1.0 shipped a0=3.85 with the comment "rough estimate for Fe-Pt".
#       v1.5 rewrote this generator and hard-set 3.615 with NO derivation
#       recorded anywhere in git — so 3.615 is a historical seed, not a
#       computed one. It is kept only where changing it would break
#       comparability with every past run.
LC_TABLE = {
    # Pure Pt: EXPERIMENTAL fcc lattice a=3.9242 A (293K). The old seed
    # was our MACE-MP-0 EOS fit a(0K)=4.0065 A - honest, but +2.21% vs
    # experiment right at t=0, which the client saw as 'нечёткое значение
    # с большой погрешностью'. NPT equilibrates to the model volume
    # anyway; the seed itself is now experimentally exact.
    'pt': 3.9242,
    # Pure Fe (fcc/gamma): our MACE-MP-0 EOS fit (scripts/eos_pt.py
    # --comp 0.00), same method as pt; a(0K)=3.5647 A.
    'fe': 3.5647,
    # Fe-Pt alloys (A1 random solution): keep the historical v1.5 seed
    # 3.615 A so all runs from v1.0..v1.7 stay reproducible; alloys are
    # relaxed in NPT anyway.
    'fept': 3.615,
    # FePt L1_0 (CuAu-I), experimental room-temperature values:
    # a = 3.85 A in-plane, c = 3.72 A along the ordering axis (c/a ~ 0.966,
    # tetragonal distortion driven by the Fe-Pt layer ordering).
    'l10_a': 3.85,
    'l10_c': 3.717,
}

KINDS = ('a1', 'l10', 'l12')


# intent: pick the seed lattice constant by system, honoring an override
# allies: generate_structure (caller), LC_TABLE (data)
# sidefx: none
# purity: pure
def lattice_constant(comp_pt, lc_override=None, kind='a1', c_over_a=None):
    """Return (a, c, source_note) in Angstrom; c == a for cubic A1.

    kind='a1'  : a from LC_TABLE by composition (or explicit override).
    kind='l10' : a = 3.85 A, c = c_over_a * a (default c/a = 3.717/3.85).
    """
    if kind not in KINDS:
        raise ValueError("unknown cell kind {!r} (expected one of {})"
                         .format(kind, ', '.join(KINDS)))
    if kind == 'l10':
        a = float(lc_override) if lc_override is not None else LC_TABLE['l10_a']
        if c_over_a is not None:
            c = a * float(c_over_a)
            note = 'L1_0 tetragonal, explicit c/a={:.4f}'.format(float(c_over_a))
        else:
            c = LC_TABLE['l10_c'] if lc_override is None else a * (
                LC_TABLE['l10_c'] / LC_TABLE['l10_a'])
            note = ('L1_0 tetragonal, experimental a=3.85 c=3.717 A '
                    '(CuAu-I ordering)')
        return a, c, note
    if kind == 'l12':
        # L1_2 (Cu3Au) is cubic; no experimental seed is hardcoded here -
        # the a is the Vegard value over our own Fe/Pt seeds, and NPT
        # relaxes the volume to the model's own equilibrium anyway.
        a = (float(lc_override) if lc_override is not None
             else LC_TABLE['fe'] + comp_pt * (LC_TABLE['pt'] - LC_TABLE['fe']))
        return a, a, ('L1_2 cubic (Cu3Au), Vegard seed {:.4f} A'.format(a))
    if lc_override is not None:
        return float(lc_override), float(lc_override), 'explicit override'
    if comp_pt >= 0.999:
        lc = LC_TABLE['pt']
        return lc, lc, 'table[pt] = experimental fcc 3.9242 A (293K)'
    if comp_pt <= 0.001:
        lc = LC_TABLE['fe']
        return lc, lc, 'table[fe] = MACE-MP-0 EOS fit (fcc)'
    lc = LC_TABLE['fept']
    return lc, lc, ('table[fept] = historical seed (v1.5, '
                    'old-run comparability)')


def _a1_types(natoms_total, comp_pt):
    """Random substitution: shuffle indices, first n_pt become Pt (type 2)."""
    n_pt = int(round(natoms_total * comp_pt))
    random.seed(42)
    indices = list(range(natoms_total))
    random.shuffle(indices)
    types = [1] * natoms_total
    for idx in indices[:n_pt]:
        types[idx] = 2
    return types, natoms_total - n_pt, n_pt


def _l10_types(natoms_total):
    """L1_0: basis atom 0 and 1 -> Fe, 2 and 3 -> Pt (planes alternate in z).

    basis = (0,0,0) (0.5,0.5,0) (0.5,0,0.5) (0,0.5,0.5)
    -> z=0 plane holds atoms 0,1 (both Fe); z=c/2 plane holds 2,3 (both Pt).
    """
    types = []
    for _ in range(natoms_total // 4):
        types.extend([1, 1, 2, 2])
    if len(types) < natoms_total:
        types.extend([1] * (natoms_total - len(types)))
    return types, natoms_total // 2, natoms_total // 2


def _l12_types(natoms_total, comp_pt):
    """L1_2 (Cu3Au): corner site holds the minority element.

    x_Pt = 0.25 -> Fe3Pt (corner = Pt, face centres = Fe);
    x_Pt = 0.75 -> FePt3 (corner = Fe, face centres = Pt).
    basis order: 0 = corner, 1..3 = face centres.
    """
    corner_is_pt = abs(comp_pt - 0.25) < 1e-6
    types = []
    for _ in range(natoms_total // 4):
        if corner_is_pt:
            types.extend([2, 1, 1, 1])
        else:
            types.extend([1, 2, 2, 2])
    if len(types) < natoms_total:
        types.extend([1] * (natoms_total - len(types)))
    n_pt = sum(1 for t in types if t == 2)
    return types, natoms_total - n_pt, n_pt


# intent: Generate an A1 (random fcc), L1_0 or L1_2 ordered cell
# allies: called by lmp_helper.gen_structure(), run_*.py scripts
# sidefx: io (writes data.fept_*.lmp to data/ or given outpath)
# purity: impure
# errors: ValueError on unknown kind / L1_0 with x_Pt != 0.5
def generate_structure(nx, ny, nz, comp_pt, outfile, lc_override=None,
                       kind='a1', c_over_a=None):
    """Generate a supercell data file.

    Parameters
    ----------
    nx, ny, nz : int
        Supercell replication along x, y and z (the box is nx*a x ny*a x nz*c).
    comp_pt : float
        Pt fraction (0.0 = pure Fe, 1.0 = pure Pt). For kind='l10' must be 0.5.
    outfile : str
        Path to output LAMMPS data file.
    lc_override : float or None
        Explicit seed lattice constant a (Angstrom).
    kind : 'a1' | 'l10' | 'l12'
        a1 = random fcc solid solution, l10 = ordered CuAu-I (x_Pt=0.5),
        l12 = ordered Cu3Au (x_Pt=0.25 Fe3Pt or 0.75 FePt3).
    c_over_a : float or None
        L1_0 only: explicit tetragonal ratio (default 0.966).
    """
    nx, ny, nz = int(nx), int(ny), int(nz)
    if min(nx, ny, nz) < 1:
        raise ValueError('nx, ny, nz must be >= 1')
    comp_pt = float(comp_pt)
    if kind == 'l10' and abs(comp_pt - 0.5) > 1e-6:
        raise ValueError(
            'L1_0 (упорядоченная CuAu-I) существует только при x_Pt = 0.5, '
            'а задано x_Pt = {:.3f}; выберите A1 для других составов'
            .format(comp_pt))
    if kind == 'l12' and min(abs(comp_pt - 0.25), abs(comp_pt - 0.75)) > 1e-6:
        raise ValueError(
            'L1_2 (упорядоченная Cu3Au) существует при x_Pt = 0.25 (Fe3Pt) '
            'или 0.75 (FePt3), а задано x_Pt = {:.3f}; выберите A1 для '
            'других составов'.format(comp_pt))
    a, c, lc_note = lattice_constant(comp_pt, lc_override, kind=kind,
                                     c_over_a=c_over_a)
    print("cell kind = {}  a = {:.4f} A  c = {:.4f} A  ({})"
          .format(kind, a, c, lc_note))
    natoms_total = 4 * nx * ny * nz

    if kind == 'l10':
        types, n_fe, n_pt = _l10_types(natoms_total)
    elif kind == 'l12':
        types, n_fe, n_pt = _l12_types(natoms_total, comp_pt)
    else:
        types, n_fe, n_pt = _a1_types(natoms_total, comp_pt)

    # Lattice vectors: fcc basis scaled by (a, a, c) - for A1 c == a.
    basis = [
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.0),
        (0.5, 0.0, 0.5),
        (0.0, 0.5, 0.5),
    ]
    atoms = []
    aid = 0
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                for dx, dy, dz in basis:
                    x = (ix + dx) * a
                    y = (iy + dy) * a
                    z = (iz + dz) * c
                    aid += 1
                    atoms.append((aid, x, y, z))

    # FIX: box per axis, not a cube of max(nx,ny,nz) - an orthorhombic
    # cell must not carry vacuum layers along the short axes.
    lx, ly, lz = nx * a, ny * a, nz * c

    with open(outfile, 'w') as f:
        label = {'l10': 'L1_0', 'l12': 'L1_2'}.get(kind, 'fcc(A1)')
        f.write("Fe-Pt {} solid solution, comp_Pt={:.2f}, "
                "a={:.4f}, c={:.4f}, box={:.3f}x{:.3f}x{:.3f}\n\n"
                .format(label, comp_pt, a, c, lx, ly, lz))
        f.write("{} atoms\n".format(natoms_total))
        f.write("2 atom types\n\n")
        f.write("0.0 {:.6f} xlo xhi\n".format(lx))
        f.write("0.0 {:.6f} ylo yhi\n".format(ly))
        f.write("0.0 {:.6f} zlo zhi\n\n".format(lz))
        f.write("Atoms\n\n")
        for (aid_, x, y, z), tp in zip(atoms, types):
            f.write("{} {} {:.6f} {:.6f} {:.6f}\n".format(aid_, tp, x, y, z))

    print("Wrote {} atoms (xFe={}, xPt={}) box {:.3f}x{:.3f}x{:.3f} -> {}"
          .format(natoms_total, n_fe, n_pt, lx, ly, lz, outfile))
    return outfile


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Generate Fe-Pt supercell (A1 random or L1_0 ordered)')
    ap.add_argument('nx', type=int)
    ap.add_argument('ny', type=int)
    ap.add_argument('nz', type=int)
    ap.add_argument('comp', type=float, help='x_Pt (L1_0 requires 0.5)')
    ap.add_argument('outfile')
    ap.add_argument('lc', nargs='?', type=float, default=None,
                    help='seed lattice constant a in Angstrom (optional)')
    ap.add_argument('--kind', default='a1', choices=KINDS,
                    help='a1 = random fcc solution, l10 = ordered CuAu-I '
                         '(x_Pt=0.5), l12 = ordered Cu3Au '
                         '(x_Pt=0.25 Fe3Pt / 0.75 FePt3)')
    ap.add_argument('--c-over-a', type=float, default=None,
                    help='L1_0 tetragonal ratio c/a (default 0.966)')
    args = ap.parse_args(argv)
    try:
        generate_structure(args.nx, args.ny, args.nz, args.comp, args.outfile,
                           lc_override=args.lc, kind=args.kind,
                           c_over_a=args.c_over_a)
    except ValueError as e:
        print('error: {}'.format(e), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
