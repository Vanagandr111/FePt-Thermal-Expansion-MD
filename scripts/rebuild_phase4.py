#!/usr/bin/env python
"""
rebuild_phase4.py — Regenerate Phase 4 artifacts from existing logs.
All 20 production runs already exist in output_v4/logs/.
This script: CSV + plots + integrity check.

Usage:
    python scripts/rebuild_phase4.py

# module-purpose: Rebuild analysis artifacts from existing LAMMPS logs
# entry-points: main()
# main-flows:
#   1. scan logs/ -> parse production data -> write CSV
#   2. generate plots (a_vs_T, a_vs_comp, facets) -> integrity check
# related-modules: lmp_helper (parse_production, write_csv, make_plots,
#                               integrity_check, print_trends)
"""
import os
import math
import re
import csv
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_PROJ, "output_v4")
_LOGS = os.path.join(_OUT, "logs")
_NATOMS = 256
_COMPS = [0.0, 0.25, 0.5, 0.75, 1.0]
_TEMPS = [300, 600, 900, 1200]


# -- Log parsing --
def parse_log(logpath):
    """
    Parse a single LAMMPS log file for production data.

    # intent: Extract a_mean, a_std, drift, n_points from one log file
    # allies: main() (called per log file)
    # sidefx: io (reads .lmp file)
    # purity: impure
    # errors: returns {"n_points": 0} on missing / too-small file
    """
    if not os.path.exists(logpath) or os.path.getsize(logpath) < 100:
        return {"n_points": 0}
    with open(logpath, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    result_a = None
    for line in text.split("\n"):
        if "RESULT:" in line and "A=" in line:
            m = re.search(r"A=([\d.]+)", line)
            if m:
                result_a = float(m.group(1))

    in_prod = False
    a_vals, vol_vals, press_vals = [], [], []
    for line in text.split("\n"):
        s = line.strip()
        if "PRODUCTION_START" in s:
            in_prod = True
            continue
        if "PRODUCTION_DONE" in s:
            break
        if in_prod and s and s[0].isdigit():
            parts = s.split()
            if len(parts) >= 9:
                try:
                    vol = float(parts[5])
                    a = (vol * 4 / _NATOMS) ** (1 / 3)
                    a_vals.append(a)
                    vol_vals.append(vol)
                    press_vals.append(float(parts[4]))
                except Exception:
                    pass

    if not a_vals:
        # fallback: parse post-EQ
        in_prod = False
        for line in text.split("\n"):
            s = line.strip()
            if "EQ_DONE" in s:
                in_prod = True
                continue
            if "RESULT:" in s:
                break
            if in_prod and s and s[0].isdigit():
                parts = s.split()
                if len(parts) >= 9:
                    try:
                        vol = float(parts[5])
                        a = (vol * 4 / _NATOMS) ** (1 / 3)
                        a_vals.append(a)
                    except Exception:
                        pass

    if not a_vals:
        return {"n_points": 0, "a_mean": None, "result_a": result_a}

    n = len(a_vals)
    mean_a = sum(a_vals) / n
    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a_vals) / max(n - 1, 1))
    mean_vol = sum(vol_vals) / n if vol_vals else 0
    mean_press = sum(press_vals) / n if press_vals else None
    std_press = math.sqrt(sum((p - mean_press) ** 2 for p in press_vals) / max(len(press_vals) - 1, 1)) if press_vals else None
    half = n // 2
    drift = sum(a_vals[half:]) / max(n - half, 1) - sum(a_vals[:half]) / max(half, 1)

    return {
        "a_mean": mean_a,
        "a_std": std_a,
        "drift": drift,
        "n_points": n,
        "result_a": result_a,
        "mean_vol": mean_vol,
        "mean_press": mean_press,
        "std_press": std_press,
    }


# -- CTE calculation --
def _linear_fit(xs, ys):
    """
    Simple linear regression.

    # intent: Compute slope, intercept, R-squared for CTE fitting
    # allies: calc_cte_report
    # sidefx: none
    # purity: pure
    # errors: returns (0,0,0) if n < 2 or denom == 0
    """
    n = len(xs)
    if n < 2:
        return 0, 0, 0
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0, 0, 0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - sy / n) ** 2 for y in ys)
    r_sq = 1 - ss_res / ss_tot if ss_tot != 0 else 0
    return slope, intercept, r_sq


