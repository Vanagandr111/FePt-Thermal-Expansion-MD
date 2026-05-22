#!/usr/bin/env python
"""Test one LAMMPS point with KOKKOS."""
import sys, os, json

PROJDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJDIR, 'scripts'))

import lmp_helper as lmp

OUT = os.path.join(PROJDIR, 'output_v4', 'long_fast')
LOGS = os.path.join(OUT, 'logs')
os.makedirs(LOGS, exist_ok=True)

# Generate proper 2048-atom structure
print("Generating structure (8x8x8 = 2048 atoms)...")
datafile = lmp.gen_structure(0.50)

pot_line = "pair_coeff      * * potentials\\library.meam Fe Pt potentials\\PtFe.meam Fe Pt"

# Generate input file with KOKKOS
infile = lmp.write_input(
    datafile, 0.50, 500, OUT,
    pot_line, 500, 1000, 1.0, 10.0, 12345, "2.0",
    omp_threads=2, use_kokkos=True
)
print("Input file:", infile)
with open(infile) as f:
    print(f.read())

# Run LAMMPS with KOKKOS
logfile = os.path.join(LOGS, 'log_kokkos_0.50_500.lmp')
print("Running LAMMPS with KOKKOS...")
result = lmp.run_lmp(infile, logfile=logfile, timeout=120,
                     lmp_label="KOKKOS x_Pt=0.50 T=500K",
                     omp_threads=2, use_kokkos=True)
print(json.dumps(result, indent=2, default=str, ensure_ascii=False))

# Parse production
if result.get('ok'):
    p = lmp.parse_production(logfile, 2048)
    print("Production data:")
    print(json.dumps(p, indent=2, default=str, ensure_ascii=False))
