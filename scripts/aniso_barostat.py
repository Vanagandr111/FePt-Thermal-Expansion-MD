# -*- coding: utf-8 -*-
"""Anisotropic Berendsen barostat (per-axis cell relaxation).

Kept in its own module on purpose: run_main_mace imports torch at module
level, and a unit test of this geometry must not drag the CUDA stack in.

ASE >= 3.29 has no 9-DoF MTKBarostat (it exists only in 3.23-3.28), and
IsotropicMTKNPT scales all three lattice vectors by one factor - so c/a of
L1_0 stays frozen and alpha cannot be split per axis. This class scales each
cell vector separately with the diagonal stress of the step:

    eps_i += dt/tau * (P_i - P_ext) / B,   s_i = 1 + eps_i

P_i comes from the ASE stress tensor, which is tensile-positive
(probe: a=3.50 -> sigma=-0.103, a=3.90 -> sigma=+0.116 for Cu), so the
pressure is P = -trace(sigma)/3. GPa = 160.2176634 * eV/A^3. Berendsen coupling gives correct MEANS (a_x, a_y,
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
        stress = atoms.get_stress(voigt=True, include_ideal_gas=True)
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
        vel = atoms.get_velocities()
        atoms.set_cell(new_cell, scale_atoms=False)
        atoms.set_scaled_positions(frac)      # affine: fractions are kept
        if vel is not None:
            # scale is a per-axis (3,) vector: velocities are (N, 3), so the
            # axis must broadcast along the LAST index. scale[:, None] is
            # (3, 1) and blows up on any cell with N != 3 atoms
            # ("(480,3) (3,1)" on a 480-atom orthorhombic run).
            atoms.set_velocities(vel / scale[None, :])
        self.steps += 1

class IsoBerendsen:
    """Uniform (isotropic) cell relaxation to the target pressure.

    scale = 1 + dt/tau * (P - P_ext) / B, applied to all three cell vectors
    and to the fractional-coordinate-preserving atomic positions.
    """

    def __init__(self, atoms, timestep, pressure_au=0.0, taut_ps=1.0,
                 bulk_modulus_gpa=150.0, max_step=0.002, smooth_steps=100):
        self.atoms = atoms
        self.dt_fs = float(timestep / units.fs)
        self.p_ext_gpa = float(pressure_au) / units.GPa
        self.taut_fs = max(50.0, float(taut_ps) * 1000.0)
        self.bulk_gpa = max(1.0, float(bulk_modulus_gpa))
        self.max_step = abs(float(max_step))
        # Instantaneous pressure in a 100-atom cell fluctuates by tens of
        # kbar; feeding that into the cell step makes the volume random-walk
        # instead of settling. Exponential moving average ~ smooth_steps.
        self.smooth = max(1, int(smooth_steps))
        self.p_ema = None
        self.steps = 0

    def __call__(self, atoms=None):
        atoms = atoms if atoms is not None else self.atoms
        stress = atoms.get_stress(voigt=True, include_ideal_gas=True)
        p_gpa = -float(np.mean(stress[:3])) * 160.2176634
        if self.p_ema is None:
            self.p_ema = p_gpa
        else:
            self.p_ema += (p_gpa - self.p_ema) / self.smooth
        d_eps = ((self.dt_fs / self.taut_fs) * (self.p_ema - self.p_ext_gpa)
                 / self.bulk_gpa)
        d_eps = float(np.clip(d_eps, -self.max_step, self.max_step))
        scale = 1.0 + d_eps
        cell = atoms.get_cell()
        frac = atoms.get_scaled_positions(wrap=True)
        vel = atoms.get_velocities()
        atoms.set_cell(cell * scale, scale_atoms=False)
        atoms.set_scaled_positions(frac)
        # Berendsen 1984: velocities must be rescaled by 1/mu as well,
        # otherwise every cell step pumps/removes kinetic energy and the
        # thermostat fights the barostat -> a permanent pressure offset.
        if vel is not None:
            atoms.set_velocities(vel / scale)
        self.steps += 1
