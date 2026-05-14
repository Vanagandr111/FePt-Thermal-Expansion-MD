#!/usr/bin/env python3
"""Integrity check: verify every result matches raw log data."""
import os, re, math

PROJ = "/mnt/c/проекты/Nikolay"
os.chdir(PROJ)

NATOMS = 256

def parse_log(logpath):
    with open(logpath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    
    in_prod = False
    a_vals = []
    for line in text.split('\n'):
        s = line.strip()
        if 'PRODUCTION_START' in s: in_prod = True; continue
        if 'PRODUCTION_DONE' in s: in_prod = False; break
        if in_prod and s and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 6:
                try:
                    vol = float(parts[5])
                    a = (vol * 4 / NATOMS) ** (1/3)
                    a_vals.append(a)
                except: pass
    
    if not a_vals:
        return None, None
    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a)**2 for x in a_vals) / (n - 1))
    return mean_a, n

import glob
logs = sorted(glob.glob("output_v3/logs/log_*.lmp"))
print(f"Integrity check: {len(logs)} log files")
print("=" * 80)

# Read CSV
with open("output_v3/pt_calibration_matrix.csv") as f:
    csv_lines = f.readlines()
csv_header = csv_lines[0].strip().split(",")
csv_rows = {}
for line in csv_lines[1:]:
    parts = line.strip().split(",")
    d = dict(zip(csv_header, parts))
    csv_rows[d['label']] = d

errors = 0
for lp in logs:
    fname = os.path.basename(lp)
    tag = fname.replace('log_', '').replace('.lmp', '')
    raw_a, raw_n = parse_log(lp)
    if raw_a is None:
        print(f"❌ {tag}: FAILED to parse raw log")
        errors += 1
        continue
    
    if tag in csv_rows:
        csv_a = float(csv_rows[tag]['a_mean_Angstrom'])
        csv_n = int(csv_rows[tag]['n_points'])
        diff = abs(raw_a - csv_a)
        if diff > 1e-6:
            print(f"❌ {tag}: MISMATCH raw={raw_a:.6f} csv={csv_a:.6f} diff={diff:.2e}")
            errors += 1
        else:
            status = "✅" if csv_n == raw_n else "⚠️"
            print(f"  {status} {tag}: a={raw_a:.6f} n={raw_n} (csv: a={csv_a:.6f} n={csv_n})")
    else:
        print(f"⚠️  {tag}: not in CSV (raw a={raw_a:.6f}, n={raw_n})")

print("=" * 80)
if errors == 0:
    print("✅ ALL RESULTS VERIFIED against raw logs")
else:
    print(f"⚠️  {errors} errors found")

# Also check output_v2 Fe-Pt logs for reference
v2_logs = sorted(glob.glob("output_v2/logs_*/log_*.lmp"))
print(f"\nPhase 2 (Fe-Pt MEAM): {len(v2_logs)} log files available")
if v2_logs:
    for lp in v2_logs[:3]:
        raw_a, raw_n = parse_log(lp)
        print(f"  {os.path.basename(lp)}: a={raw_a:.6f} n={raw_n}")
