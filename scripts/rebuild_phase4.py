#!/usr/bin/env python
"""
rebuild_phase4.py — Regenerate Phase 4 artifacts from existing logs.
All 20 production runs already exist in output_v4/logs/.
This script: CSV + plots + integrity check.
"""
import os, math, re, csv, sys

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PROJ, "output_v4")
LOGS = os.path.join(OUT, "logs")
NATOMS = 256
COMPS = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPS = [300, 600, 900, 1200]


def parse_log(logpath):
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
                    a = (vol * 4 / NATOMS) ** (1 / 3)
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
                        a = (vol * 4 / NATOMS) ** (1 / 3)
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
    std_press = (
        math.sqrt(sum((p - mean_press) ** 2 for p in press_vals) / max(len(press_vals) - 1, 1))
        if press_vals and len(press_vals) > 1
        else None
    )
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


def write_csv(parsed):
    csv_path = os.path.join(OUT, "all_results.csv")
    with open(csv_path, "w") as f:
        f.write(
            "x_Pt,T_K,a_mean_Angstrom,a_std_Angstrom,result_last_point,drift,"
            "n_points,mean_press_bar,std_press_bar,runtime_s\n"
        )
        for comp in COMPS:
            for T in TEMPS:
                p = parsed.get((comp, T), {})
                if p and p.get("a_mean") is not None:
                    pm = p.get("mean_press", 0) or 0
                    sp = p.get("std_press", 0) or 0
                    f.write(
                        f"{comp:.2f},{T},{p['a_mean']:.6f},{p['a_std']:.6f},"
                        f"{p.get('result_a', 0) or 0:.6f},{p.get('drift', 0):.6e},"
                        f"{p.get('n_points', 0)},{pm:.1f},{sp:.1f},0\n"
                    )
    print(f"  CSV: {csv_path}")

    for comp in COMPS:
        comp_csv = os.path.join(OUT, f"a_T_comp_{comp:.2f}.csv")
        with open(comp_csv, "w") as f:
            f.write("x_Pt,T_K,a_mean_Angstrom\n")
            for T in TEMPS:
                p = parsed.get((comp, T), {})
                if p and p.get("a_mean") is not None:
                    f.write(f"{comp:.2f},{T},{p['a_mean']:.6f}\n")
    print("  Per-composition CSVs ✓")


def plot_results(parsed):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    # 1. a(T) all comps
    fig, ax = plt.subplots(figsize=(10, 7))
    for ci, comp in enumerate(COMPS):
        pts = [
            (T, parsed[(comp, T)])
            for T in TEMPS
            if (comp, T) in parsed and parsed[(comp, T)].get("a_mean") is not None
        ]
        if pts:
            pts.sort()
            ts = [p[0] for p in pts]
            avs = [p[1]["a_mean"] for p in pts]
            errs = [p[1].get("a_std", 0) for p in pts]
            ax.errorbar(
                ts, avs, yerr=errs, fmt="o-", color=colors[ci],
                label=f"x_Pt={comp:.2f}", markersize=7, linewidth=2, capsize=3,
            )
            ax.fill_between(
                ts,
                [a - s for a, s in zip(avs, errs)],
                [a + s for a, s in zip(avs, errs)],
                alpha=0.15,
                color=colors[ci],
            )
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Lattice parameter a (Å)")
    ax.set_title("Fe-Pt Thermal Expansion — Phase 4 (Long Protocol)")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "a_vs_T_all_v4.png"), dpi=150)
    plt.close(fig)
    print("  Plot: a_vs_T_all_v4.png")

    # 2. a(comp) at fixed T
    fig, ax = plt.subplots(figsize=(10, 7))
    for Ti, T in enumerate(TEMPS):
        pts = [
            (comp, parsed[(comp, T)]["a_mean"])
            for comp in COMPS
            if (comp, T) in parsed and parsed[(comp, T)].get("a_mean") is not None
        ]
        if pts:
            pts.sort()
            xs = [p[0] for p in pts]
            avs = [p[1] for p in pts]
            ax.plot(xs, avs, "o-", label=f"T={T}K", markersize=8, linewidth=2)
    ax.set_xlabel("Pt fraction x_Pt")
    ax.set_ylabel("Lattice parameter a (Å)")
    ax.set_title("Fe-Pt a(comp) at fixed temperatures — Phase 4")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "a_vs_comp_v4.png"), dpi=150)
    plt.close(fig)
    print("  Plot: a_vs_comp_v4.png")

    # 3. Facets 2x3
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    fig.suptitle(
        "Fe-Pt Thermal Expansion — Phase 4 (Long Protocol)",
        fontsize=14,
        fontweight="bold",
    )
    axes_flat = axes.flatten()
    for ci, comp in enumerate(COMPS):
        ax = axes_flat[ci]
        pts = [
            (T, parsed[(comp, T)])
            for T in TEMPS
            if (comp, T) in parsed and parsed[(comp, T)].get("a_mean") is not None
        ]
        if pts:
            pts.sort()
            ts = [p[0] for p in pts]
            vs = [p[1] for p in pts]
            avs = [v["a_mean"] for v in vs]
            errs = [v.get("a_std", 0) for v in vs]
            ax.errorbar(ts, avs, yerr=errs, fmt="o-", color=colors[ci], capsize=4, markersize=6)
            rise = avs[-1] - avs[0]
            alpha_eff = rise / avs[0] / 900
            ax.set_title(
                f"x_Pt={comp:.2f}\nΔa={rise:.4f}Å α={alpha_eff:.2e}", fontsize=10
            )
            ax.set_xlabel("T (K)")
            ax.set_ylabel("a (Å)")
            ax.grid(alpha=0.3)
    for i in range(len(COMPS), len(axes_flat)):
        axes_flat[i].set_visible(False)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "a_vs_T_facets_v4.png"), dpi=150)
    plt.close(fig)
    print("  Plot: a_vs_T_facets_v4.png")


