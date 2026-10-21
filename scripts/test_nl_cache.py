"""Verlet-skin neighbour-list cache correctness test (lever D).

Guarantees the gated claim: within skin/2 displacement the cached list
filtered back to the model cutoff reproduces the ORIGINAL matscipy
builder's pair set AND edge order (array_equal), large displacements and
cutoff changes trigger a rebuild. Run: .venv-mace/Scripts/python.exe
scripts/test_nl_cache.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import mace.data.neighborhood as nb_orig  # noqa: E402
from run_main_mace import _install_nl_cache, read_lammps_data  # noqa: E402
import lmp_helper as lmp  # noqa: E402

CUTOFF = 6.0  # MACE-MP-0 r_max


def main():
    datafile = lmp.gen_structure(0.5, nx=2, ny=2, nz=2, force=True)
    atoms = read_lammps_data(datafile)
    pos = np.asarray(atoms.get_positions(), dtype=float)
    cell = np.asarray(atoms.cell.array, dtype=float)
    pbc = (True, True, True)

    _install_nl_cache(1.0)
    import mace.data.atomic_data as ad
    gn = ad.get_neighborhood

    ei0, sh0, us0, _ = nb_orig.get_neighborhood(pos, CUTOFF, pbc, cell)

    r = gn(pos, CUTOFF, pbc, cell)
    assert r[2].shape[1] > 0, 'empty rebuild'

    # the skin buffer really exists: more pairs at cutoff+skin than at
    # cutoff, and the cache returns them filtered down to the cutoff
    r_full, _, _, _ = nb_orig.get_neighborhood(pos, CUTOFF + 1.0, pbc, cell)
    assert r_full.shape[1] > ei0.shape[1], 'no skin buffer to cache'
    assert r[0].shape[1] == ei0.shape[1], 'rebuild+filter != original'

    ei_h, sh_h, us_h, _ = gn(pos, CUTOFF, pbc, cell)
    assert np.array_equal(ei_h, ei0), 'edge order differs from orig'
    assert np.array_equal(sh_h, sh0), 'shifts differ from orig'
    assert np.array_equal(us_h, us0), 'unit shifts differ from orig'
    print('OK: same pairs AND same order as original builder '
          '({} edges from a {}-edge skin buffer)'.format(
              ei_h.shape[1], r_full.shape[1]))

    for eps in (1e-4, 2e-4, 4e-4):
        r = gn(pos + eps, CUTOFF, pbc, cell)
        r0 = nb_orig.get_neighborhood(pos + eps, CUTOFF, pbc, cell)
        assert np.array_equal(r[0], r0[0]), \
            'pair set incomplete at disp {} ({} vs {})'.format(
                eps, r[0].shape[1], r0[0].shape[1])
    print('OK: pair set complete under small displacements (<= skin/2)')

    r = gn(pos + 0.6, CUTOFF, pbc, cell)
    r0 = nb_orig.get_neighborhood(pos + 0.6, CUTOFF, pbc, cell)
    assert r[0].shape[1] == r0[0].shape[1], 'rebuild after big shift'
    print('OK: rebuild on displacement > skin/2 ({} edges)'.format(
        r[0].shape[1]))

    r = gn(pos, CUTOFF - 0.5, pbc, cell)
    r0 = nb_orig.get_neighborhood(pos, CUTOFF - 0.5, pbc, cell)
    assert r[0].shape[1] == r0[0].shape[1], 'rebuild on cutoff change'
    print('OK: rebuild on cutoff change')
    print('ALL PASS')


if __name__ == '__main__':
    main()
