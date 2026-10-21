"""EOS test: zero-pressure lattice constant from MACE-MP-0 (E(V) fit).

Separates "potential is bad" from "the run was wrong": volume scan with
full position relaxation at fixed cell (fp32, no thermostat/barostat),
then a parabola fit E(V) -> V0 -> a(0K).

Run: .venv-mace/Scripts/python.exe scripts/eos_pt.py [--comp 1.00]
     (comp 1.00 = pure Pt -> LC_TABLE['pt']; comp 0.00 = pure Fe, fcc)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from run_main_mace import FastMACECalculator, find_model, read_lammps_data
import lmp_helper as lmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--comp', type=float, default=1.00)
    ap.add_argument('--model', default=None,
                    help='path to an alternate MACE model file '
                         '(default: find_model current FePt potential)')
    ap.add_argument('--device', default='cuda', choices=['cuda', 'cpu'])
    args = ap.parse_args()

    from ase.optimize import BFGS

    model = find_model(args.model)
    print('model:', model)
    # torch.compile on CPU wants MSVC cl.exe (absent in most shells) and
    # buys nothing for an EOS scan; CUDA path keeps the normal compiled run.
    calc = FastMACECalculator(
        model_paths=model, device=args.device,
        compile_mode='default' if args.device == 'cuda' else None,
        use_bf16=False)
    datafile = lmp.gen_structure(args.comp, nx=4, ny=4, nz=4, force=True)
    base = read_lammps_data(datafile)
    print('comp={:.2f}  atoms: {}  a_start={:.4f}'.format(
        args.comp, len(base), base.cell.lengths()[0]))

    scales = np.linspace(0.94, 1.07, 14)
    rows = []
    for s in scales:
        a = base.copy()
        a.calc = calc
        a.set_cell(a.cell.array * s, scale_atoms=True)
        opt = BFGS(a, logfile=None)
        opt.run(fmax=1e-3, steps=200)
        e = a.get_potential_energy()
        v = a.get_volume()
        rows.append((s, v, e))
        print('  s={:.3f} V={:8.2f} E={:.6f} ({:d} steps)'.format(
            s, v, e, opt.nsteps))

    v = np.array([r[1] for r in rows])
    e = np.array([r[2] for r in rows])
    c = np.polyfit(v, e, 2)
    v0 = -c[1] / (2.0 * c[0])
    natoms = len(base)
    # fcc: 4 atoms per conventional cell -> a = (V_atom * 4)^(1/3)
    a0 = (v0 * 4.0 / natoms) ** (1.0 / 3.0)
    print()
    print('EOS_PARABOLA a(0K) comp={:.2f} = {:.4f} A  (V0={:.2f} A^3, {} atoms)'.format(
        args.comp, a0, v0, natoms))
    for s, vv, ee in rows:
        print('   s={:.3f}  V={:8.2f}  E={:.6f}'.format(s, vv, ee))


if __name__ == '__main__':
    main()
