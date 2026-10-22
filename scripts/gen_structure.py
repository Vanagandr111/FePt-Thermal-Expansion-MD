#!/usr/bin/env python
"""
gen_structure.py — Generate fcc Fe-Pt solid solution LAMMPS data file.
Creates a supercell with random substitution for given composition.
Output: data/fc c{comp}.lmp

# module-purpose: Generate FCT lattice LAMMPS data files for Fe-Pt alloy
# entry-points: generate_structure()
# main-flows:
#   1. create fcc lattice in LAMMPS data format
#   2. random substitution Fe -> Pt at given composition
#   3. write LAMMPS data file with atom coordinates
# related-modules: lmp_helper.gen_structure (caller), lmp_helper.DATA_DIR
"""
import random
import math
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── Seed lattice constants, one explicit table (no silent hardcode) ─────
# intent: sources for every seed value; override via generate_structure(lc=)
# allies: generate_structure (consumer), run_main_mace.py --lc (override)
# sidefx: none (pure data)
# purity: pure
# NOTE: v1.0 shipped a0=3.85 with the comment "rough estimate for Fe-Pt".
#       v1.5 rewrote this generator and hard-set 3.615 with NO derivation
#       recorded anywhere in git — so 3.615 is a historical seed, not a
#       computed one. It is kept only where changing it would break
#       comparability with every past run.
LC_TABLE = {
    # Pure Pt: our own MACE-MP-0 EOS fit (scripts/eos_pt.py): E(V) parabola,
    # fp32, a(0K)=4.0065 A (+2.21% vs experimental 3.92 A).
    'pt': 4.0065,
    # Pure Fe (fcc/gamma): our MACE-MP-0 EOS fit (scripts/eos_pt.py
    # --comp 0.00), same method as pt; a(0K)=3.5647 A.
    'fe': 3.5647,
    # Fe-Pt alloys: keep the historical v1.5 seed 3.615 A so all runs from
    # v1.0..v1.7 stay reproducible; alloys are relaxed in NPT anyway.
    'fept': 3.615,
}


# intent: pick the seed lattice constant by system, honoring an override
# allies: generate_structure (caller), LC_TABLE (data)
# sidefx: none
# purity: pure
def lattice_constant(comp_pt, lc_override=None):
    """Return (lc_angstrom, source_note)."""
    if lc_override is not None:
        return float(lc_override), 'explicit override'
    if comp_pt >= 0.999:
        return LC_TABLE['pt'], 'table[pt] = MACE-MP-0 EOS fit'
    if comp_pt <= 0.001:
        return LC_TABLE['fe'], 'table[fe] = MACE-MP-0 EOS fit (fcc)'
    return LC_TABLE['fept'], 'table[fept] = historical seed (v1.5, old-run comparability)'


# intent: Generate fcc Fe-Pt structure as LAMMPS data file
# allies: called by lmp_helper.gen_structure(), run_*.py scripts
# sidefx: io (writes data.fept_*.lmp to data/ or given outpath)
# purity: impure
# errors: raises on subprocess failure, writes empty file on bad comp
def generate_structure(nx, ny, nz, comp_pt, outfile, lc_override=None):
    """
    Generate fcc solid solution.

    Parameters
    ----------
    nx, ny, nz : int
        Supercell replication in each direction.
    comp_pt : float
        Pt fraction (0.0 = pure Fe, 1.0 = pure Pt).
    outfile : str
        Path to output LAMMPS data file.
    lc_override : float or None
        Explicit seed lattice constant (Angstrom); None = LC_TABLE by system.
    """
    lc, lc_note = lattice_constant(comp_pt, lc_override)
    print("seed lc = {:.4f} A  ({})".format(lc, lc_note))
    natoms_total = 4 * nx * ny * nz  # 4 atoms per fcc unit cell
    n_pt = int(round(natoms_total * comp_pt))
    n_fe = natoms_total - n_pt

    # Lattice vectors
    basis = [
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.0),
        (0.5, 0.0, 0.5),
        (0.0, 0.5, 0.5),
    ]

    # Generate all atom positions
    atoms = []
    aid = 0
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                for dx, dy, dz in basis:
                    x = (ix + dx) * lc
                    y = (iy + dy) * lc
                    z = (iz + dz) * lc
                    aid += 1
                    atoms.append((aid, x, y, z))

    # Assign types: 1=Fe, 2=Pt — shuffle and assign first N_pt as Pt
    random.seed(42)
    indices = list(range(natoms_total))
    random.shuffle(indices)
    types = [1] * natoms_total
    for idx in indices[:n_pt]:
        types[idx] = 2

    box_hi = max(nx, ny, nz) * lc

    with open(outfile, 'w') as f:
        f.write("Fe-Pt fcc solid solution, comp_Pt={:.2f}\n\n".format(comp_pt))
        f.write("{} atoms\n".format(natoms_total))
        f.write("2 atom types\n\n")
        f.write("0.0 {} xlo xhi\n".format(box_hi))
        f.write("0.0 {} ylo yhi\n".format(box_hi))
        f.write("0.0 {} zlo zhi\n\n".format(box_hi))
        f.write("Atoms\n\n")
        for (aid, x, y, z), tp in zip(atoms, types):
            f.write("{} {} {:.6f} {:.6f} {:.6f}\n".format(aid, tp, x, y, z))

    print("Wrote {} atoms (xFe={}, xPt={}) -> {}".format(natoms_total, n_fe, n_pt, outfile))
    return outfile


if __name__ == '__main__':
    # intent: CLI entry: python gen_structure.py nx ny nz comp_pt outfile [lc]
    # allies: generate_structure, lmp_helper.gen_structure
    # sidefx: io
    # purity: impure
    # errors: exits 1 on bad args
    if len(sys.argv) == 2 and sys.argv[1] in ('--help', '-h'):
        print("Usage: python gen_structure.py nx ny nz comp_pt outfile [lc_A]")
        sys.exit(0)
    if len(sys.argv) not in (6, 7):
        print("Usage: python gen_structure.py nx ny nz comp_pt outfile [lc_A]")
        sys.exit(1)
    nx = int(sys.argv[1])
    ny = int(sys.argv[2])
    nz = int(sys.argv[3])
    comp_pt = float(sys.argv[4])
    outfile = sys.argv[5]
    lc_override = float(sys.argv[6]) if len(sys.argv) == 7 else None
    generate_structure(nx, ny, nz, comp_pt, outfile, lc_override=lc_override)
