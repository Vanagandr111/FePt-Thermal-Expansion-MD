
import sys, os
sys.path.insert(0, 'scripts')

from lmp_helper import run_lmp, PROJDIR

# Point to test: Fe (x_Pt=0.00) at 300K
x_pt = 0.00
temp = 300
label = "test_one_point"

in_file = os.path.join(PROJDIR, 'output_v4', 'long_fast', 'in', f'in_phase4_{x_pt:.2f}_{temp}.lmp')
log_file = os.path.join(PROJDIR, 'output_v4', 'long_fast', 'logs', f'log_phase4_{x_pt:.2f}_{temp}.lmp')

print(f"Input: {in_file}")
print(f"Log: {log_file}")
print(f"Exists: {os.path.isfile(in_file)}")

if not os.path.isfile(in_file):
    print("ERROR: input file not found!")
    sys.exit(1)

print(f"Running Fe (x_Pt={x_pt}) at T={temp}K with full production protocol...")
print(f"Using KOKKOS, 2 OMP threads")
print(f"Timeout: 7200s (2 hours)")

result = run_lmp(in_file, logfile=log_file, timeout=7200, omp_threads=2, use_kokkos=True)

ok = result.get('ok', False)
ec = result.get('exit_code', -1)
el = result.get('elapsed', 0)
tm = result.get('timeout', False)
cmd = result.get('cmd', '')
stdout = result.get('stdout', '')
stderr = result.get('stderr', '')

print(f"\nResult: OK={ok}, EXIT={ec}, ELAPSED={el:.1f}s, TIMEOUT={tm}")
print(f"Cmd: {cmd}")

if stdout:
    # Find lattice parameter in stdout
    lines = stdout.split('\n')
    print(f"\n=== Last 20 lines of stdout ===")
    for line in lines[-20:]:
        print(f"  {line.strip()}")
        
    # Parse lattice parameter
    import re
    a_vals = []
    for line in lines:
        m = re.search(r'a\s*=\s*([0-9.]+)', line)
        if m:
            val = float(m.group(1))
            a_vals.append((line.strip(), val))
    
    if a_vals:
        print(f"\n=== Lattice parameter 'a' values ===")
        for line, val in a_vals[-10:]:
            print(f"  a = {val:.6f}  ({line[:60]})")
    
    # Also check for errors
    for line in lines:
        if 'ERROR' in line:
            print(f"\n⚠️ ERROR found: {line.strip()}")
else:
    print("stdout is empty!")

if stderr:
    print(f"\n=== stderr ===")
    print(stderr[:500])

print("\nDONE")
