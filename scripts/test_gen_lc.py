#!/usr/bin/env python
"""Generate fcc data file with custom lc for testing."""
import random, os, sys

def gen(nx, ny, nz, comp_pt, lc, outfile):
    natoms = 4 * nx * ny * nz
    n_pt = int(round(natoms * comp_pt))
    
    basis = [(0,0,0), (0.5,0.5,0), (0.5,0,0.5), (0,0.5,0.5)]
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
    
    random.seed(42)
    indices = list(range(natoms))
    random.shuffle(indices)
    types = [1] * natoms
    for idx in indices[:n_pt]:
        types[idx] = 2
    
    box_hi = max(nx, ny, nz) * lc
    
    with open(outfile, 'w') as f:
        f.write(f"Fe-Pt fcc, comp_Pt={comp_pt:.2f}, lc={lc:.3f}\n\n")
        f.write(f"{natoms} atoms\n")
        f.write("2 atom types\n\n")
        f.write(f"0.0 {box_hi} xlo xhi\n")
        f.write(f"0.0 {box_hi} ylo yhi\n")
        f.write(f"0.0 {box_hi} zlo zhi\n\n")
        f.write("Atoms\n\n")
        for (aid, x, y, z), tp in zip(atoms, types):
            f.write(f"{aid} {tp} {x:.6f} {y:.6f} {z:.6f}\n")
    
    fe = natoms - n_pt
    print(f"Wrote {natoms} atoms (Fe={fe}, Pt={n_pt}, lc={lc:.3f}) -> {outfile}")
    return outfile

if __name__ == '__main__':
    nx, ny, nz = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    comp = float(sys.argv[4])
    lc = float(sys.argv[5])
    out = sys.argv[6]
    gen(nx, ny, nz, comp, lc, out)