def calc_cte_report(a_vals):
    """
    Calculate comprehensive CTE report for one composition.

    Parameters
    ----------
    a_vals : list of (T, a_mean)
        Sorted by T, e.g. [(300, 3.929), (600, 3.937), ...]

    # intent: Compute 2-point CTE, fitted CTE, segmental CTE, uncertainty range
    # allies: main() (writes CSV), _linear_fit
    # sidefx: none
    # purity: pure
    # errors: returns None if < 2 points
    """
    if not a_vals or len(a_vals) < 2:
        return None

    pts = sorted(a_vals, key=lambda x: x[0])
    ts = [p[0] for p in pts]
    avs = [p[1] for p in pts]

    rise = avs[-1] - avs[0]
    temp_range = ts[-1] - ts[0]
    alpha_2pt = rise / avs[0] / temp_range if temp_range > 0 else 0

    slope, intercept, r_sq = _linear_fit(ts, avs)
    alpha_fit = slope / avs[0]
    delta_a_fit = slope * temp_range

    alphas_seg = []
    seg_labels = []
    for i in range(len(pts) - 1):
        dT = ts[i + 1] - ts[i]
        if dT > 0:
            a_seg = (avs[i + 1] - avs[i]) / avs[i] / dT
            alphas_seg.append(a_seg)
            seg_labels.append('{}-{}K'.format(ts[i], ts[i + 1]))

    all_alphas = [alpha_2pt, alpha_fit] + alphas_seg
    alpha_min = min(all_alphas)
    alpha_max = max(all_alphas)

    return {
        'n_points': len(pts),
        'T_min': ts[0],
        'T_max': ts[-1],
        'a_min': avs[0],
        'a_max': avs[-1],
        'delta_a_rise': rise,
        'delta_a_fit': delta_a_fit,
        'alpha_2pt': alpha_2pt,
        'alpha_fit': alpha_fit,
        'r_squared': r_sq,
        'alpha_segmental': alphas_seg,
        'seg_labels': seg_labels,
        'alpha_min': alpha_min,
        'alpha_max': alpha_max,
        'alpha_range': alpha_max - alpha_min,
    }


