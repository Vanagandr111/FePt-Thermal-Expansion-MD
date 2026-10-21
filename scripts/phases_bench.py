"""Phase micro-bench for the MACE hot path (gate diagnostics).

Measures the real per-call cost of the phases inside MACECalculator.calculate
without cProfile distortion:
  A. _atoms_to_batch          (config+neighbor list+padding+H2D copy)
  B. full calculate           (what one MD step pays)
  C. neighbor-list part       (config_from_atoms + AtomicData.from_config)
  D. B - A - overhead         ~= forward+results (GPU part, sync-excluded)

Run: .venv-mace/Scripts/python.exe scripts/phases_bench.py [--steps 200]
Math untouched: read-only timing of existing calls.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_main_mace import FastMACECalculator, find_model, read_lammps_data
import lmp_helper as lmp
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=200)
    ap.add_argument('--grid', type=int, default=4)
    args = ap.parse_args()

    import torch

    model = find_model(None)
    print('model:', model)
    calc = FastMACECalculator(model_paths=model, device='cuda',
                              compile_mode='default', use_bf16=True)
    datafile = lmp.gen_structure(0.5, nx=args.grid, ny=args.grid,
                                 nz=args.grid, force=True)
    atoms = read_lammps_data(datafile)
    atoms.calc = calc

    n = args.steps
    rng = np.random.default_rng(42)

    # warmup: compile + padding estimate
    for i in range(60):
        atoms.set_positions(atoms.positions + rng.normal(0, 1e-4, atoms.positions.shape))
        atoms.get_forces()
    torch.cuda.synchronize()

    def t_call(fn, loops):
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(loops):
            fn()
        torch.cuda.synchronize()
        return (time.perf_counter() - t0) * 1000.0 / loops

    pos0 = atoms.positions.copy()

    def do_batch():
        calc._atoms_to_batch(atoms)

    def do_full():
        atoms.set_positions(pos0 + rng.normal(0, 1e-4, pos0.shape))
        calc.calculate(atoms, properties=['forces'])

    ms_batch = t_call(do_batch, n)
    ms_full = t_call(do_full, n)

    # neighbor-list part: config_from_atoms + AtomicData.from_config
    from mace.tools import torch_geometric  # noqa: F401  (ensure imports warm)
    from mace.data import config_from_atoms, KeySpecification, AtomicData
    ks = KeySpecification(info_keys=calc.info_keys,
                          arrays_keys=calc.arrays_keys)
    from mace.tools import torch_tools

    def do_nl():
        with torch_tools.default_dtype(calc.default_dtype):
            cfg = config_from_atoms(atoms, key_specification=ks,
                                    head_name=calc.head)
            AtomicData.from_config(cfg, z_table=calc.z_table,
                                   cutoff=calc.r_max,
                                   heads=calc.available_heads)

    ms_nl = t_call(do_nl, n)

    # pad-graph build (fake padding)
    do_nl()
    from mace.data.padding_tools import build_fake_padding_graph

    def do_pad():
        with torch_tools.default_dtype(calc.default_dtype):
            cfg = config_from_atoms(atoms, key_specification=ks,
                                    head_name=calc.head)
            g = AtomicData.from_config(cfg, z_table=calc.z_table,
                                       cutoff=calc.r_max,
                                       heads=calc.available_heads)
        build_fake_padding_graph(
            g, num_atoms=1,
            num_edges=max(1, calc.pad_num_edges - int(g['edge_index'].shape[1])),
            r_max=calc.r_max)

    ms_pad = t_call(do_pad, n // 2)

    print()
    print('PHASES ms/call (steps={}, grid={}):'.format(n, args.grid))
    print('  A _atoms_to_batch          {:7.2f}'.format(ms_batch))
    print('  C neighbor-list part       {:7.2f}'.format(ms_nl))
    print('  C2 pad-graph build         {:7.2f}'.format(ms_pad))
    print('  B full calculate           {:7.2f}'.format(ms_full))
    print('  B - A (forward+results)    {:7.2f}'.format(ms_full - ms_batch))
    print('  padding: atoms={} edges={} -> {} edges'.format(
        calc.pad_num_atoms, calc.pad_num_edges, calc.pad_num_edges))
    print('PHASES_JSON ' + str({
        'batch': round(ms_batch, 2), 'nl': round(ms_nl, 2),
        'pad': round(ms_pad, 2), 'full': round(ms_full, 2),
        'fwd_results': round(ms_full - ms_batch, 2)}))


if __name__ == '__main__':
    main()
