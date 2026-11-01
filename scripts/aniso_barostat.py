# -*- coding: utf-8 -*-
"""Anisotropic Berendsen barostat (per-axis cell relaxation).

Kept in its own module on purpose: run_main_mace imports torch at module
level, and a unit test of this geometry must not drag the CUDA stack in.

ASE >= 3.29 has no 9-DoF MTKBarostat (it exists only in 3.23-3.28), and
IsotropicMTKNPT scales all three lattice vectors by one factor - so c/a of
L1_0 stays frozen and alpha cannot be split per axis. This class scales each
cell vector separately with the diagonal stress of the step:

    eps_i += dt/tau * (P_i - P_ext) / B,   s_i = 1 + eps_i

P_i comes from the stress tensor (ASE sign: positive stress = compression,
so pressure P = -stress). Berendsen coupling gives correct MEANS (a_x, a_y,
a_z and c/a versus T) while damping volume fluctuations, which is what a
thermal-expansion run needs; the reported sigma still comes from the window.
"""
import numpy as np

from ase import units


class AnisoBerendsen:
    """Per-axis barostat: relaxes the cell SHAPE, not only its volume."""

    def __init__(self, atoms, timestep, pressure_au=0.0, taut_ps=2.0,
                 bulk_modulus_gpa=150.0, max_step=0.02):
        self.atoms = atoms
        self.dt_fs = float(timestep / units.fs)
        self.p_ext_gpa = float(pressure_au) / units.GPa
        self.taut_fs = max(50.0, float(taut_ps) * 1000.0)
        self.bulk_gpa = max(1.0, float(bulk_modulus_gpa))
        self.max_step = abs(float(max_step))
        self.steps = 0

    def __call__(self, atoms=None):
        atoms = atoms if atoms is not None else self.atoms
        stress = atoms.get_stress(voigt=True)          # eV/A^3
        p_gpa = -np.array(stress[:3], dtype=float) * 160.2176634
        d_eps = ((self.dt_fs / self.taut_fs) * (p_gpa - self.p_ext_gpa)
                 / self.bulk_gpa)
        d_eps = np.clip(d_eps, -self.max_step, self.max_step)
        scale = 1.0 + d_eps
        cell = atoms.get_cell()
        new_cell = cell.copy()
        for i in range(3):
            new_cell[i] = cell[i] * scale[i]
        frac = atoms.get_scaled_positions(wrap=True)
        atoms.set_cell(new_cell, scale_atoms=False)
        atoms.set_scaled_positions(frac)      # affine: fractions are kept
        self.steps += 1