# -- Main --
def main():
    """
    # intent: Rebuild all Phase 4 artifacts from existing logs
    # allies: parse_log, calc_cte_report
    # sidefx: io (writes output_v4/ CSVs + integrity + plots)
    # purity: impure
    # errors: returns 1 if log dir missing
    """
    import lmp_helper as lmp  # avoid circular at module level

    if not os.path.isdir(_LOGS):
        print("ERROR: no logs dir at " + _LOGS)
        return 1

    print("=" * 60)
    print("  Rebuilding Phase 4 from logs")
    print("  Logs: " + _LOGS)
    print("  Output: " + _OUT)
    print("=" * 60)

    # TEMP: parse all logs using local parse_log for compatibility
    # reason: lmp_helper.parse_production() signature differs slightly
    # remove-after: after lmp_helper refactor, switch to lmp.parse_production
    results = {}
    for comp in _COMPS:
        for T in _TEMPS:
            logpath = os.path.join(_LOGS, 'log_{:.2f}_{}.lmp'.format(comp, T))
            p = parse_log(logpath)
            results[(comp, T)] = p
            if p.get('a_mean'):
                print('  {:>6.2f} {:>5}: a={:.6f} n={}'.format(comp, T, p['a_mean'], p['n_points']))

    # Restore seed from logs
    seed = None
    for logname in sorted(os.listdir(_LOGS)):
        if logname.startswith("log_") and logname.endswith(".lmp"):
            logpath = os.path.join(_LOGS, logname)
            with open(logpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = re.search(r'seed=(\d+)', line)
                    if m:
                        seed = int(m.group(1))
                        break
            if seed:
                break

    # Write CSV
    comps = _COMPS
    temps = _TEMPS
    csv_path = os.path.join(_OUT, "all_results.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f, delimiter=";")
        header = ["x_Pt", "T_K", "a_mean_Angstrom", "a_std_Angstrom",
                   "result_last_point", "drift", "n_points",
                   "mean_press_bar", "std_press_bar"]
        if seed:
            header += ["seed"]
        w.writerow(header)
        for comp in comps:
            for T in temps:
                p = results.get((comp, T), {})
                if p and p.get("a_mean") is not None:
                    row = [
                        "{:.2f}".format(comp), T,
                        "{:.6f}".format(p["a_mean"]),
                        "{:.6f}".format(p.get("a_std", 0)),
                        "{:.6f}".format(p.get("result_a", 0) or 0),
                        "{:.6e}".format(p.get("drift", 0)),
                        p.get("n_points", 0),
                        "{:.1f}".format(p.get("mean_press", 0) or 0),
                        "{:.1f}".format(p.get("std_press", 0) or 0),
                    ]
                    if seed:
                        row += [seed]
                    w.writerow(row)
    print("\n  CSV: " + csv_path)

    # Integrity check
    integrity_path = os.path.join(_OUT, "integrity_check_v4.txt")
    ok_count = sum(1 for p in results.values() if p and p.get("a_mean") is not None)
    fail_count = len(comps) * len(temps) - ok_count
    with open(integrity_path, "w", encoding="utf-8") as f:
        f.write("Fe-Pt Phase 4 -- Integrity Check (rebuilt)\n")
        f.write("Seed: {}\n".format(seed or "unknown"))
        f.write("=" * 60 + "\n")
        for comp in comps:
            for T in temps:
                p = results.get((comp, T), {})
                if p and p.get("a_mean") is not None:
                    f.write("  v x_Pt={:.2f} T={}: a={:.6f} n={} drift={:.2e}\n".format(
                        comp, T, p["a_mean"], p.get("n_points", 0), p.get("drift", 0)))
                else:
                    f.write("  x x_Pt={:.2f} T={}: NO DATA\n".format(comp, T))
        f.write("=" * 60 + "\n")
        f.write("OK: {} verified / Failures: {} / Total: {}\n".format(
            ok_count, fail_count, ok_count + fail_count))
    print("  Integrity: " + integrity_path)

    # PT benchmark
    pt300 = results.get((1.0, 300), {})
    pt1200 = results.get((1.0, 1200), {})
    if pt300.get("a_mean") and pt1200.get("a_mean"):
        alpha = (pt1200["a_mean"] - pt300["a_mean"]) / pt300["a_mean"] / 900
        print("\n  Pt benchmark:")
        print("  a(300K) = {:.6f} (expected ~3.929)".format(pt300["a_mean"]))
        print("  a(1200K) = {:.6f} (expected ~3.956)".format(pt1200["a_mean"]))
        print("  a_Pt = {:.3e} (expected ~7.5e-6)".format(alpha))

    # CTE report
    print("\n  --- CTE Report ---")
    print("  {:>6} {:>10} {:>10} {:>10}".format("x_Pt", "a2pt", "a_fit", "R2"))
    print("  " + "-" * 42)
    cte_csv_path = os.path.join(_OUT, "cte_report.csv")
    with open(cte_csv_path, "w", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["x_Pt", "alpha_2pt", "alpha_fit", "r_squared"])
        for comp in comps:
            a_vals = [(T, results[(comp, T)]["a_mean"])
                      for T in temps
                      if (comp, T) in results and results[(comp, T)].get("a_mean")]
            cte = calc_cte_report(a_vals) if len(a_vals) == 4 else None
            if cte:
                print("  {:>6.2f} {:>10.3e} {:>10.3e} {:>10.4f}".format(
                    comp, cte["alpha_2pt"], cte["alpha_fit"], cte["r_squared"]))
                w.writerow(["{:.2f}".format(comp), cte["alpha_2pt"],
                           cte["alpha_fit"], cte["r_squared"]])
    print("  CTE CSV: " + cte_csv_path)

    # Plots
    try:
        lmp.make_plots(results, comps, temps, seed or 0, _OUT,
                       a_vs_T_fn="a_vs_T_all.png",
                       a_vs_T_facets_fn="a_vs_T_facets.png")
    except Exception as e:
        print("  Plot error: {}".format(e))

    print("\n  Done! {} OK / {} total".format(ok_count, ok_count + fail_count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
