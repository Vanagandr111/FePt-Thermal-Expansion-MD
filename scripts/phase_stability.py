# -*- coding: utf-8 -*-
"""Phase stability: QHA free energies G(T) and the transition point.

Protocol after Correa et al., J. Chem. Theory Comput. 2025, 21, 12197
(acs.jctc.5c01387) - first stage of their three-stage workflow:

    G(T) = E0(V) + F_vib(T, V) + F_conf(T)

* E0(V)      static lattice energy after a positional relaxation at a
             fixed cell volume (five volumes around the P = 0 cell).
* F_vib(T,V) vibrational free energy from the phonon spectrum obtained
             by central differences on the FORCES (2N energy/force
             evaluations per Hessian, not 4N^2): a 2x2x2 supercell gives
             the Gamma-only spectrum of eight q-points. The three
             acoustic modes of the supercell (omega -> 0) are dropped -
             they diverge classically and are identical for both phases.
* F_conf     configurational entropy of the DISORDERED phase,
             S_conf = -k_B [x ln x + (1-x) ln(1-x)] per atom, so
             F_conf = -T * S_conf. Ordered L1_0 / L1_2 at S = 1 have
             F_conf = 0.

The fluctuation route (C_V from <E^2>-<E>^2) is deliberately NOT used:
the Berendsen thermostat/barostat is not a true canonical ensemble, the
integral of C_V/T loses the configurational term entirely, and at 1500 K
T*S_conf is about 0.09 eV/atom - the dominant part of the A1 vs ordered
transition.

Usage:
    python phase_stability.py --comp 0.25 --a-kind l12 --b-kind a1 \\
        --model potentials/gpu/mace-matpes-r2scan-0-medium.model
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('OMP_NUM_THREADS', '2')

import numpy as np                          # noqa: E402
from ase.io import read as ase_read          # noqa: E402

import gen_structure as gs                  # noqa: E402
import lmpdata                               # noqa: E402
import run_main_mace as rmm                  # noqa: E402
from ase.optimize import BFGS                # noqa: E402

K_B = 8.617333262145e-5      # eV/K
H_BAR = 6.582119569e-16      # eV*s
# sqrt(1 eV / (amu * A^2)) in rad/s
OMEGA_UNIT = math.sqrt(1.602176634e-19 / (1.66053906660e-27 * 1e-20))
MASS = {'Fe': 55.845, 'Pt': 195.084, 'Cu': 63.546}

SCALES = (0.96, 0.98, 1.00, 1.02, 1.04)
N_SUP = 2                    # 2x2x2 supercell -> 32 atoms, 96 modes
DELTA = 0.01                 # A, central-difference step


def build(kind, comp, system='fept', n_sup=N_SUP, a_scale=1.0):
    path = os.path.join(os.environ['TEMP'],
                        'qs_%s_%s_%s.lmp' % (kind, comp, a_scale))
    gs.generate_structure(n_sup, n_sup, n_sup, comp, path, kind=kind,
                          system=system)
    at = lmpdata.read_lammps_data(path)
    if abs(a_scale - 1.0) > 1e-9:
        at.set_cell(at.get_cell() * a_scale, scale_atoms=True)
    return at


def relax(at, fmax=0.01, steps=200):
    BFGS(at, logfile=None).run(fmax=fmax, steps=steps)
    return at


def hessian_forces(at, delta=DELTA):
    """H_ij = -dF_i/dx_j by central differences on the FORCES.

    2 * 3N evaluations (32 atoms -> 192), each one a full force call.
    """
    n = len(at)
    dim = 3 * n
    h = np.zeros((dim, dim))
    base = None
    for j in range(dim):
        a0 = j // 3
        c0 = j % 3
        for sign in (+1.0, -1.0):
            cell0 = at.get_cell().array.copy()
            pos0 = at.get_positions()
            p = pos0.copy()
            p[a0, c0] += sign * delta
            at.set_positions(p)
            f = at.get_forces()
            at.set_positions(pos0)
            at.set_cell(cell0, scale_atoms=False)
            if base is None:
                base = f.copy()
            h[:, j] += (-sign) * f.reshape(dim) / (2.0 * delta)
    h = 0.5 * (h + h.T)
    return h


def frequencies_eV(at):
    """Eigenvalues of the mass-weighted Hessian -> hbar*omega in eV."""
    h = hessian_forces(at)
    n = len(at)
    m = np.array([MASS.get(s, 1.0) for s in at.get_chemical_symbols()])
    mw = 1.0 / np.sqrt(np.repeat(m, 3))
    d = h * mw[:, None] * mw[None, :]
    w2 = np.linalg.eigvalsh(d)               # (rad/s)^2 after scaling
    w2 = np.clip(w2, 0.0, None)
    omega = np.sqrt(w2) * OMEGA_UNIT          # rad/s
    return H_BAR * omega                      # eV


def f_vib(freqs_ev, temp_k, n_drop=3):
    """Vibrational free energy per atom, eV. Drops the n_drop softest
    (acoustic) modes of the supercell."""
    f = np.sort(np.asarray(freqs_ev, dtype=float))
    if n_drop:
        f = f[n_drop:]
    f = f[f > 1e-9]
    if len(f) == 0:
        return 0.0
    if temp_k <= 0:
        return float(0.5 * f.sum() / _n_atoms_from_modes(freqs_ev))
    x = f / (K_B * temp_k)
    # ln(1-exp(-x)) is stable in this form
    terms = 0.5 * f + K_B * temp_k * np.log1p(-np.exp(-np.clip(x, 0, 700)))
    return float(terms.sum() / _n_atoms_from_modes(freqs_ev))


_N_ATOMS = 3 * N_SUP ** 3          # modes = 3 * natoms (set by caller)


def _n_modules_unused():
    return _N_ATOMS


def _n_atoms_from_modes(freqs):
    return len(freqs) // 3


def f_conf(temp_k, x):
    """Configurational free energy per atom, eV (ordered phases: x=0 or 1
    gives 0)."""
    if x <= 0.0 or x >= 1.0:
        return 0.0
    s_conf = -(x * math.log(x) + (1.0 - x) * math.log(1.0 - x))
    return -float(temp_k) * K_B * s_conf


def phase_curve(kind, comp, model_path, temps, a_ref=None, system='fept'):
    """E0(V), F_vib(T,V) and the QHA G(T) curve for one phase."""
    calc = rmm.FastMACECalculator(model_paths=[model_path], device='cuda',
                                  default_dtype='float32',
                                  compile_mode=None)
    if a_ref is None:
        seed = build(kind, comp, system, n_sup=1, a_scale=1.0)
        a_ref = (4.0 * seed.get_volume() / len(seed)) ** (1.0 / 3.0)
    rows = []
    for s in SCALES:
        at = build(kind, comp, system, n_sup=N_SUP, a_scale=s)
        at.calc = calc
        relax(at)
        e0 = float(at.get_potential_energy())
        freqs = frequencies_eV(at)
        vol = float(at.get_volume())
        per_atom = {'E0': e0 / len(at), 'V': vol, 'n': len(at),
                    'freqs': [round(float(v), 6) for v in freqs]}
        rows.append(per_atom)
        print('  [%s] scale=%.2f E0/atom=%.5f eV V=%.1f A3 modes=%d' % (
            kind, s, per_atom['E0'], vol, len(freqs)), flush=True)
    # QHA minimisation: for each T, parabola through (E0+F_vib)(V)
    curve = []
    vols = np.array([r['V'] for r in rows])
    e0s = np.array([r['E0'] for r in rows])
    order = np.argsort(vols)
    vols, e0s, rows = vols[order], e0s[order], [rows[i] for i in order]
    for T in temps:
        g = np.array([e0s[i] + f_vib(np.array(rows[i]['freqs']), T)
                      for i in range(len(rows))])
        k = int(np.argmin(g))
        lo, hi = max(0, k - 1), min(len(rows) - 1, k + 1)
        v_min, g_min = vols[k], g[k]
        if hi > lo and hi != lo:
            try:
                coef = np.polyfit(vols[lo:hi + 1], g[lo:hi + 1], 2)
                if coef[0] > 0:
                    v_star = -coef[1] / (2.0 * coef[0])
                    if vols[lo] <= v_star <= vols[hi]:
                        g_star = np.polyval(coef, v_star)
                        v_min, g_min = v_star, g_star
            except Exception:                  # noqa: BLE001
                pass
        curve.append({'T': float(T), 'G': float(g_min), 'V': float(v_min),
                      'F_vib': float(g_min - e0s[k])})
    return {'kind': kind, 'comp': comp, 'rows': rows, 'curve': curve}


def crossing(curve_a, curve_b, x):
    """First temperature where G_A - G_B changes sign (linear interp)."""
    diffs = [(c['T'], c['G'] - d['G'])
             for c, d in zip(curve_a, curve_b)]
    for (t0, d0), (t1, d1) in zip(diffs, diffs[1:]):
        # strict sign change only: an exact touch (or two identical
        # curves, d == 0 everywhere) is NOT a transition
        if d0 * d1 < 0:
            return t0 + (t1 - t0) * (-d0) / (d1 - d0)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--comp', type=float, default=0.25)
    ap.add_argument('--a-kind', default='l12')
    ap.add_argument('--b-kind', default='a1')
    ap.add_argument('--system', default='fept')
    ap.add_argument('--model', required=True)
    ap.add_argument('--t-min', type=float, default=300.0)
    ap.add_argument('--t-max', type=float, default=1800.0)
    ap.add_argument('--t-step', type=float, default=100.0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    temps = list(np.arange(args.t_min, args.t_max + 1, args.t_step))
    print('QHA: comp=%.2f  %s vs %s  T=%.0f..%.0f' % (
        args.comp, args.a_kind, args.b_kind, temps[0], temps[-1]),
        flush=True)
    a = phase_curve(args.a_kind, args.comp, args.model, temps,
                    system=args.system)
    b = phase_curve(args.b_kind, args.comp, args.model, temps,
                    system=args.system)
    # configurational term: only the disordered phase carries it
    if args.b_kind == 'a1':
        for row in b['curve']:
            row['G'] += f_conf(row['T'], args.comp)
            row['F_conf'] = f_conf(row['T'], args.comp)
        for row in a['curve']:
            row['F_conf'] = 0.0
    else:
        for row in a['curve'] + b['curve']:
            row.setdefault('F_conf', 0.0)
    t_tr = crossing(a['curve'], b['curve'], args.comp)
    out = {'comp': args.comp, 'a_kind': args.a_kind,
           'b_kind': args.b_kind, 'model': args.model,
           'T_tr': t_tr, 'a': a, 'b': b, 'temps': [float(t) for t in temps]}
    out_path = args.out or os.path.join(os.environ['TEMP'],
                                        'qha_%s_vs_%s.json' % (
                                            args.a_kind, args.b_kind))
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('T_tr = %s' % ('%.0f K' % t_tr if t_tr else
                         'no crossing in range'), flush=True)
    print('QHA_DONE', out_path, flush=True)


if __name__ == '__main__':
    main()
