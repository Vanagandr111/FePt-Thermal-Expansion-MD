# -*- coding: utf-8 -*-
"""Order parameters for the phase-transition block.

Three independent observables, each answering a different question:

* S(t)  -- Bragg-Williams long-range order of the CHEMICAL sublattices
           (Fe <-> Pt swapping). It says whether the crystal is
           chemically ordered (L1_0/L12) or disordered (A1).
* q4/q6 -- Steinhardt bond-orientational order. It says whether the
           crystal still has crystalline symmetry, i.e. whether a drop
           in S is chemical disordering or actual melting.
* rho   -- number density, the third melting/collapse witness.

Melting must not be reported as disordering: the acceptance test needs
S to fall while q6 stays above Q_WARN_CRYSTAL.

Physics notes (v2.4.5 customer review):

* S is taken as the MAXIMUM over all crystallographically equivalent
  sublattices, clipped to [0, 1]. Pinning a single sublattice makes an
  ordered cell that merely moved its order to another equivalent
  sublattice (or drifted its centre of mass) read S = -1/3 - worse
  than random - while the crystal is still perfectly ordered L1_2.
* Bond vectors MUST include the periodic image shift
  (neighbour_list 'S'): pos[j] - pos[i] alone points across the box in
  a periodic cell, which made q6 depend on the supercell size and rise
  above the fcc reference when heated.
* Neighbours are exactly the 12 nearest of each atom (adaptive to the
  thermally expanded cell), then q_lm is Lechner-Dellago averaged over
  the atom and its neighbours: ideal fcc gives q6 = 0.5745 +- 0.005
  and q4 = 0.1909 +- 0.005 at any cell size.
"""
import math

import numpy as np

# First coordination shell of fcc/a1 sits near 4.6 A at a ~ 3.9 A. The
# neighbour search itself uses a generous fixed radius; the strict
# top-12 selection afterwards is what defines the shell.
R_CUT_DEFAULT = 5.0
Q_WARN_CRYSTAL = 0.35        # q6 below this means "not a crystal anymore"
Q6_FCC_REF = 0.5745          # ideal fcc reference (acceptance test)


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


def sublattice_sites(kind, sc, nx, ny, nz):
    """One index array per crystallographically equivalent sublattice.

    L1_2 has 4: the corner site plus the three face sites (0.5,0,0),
    (0,0.5,0), (0,0,0.5). L1_0 has 2 layers per axis (6 total). A1 has
    no sublattice at all - the whole cell is one, so S sits at 0.
    """
    sc = np.asarray(sc, dtype=float)
    n = np.array([nx, ny, nz], dtype=float)
    prod = sc * n
    frac = np.abs(prod - np.round(prod))
    whole = frac < 1e-4
    if kind == 'l12':
        # fcc/L1_2 basis: corner (0,0,0) + the three FACE centres
        # (0.5,0.5,0), (0.5,0,0.5), (0,0.5,0.5) - two coordinates at
        # 0.5, one whole. (The edge midpoints (0.5,0,0) etc. are NOT
        # lattice sites: they made the face sublattices empty.)
        sites = [np.where(whole.all(axis=1))[0]]
        half = np.abs(frac - 0.5) < 1e-4
        for ax in range(3):
            mask = whole[:, ax].copy()
            for other in range(3):
                if other != ax:
                    mask &= half[:, other]
            sites.append(np.where(mask)[0])
        return sites
    if kind == 'l10':
        sites = []
        for ax in range(3):
            layer = np.round(prod[:, ax]).astype(int) % 2
            for parity in (0, 1):
                sites.append(np.where(layer == parity)[0])
        return sites
    return [np.arange(len(sc))]


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


