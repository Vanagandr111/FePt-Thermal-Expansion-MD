"""Test single LAMMPS point - without Kokkos."""
import sys, os

PROJDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJDIR, 'scripts'))

import lmp_helper as lmp

OUT = os.path.join(PROJDIR, 'output_v4')
os.makedirs(os.path.join(OUT, 'logs'), exist_ok=True)
os.makedirs(os.path.join(OUT, 'in'), exist_ok=True)

pot_line = "pair_coeff      * * potentials\\library.meam Fe Pt potentials\\PtFe.meam Fe Pt"

# Test with very short run to see if it completes at all
infile = lmp.write_input(
    os.path.join(PROJDIR, 'data', 'data.fept_c0.25.lmp'),
    0.25, 300, OUT, pot_line,
    50, 100, 1.0, 10.0, 100101, '1.0',  # tiny steps
    omp_threads=1, use_kokkos=False
)
logfile = os.path.join(OUT, 'logs', 'test_nokokkos.lmp')
print(f"Input: {infile}")
print(f"Log: {logfile}")

result = lmp.run_lmp(infile, logfile=logfile, timeout=300,
                     lmp_label='TEST NO-KOKKOS x_Pt=0.25 T=300K',
                     omp_threads=1, use_kokkos=False)  # <-- NO KOKKOS

print(f"\nOK: {result['ok']}")
print(f"Exit code: {result['exit_code']}")
print(f"Timeout: {result['timeout']}")
print(f"Elapsed: {result['elapsed']:.1f}s")

stderr = result.get('stderr', '')
if stderr:
    print(f"\nSTDERR ({len(stderr)} chars):")
    print(stderr[:500])

stdout = result.get('stdout', '')
if stdout:
    tail = stdout[-3000:]
    print(f"\nSTDOUT tail ({len(stdout)} chars total):")
    print(tail[:2000])

