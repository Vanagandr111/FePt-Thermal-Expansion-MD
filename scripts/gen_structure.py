#!/usr/bin/env python3
"""
Generate fcc Fe-Pt solid solution LAMMPS data file.
Creates a supercell with random substitution for given composition.
"""
import sys
import random
import math

def generate_fcc(nx, ny, nz, lattice_const, comp_Pt, seed=42):
    """
    Generate fcc solid solution.
    comp_Pt = fraction of Pt atoms (0 to 1).
    Returns list of (x, y, z, atom_type, element)
    """
    random.seed(seed)
    atoms = []
    idx = 0
    
    # fcc basis: (0,0,0), (0.5,0.5,0), (0.5,0,0.5), (0,0.5,0.5)
    basis = [(0.0, 0.0, 0.0),
             (0.5, 0.5, 0.0),
             (0.5, 0.0, 0.5),
             (0.0, 0.5, 0.5)]
    
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                for bx, by, bz in basis:
                    x = (ix + bx) * lattice_const
                    y = (iy + by) * lattice_const
                    z = (iz + bz) * lattice_const
                    idx += 1
                    
                    # Random type assignment
                    if random.random() < comp_Pt:
                        atype = 2  # Pt
                        elem = "Pt"
                    else:
                        atype = 1  # Fe
                        elem = "Fe"
                    
                    atoms.append((idx, atype, elem, x, y, z))
    
    return atoms

def write_lammps_data(atoms, lattice_const, filename):
    """Write LAMMPS data file."""
    natoms = len(atoms)
    ntypes = 2
    
    # Count types
    type_counts = {1: 0, 2: 0}
    for _, atype, _, _, _, _ in atoms:
        type_counts[atype] = type_counts.get(atype, 0) + 1
    
    # Box dimensions
    xs = [a[3] for a in atoms]
    ys = [a[4] for a in atoms]
    zs = [a[5] for a in atoms]
    xlo, xhi = 0.0, max(xs) + lattice_const * 0.01
    ylo, yhi = 0.0, max(ys) + lattice_const * 0.01
    zlo, zhi = 0.0, max(zs) + lattice_const * 0.01
    
    with open(filename, 'w') as f:
        f.write(f"Fe-Pt fcc solid solution - LAMMPS data file\n\n")
        f.write(f"{natoms} atoms\n")
        f.write(f"{ntypes} atom types\n\n")
        f.write(f"{xlo:.6f} {xhi:.6f} xlo xhi\n")
        f.write(f"{ylo:.6f} {yhi:.6f} ylo yhi\n")
        f.write(f"{zlo:.6f} {zhi:.6f} zlo zhi\n\n")
        f.write("Masses\n\n")
        f.write("1 55.845  # Fe\n")
        f.write("2 195.084 # Pt\n\n")
        f.write("Atoms\n\n")
        
        for atom_id, atype, elem, x, y, z in atoms:
            f.write(f"{atom_id} {atype} {x:.6f} {y:.6f} {z:.6f}\n")
    
    return type_counts

def main():
    if len(sys.argv) < 4:
        print("Usage: gen_structure.py <nx> <ny> <nz> <comp_Pt> [output_file]")
        print("  comp_Pt: 0.0 to 1.0 (fraction of Pt atoms)")
        sys.exit(1)
    
    nx, ny, nz = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    comp_Pt = float(sys.argv[4])
    output = sys.argv[5] if len(sys.argv) > 5 else f"data.fept_c{comp_Pt:.2f}.lmp"
    
    # Initial lattice constant (will be relaxed in NPT)
    a0 = 3.85  # Angstrom, rough estimate for Fe-Pt
    
    atoms = generate_fcc(nx, ny, nz, a0, comp_Pt)
    type_counts = write_lammps_data(atoms, a0, output)
    
    natoms = len(atoms)
    nfe = type_counts.get(1, 0)
    npt = type_counts.get(2, 0)
    actual_comp = npt / natoms if natoms > 0 else 0
    
    print(f"Generated: {output}")
    print(f"  Atoms: {natoms} (Fe: {nfe}, Pt: {npt})")
    print(f"  Target comp: Pt = {comp_Pt:.2f}")
    print(f"  Actual comp:  Pt = {actual_comp:.4f}")
    print(f"  Box: {nx}x{ny}x{nz} supercell of fcc")

if __name__ == "__main__":
    main()
