"""Test MEAM for pure Pt from command line."""
import subprocess, os

os.chdir("/mnt/c/проекты/Nikolay")

# Write test input
test_input = """# Pt MEAM test
units metal
boundary p p p
atom_style atomic
read_data cal_pt/data.pt.lmp
pair_style meam
pair_coeff * * potentials/library.meam Pt
neighbor 2.0 bin
neigh_modify every 1 delay 0 check yes
thermo 100
thermo_style custom step temp pe ke press vol lx ly lz
minimize 1.0e-6 1.0e-8 1000 10000
fix nptfix all npt temp 300 300 1.0 iso 0.0 0.0 10.0
run 500
print "DONE"
"""

with open("/mnt/c/проекты/Nikolay/output_v3/test_meam.lmp", 'w') as f:
    f.write(test_input)

result = subprocess.run(
    ["cmd.exe", "/c",
     "C:\\\\проекты\\\\Nikolay\\\\_run_lmp.bat -in output_v3/test_meam.lmp -screen none"],
    capture_output=True, text=False, timeout=120
)

out = result.stdout.decode('cp1251', errors='replace') if result.stdout else ''
err = result.stderr.decode('cp1251', errors='replace') if result.stderr else ''

print(f"Exit: {result.returncode}")
print(f"---stdout (last 30 lines)---")
for line in out.split('\n')[-30:]:
    print(line)
if err:
    print(f"---stderr---")
    print(err[-2000:])
