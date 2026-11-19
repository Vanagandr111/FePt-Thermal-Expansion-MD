# -*- coding: utf-8 -*-
"""Order parameters for the phase-transition block (v2.4.0).

Three independent observables, each answering a different question:

* S(t)  -- Bragg-Williams long-range order of the CHEMICAL sublattices
           (Fe <-> Pt swapping). It says whether the crystal is
           chemically ordered (L1_0/L12) or disordered (A1).
* q4/q6 -- Steinhardt bond-orientational order. It says whether the
           crystal still has crystalline symmetry, i.e. whether a drop
           in S is chemical disordering or actual melting.
* rho   -- number density, the third melting/collapse witness.

Melting must not be reported as disordering: the acceptance test needs
S < 0.9 while q6 stays > 0.35.
"""
import math

import numpy as np

# Cutoff of the neighbour shell: first shell of fcc/a1 (a ~ 3.9 A) ends
# near 4.6 A; 5.0 A keeps 12 neighbours and rejects the second shell.
R_CUT_DEFAULT = 5.0
Q_WARN_CRYSTAL = 0.35        # q6 below this means "not a crystal anymore"


def corner_indices_from_scaled(sc, nx, ny, nz):
    """Corner sublattice from ALREADY KNOWN scaled positions.

    Must be evaluated on the structure AS GENERATED: the 0 K relaxation
    in run_point nudges the atoms off the ideal sites by more than the
    1e-4 tolerance, and then every corner index is lost (S came back
    as None for a perfect L1_2 cell).
    """
    n = np.array([nx, ny, nz], dtype=float)
    prod = sc * n
    frac = np.abs(prod - np.round(prod))
    return np.where((frac < 1e-4).all(axis=1))[0]


def sublattice_corner_indices(atoms, nx, ny, nz):
    """Corner indices of the AS-IS structure (see corner_indices_from_scaled)."""
    return corner_indices_from_scaled(atoms.get_scaled_positions(wrap=True),
                                      nx, ny, nz)


def layer_indices_from_scaled(sc, nz):
    """Even z-layers for L1_0 from known scaled positions."""
    layer = np.round(np.asarray(sc)[:, 2] * nz).astype(int) % 2
    return np.where(layer == 0)[0]


def sublattice_layer_indices(atoms, nz):
    """Indices of the even z-layers for L1_0 (layers alternate A/B)."""
    return layer_indices_from_scaled(atoms.get_scaled_positions(wrap=True),
                                     nz)


def bragg_williams(atoms, site_idx, element):
    """Long-range order S = (c_site - x) / (1 - x).

    `site_idx` are the sites that hold `element` in the perfectly ordered
    structure (corners for L1_2, even layers for L1_0). For a random A1
    solid solution c_site == x, so S == 0; for the perfect ordered cell
    c_site == 1, so S == 1.
    """
    if len(site_idx) == 0:
        return float('nan')
    x = sum(1 for s in atoms.get_chemical_symbols()
            if s == element) / float(len(atoms))
    if abs(1.0 - x) < 1e-9:
        return float('nan')
    c_site = sum(1 for i in site_idx
                 if atoms[int(i)].symbol == element) / float(len(site_idx))
    return (c_site - x) / (1.0 - x)


def steinhardt_q(atoms, l, r_cut=None):
    """Mean Steinhardt parameter q_l over all atoms with neighbours.

    q_lm = (1/N_b) sum_j Y_lm(theta_j, phi_j),
    q_l  = < sqrt( 4*pi/(2l+1) * sum_m |q_lm|^2 ) >.

    Reference values for the acceptance test: fcc q6 = 0.577,
    bcc q6 = 0.511, liquid q6 = 0.05-0.2.
    """
    from ase.neighborlist import neighbor_list
    from scipy.special import sph_harm_y
    n = len(atoms)
    i_idx, j_idx = neighbor_list('ij', atoms, R_CUT_DEFAULT)
    if len(i_idx) == 0:
        return float('nan')
    pos = atoms.get_positions()
    vec = pos[j_idx] - pos[i_idx]
    dist = np.linalg.norm(vec, axis=1)
    good = dist > 1e-8
    i_idx, vec, dist = i_idx[good], vec[good], dist[good]
    if r_cut is None:
        # keep ONLY the first coordination shell: the second and third
        # shells (6 + 24 neighbours) drag q6 of fcc from 0.577 down to
        # ~0.11 and hide the melting signal.
        r_cut = 1.25 * float(dist.min())
    keep = dist <= r_cut
    i_idx, vec, dist = i_idx[keep], vec[keep], dist[keep]
    if len(i_idx) == 0:
        return float('nan')
    theta = np.arccos(np.clip(vec[:, 2] / dist, -1.0, 1.0))
    phi = np.arctan2(vec[:, 1], vec[:, 0])
    counts = np.bincount(i_idx, minlength=n).astype(float)
    q_lm = np.zeros((2 * l + 1, n), dtype=complex)
    for k, m in enumerate(range(-l, l + 1)):
        y = sph_harm_y(l, m, theta, phi)
        np.add.at(q_lm[k], i_idx, y)
    nz = counts > 0
    q_lm[:, nz] /= counts[nz]
    per_atom = np.sqrt((4.0 * np.pi / (2 * l + 1)) *
                       np.sum(np.abs(q_lm[:, nz]) ** 2, axis=0))
    return float(per_atom.mean())


def steinhardt_q6_real(atoms, r_cut=R_CUT_DEFAULT):
    """Alias kept for callers that ask for q6 explicitly."""
    return steinhardt_q(atoms, 6, r_cut)


def mc_swap_sweep(atoms, calc, temp_k, attempts, idx_a, idx_b, rng):
    """K Metropolis Fe<->Pt swap attempts, energy only (no forces).

    Returns the acceptance fraction. Delta E is evaluated with the
    calculator in energy-only mode: no stress, no autograd - on the RTX
    3070 Ti a stress evaluation costs several times an energy one.
    """
    if temp_k <= 0 or attempts <= 0 or len(idx_a) == 0 or len(idx_b) == 0:
        return float('nan')
    k_b = 8.617333262145e-5          # eV/K
    beta = 1.0 / (k_b * float(temp_k))
    symbols = atoms.get_chemical_symbols()
    acc = 0
    try:
        e0 = atoms.get_potential_energy()
    except Exception:                 # noqa: BLE001
        return float('nan')
    for _ in range(int(attempts)):
        i = int(rng.choice(idx_a))
        j = int(rng.choice(idx_b))
        if symbols[i] == symbols[j]:
            continue
        symbols[i], symbols[j] = symbols[j], symbols[i]
        atoms.set_chemical_symbols(symbols)
        try:
            e1 = atoms.get_potential_energy()
        except Exception:             # noqa: BLE001
            symbols[i], symbols[j] = symbols[j], symbols[i]
            atoms.set_chemical_symbols(symbols)
            continue
        de = e1 - e0
        if de <= 0.0 or rng.random() < math.exp(-beta * de):
            e0 = e1
            acc += 1
        else:
            symbols[i], symbols[j] = symbols[j], symbols[i]
            atoms.set_chemical_symbols(symbols)
    return acc / float(attempts)


def number_density(atoms):
    """Atoms per A^3 (the melting witness together with q6)."""
    v = atoms.get_volume()
    return float(len(atoms) / v) if v > 0 else float('nan')