def write_integrity(parsed):
    lines = [
        "Fe-Pt Phase 4 — Integrity Check",
        "Protocol: 50000 eq + 100000 prod, Pdamp=10.0",
        "MEAM potential: PtFe.meam (Fe-Pt cross interaction)",
        "Grid: 5 comps x 4 temps = 20 points",
        "=" * 60,
    ]
    ok_count = 0
    fail_count = 0
    for comp in COMPS:
        for T in TEMPS:
            p = parsed.get((comp, T), {})
            if p and p.get("a_mean") is not None:
                ok_count += 1
                lines.append(
                    f"  x_Pt={comp:.2f} T={T}: a={p['a_mean']:.6f} "
                    f"n={p.get('n_points',0)} drift={p.get('drift',0):.2e}"
                )
            else:
                fail_count += 1
                lines.append(f"  x_Pt={comp:.2f} T={T}: NO DATA")
    lines.append("=" * 60)
    lines.append(f"OK: {ok_count} verified | Failures: {fail_count} | Total: {ok_count+fail_count}")

    # Pt benchmark
    pt_300 = parsed.get((1.0, 300), {})
    pt_1200 = parsed.get((1.0, 1200), {})
    if pt_300.get("a_mean") and pt_1200.get("a_mean"):
        a300 = pt_300["a_mean"]
        a1200 = pt_1200["a_mean"]
        alpha = (a1200 - a300) / a300 / 900
        lines.append("")
        lines.append("Pt benchmark:")
        lines.append(f"  a(300K) = {a300:.6f} A (expected ~3.929)")
        lines.append(f"  a(1200K) = {a1200:.6f} A (expected ~3.956)")
        lines.append(f"  alpha_eff = {alpha:.3e} (expected ~7.5e-6)")
        lines.append(f"  Da300 = {abs(a300-3.929):.6f} A from expected")
        lines.append(f"  Da1200 = {abs(a1200-3.956):.6f} A from expected")

    integrity_path = os.path.join(OUT, "integrity_check_v4.txt")
    with open(integrity_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Integrity: {integrity_path}")
    print(f"\n  OK: {ok_count}/{ok_count+fail_count} verified")
    return ok_count, fail_count, pt_300.get("a_mean"), pt_1200.get("a_mean")


def main():
    print("=" * 60)
    print("Phase 4 — Rebuild artifacts from existing logs")
    print("=" * 60)

    parsed = {}
    for comp in COMPS:
        for T in TEMPS:
            logpath = os.path.join(LOGS, f"log_fept_{comp:.2f}_T{T}.lmp")
            p = parse_log(logpath)
            parsed[(comp, T)] = p
            if p.get("a_mean"):
                print(f"  x_Pt={comp:.2f} T={T}: a={p['a_mean']:.6f} +-{p['a_std']:.6f} [{p['n_points']}pts]")
            else:
                print(f"  x_Pt={comp:.2f} T={T}: NO DATA")

    print("\n--- CSV ---")
    write_csv(parsed)

    print("\n--- Plots ---")
    try:
        plot_results(parsed)
    except ImportError:
        print("  [SKIP] matplotlib not available, install with: pip install matplotlib")

    print("\n--- Integrity ---")
    ok_count, fail_count, a300, a1200 = write_integrity(parsed)

    print("\n" + "=" * 60)
    if fail_count == 0:
        print(f"PHASE 4 REBUILD COMPLETE — {ok_count}/20 points verified")
    else:
        print(f"PHASE 4 REBUILD — {ok_count} ok, {fail_count} failures")
    print(f"  Output: {OUT}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