def long_range_order(atoms, kind, comp, init_scaled, nx, ny, nz):
    """Best-matching sublattice order, clipped to [0, 1].

    Fixes the customer bug S = -1/3 at 1600 K: a single pinned
    sublattice reports -1/3 when the order simply lives on one of the
    other equivalent sublattices (a fully ordered L1_2 cell!). The
    invariant answer is the maximum over all equivalent sublattices.
    """
    if abs(1.0 - comp) < 1e-9 or abs(comp) < 1e-9:
        return float('nan')
    element = 'Pt' if comp <= 0.5 else 'Fe'   # minority species
    best = float('-inf')
    for idx in sublattice_sites(kind, init_scaled, nx, ny, nz):
        if len(idx) == 0:
            continue
        s = bragg_williams(atoms, idx, element)
        if s == s:                            # not NaN
            best = max(best, s)
    if best == float('-inf'):
        return float('nan')
    return max(0.0, min(1.0, best))


def _bonds_top12(atoms, r_max):
    """Bond vectors WITH periodic image shifts, strictly 12 nearest."""
    from ase.neighborlist import neighbor_list
    n = len(atoms)
    i_idx, j_idx, shift, d = neighbor_list('ijSd', atoms, r_max)
    good = d > 1e-8
    i_idx, j_idx, shift, d = (i_idx[good], j_idx[good],
                              shift[good], d[good])
    if len(i_idx) == 0:
        return None
    pos = atoms.get_positions()
    cell = np.asarray(atoms.cell)
    vec = pos[j_idx] + shift.dot(cell) - pos[i_idx]
    order = np.lexsort((d, i_idx))
    i_idx, j_idx, vec, d = (i_idx[order], j_idx[order],
                            vec[order], d[order])
    # exactly the 12 nearest neighbours of every atom: adaptive to the
    # thermally expanded cell, never swallows the second shell and
    # never loses neighbours to a shrinking 1.25*min cutoff
    cnt = np.bincount(i_idx, minlength=n)
    starts = np.repeat(np.cumsum(cnt) - cnt, cnt)
    rank = np.arange(len(i_idx)) - starts
    keep = rank < 12
    i_idx, j_idx, vec, d = (i_idx[keep], j_idx[keep],
                            vec[keep], d[keep])
    if len(i_idx) == 0:
        return None
    return i_idx, j_idx, vec, d, n


def steinhardt_q(atoms, l, r_cut=None):
    """Lechner-Dellago averaged q_l over all atoms with neighbours.

    Bond vectors include the periodic image shift (see module doc);
    neighbours are the strict 12 nearest; then

      q_lm(i)  = (1/12) sum_j Y_lm(theta_j, phi_j),
      q_bar_lm(i) = (q_lm(i) + sum_j q_lm(j)) / 13,
      q_l(i) = sqrt( 4*pi/(2l+1) * sum_m |q_bar_lm(i)|^2 ),

    and q_l is averaged over atoms. Ideal fcc: q6 = 0.5745, q4 = 0.1909
    (independent of the supercell size - verified 2x2x2 / 3x3x3 / 4x4x4).
    """
    from scipy.special import sph_harm_y
    r_max = float(r_cut) if r_cut else R_CUT_DEFAULT
    got = _bonds_top12(atoms, r_max)
    if got is None:
        return float('nan')
    i_idx, j_idx, vec, d, n = got
    theta = np.arccos(np.clip(vec[:, 2] / d, -1.0, 1.0))
    phi = np.arctan2(vec[:, 1], vec[:, 0])
    counts = np.bincount(i_idx, minlength=n).astype(float)
    q_lm = np.zeros((2 * l + 1, n), dtype=complex)
    for k, m in enumerate(range(-l, l + 1)):
        np.add.at(q_lm[k], i_idx, sph_harm_y(l, m, theta, phi))
    nz = counts > 0
    q_lm[:, nz] /= counts[nz]
    # Lechner-Dellago: average each atom with its own neighbours
    acc = np.zeros_like(q_lm)
    for k in range(2 * l + 1):
        np.add.at(acc[k], i_idx, q_lm[k, j_idx])
    q_bar = (q_lm + acc) / (counts + 1.0)
    per_atom = np.sqrt((4.0 * np.pi / (2 * l + 1)) *
                       np.sum(np.abs(q_bar[:, nz]) ** 2, axis=0))
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
