#!/usr/bin/env python3
"""Debug: test run_lmp directly."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
import lmp_helper as lmp

print("PROJDIR:", lmp.PROJDIR)
print("LMP:", lmp.find_lmp())

# Generate minimal input
outdir = os.path.join(lmp.OUTPUT, 'comp_test')
os.makedirs(outdir, exist_ok=True)
infile = os.path.join(outdir, 'in_300.lmp')

lines = [
    'units metal',
    'boundary p p p',
    'atom_style atomic',
    'read_data data/data.fept_c0.00.lmp',
    '',
    'pair_style meam',
    'pair_coeff * * potentials/library.meam Fe Pt potentials/PtFe.meam Fe Pt',
    '',
    'neighbor 2.0 bin',
    'neigh_modify every 1 delay 0 check yes',
    'thermo 100',
    'minimize 1.0e-6 1.0e-8 1000 10000',
    '',
    'fix nptfix all npt temp 300 300 0.5 iso 0.0 0.0 1.0',
    'thermo 1000',
    'run 500',
    '',
    'variable mya equal (4.0*vol/count(all))^(1.0/3.0)',
    'print RESULT_DONE',
]
with open(infile, 'w') as f:
    f.write('\n'.join(lines))

print("Infile:", infile)
print("Infile exists:", os.path.exists(infile))

try:
    r = lmp.run_lmp(infile, timeout=60)
    print("Exit code:", r.returncode)
    print("STDOUT:", r.stdout[:1000])
    print("STDERR:", r.stderr[:500])
except Exception as e:
    print("EXCEPTION:", type(e).__name__, str(e)[:500])
