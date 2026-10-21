# Changelog — FePt Thermal Expansion (MACE pipeline)

## v1.7.4 (2026-10-21)
- **Seed lattice constant: no more hidden hardcode.** `LC_TABLE` in
  `scripts/gen_structure.py` with printed provenance per run:
  pt = 4.0065 A (our MACE-MP-0 EOS fit, E(V) parabola),
  fe = 3.5647 A (our EOS fit, fcc),
  fept = 3.615 A (historical v1.5 seed, kept only for old-run
  comparability). Override per run: `--lc <A>`.
- **Lever D merged: Verlet-skin neighbour-list cache** (`--nl-skin`,
  default 1.0 A). Same pairs, same order as the matscipy builder
  (array_equal), verified by `scripts/test_nl_cache.py`; gate:
  56.0 -> 52.5 ms/step (256 atoms, RTX 3070 Ti), a(300K) shift +0.004%.
- **torch-2.6 weights_only fix**: `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`
  is now set inside `run_main_mace.py` — imports work in any shell
  (was UnpicklingError/hang wherever the variable was not preset).
- **Spawned workers get per-PID triton/inductor sub-caches** (Windows
  PermissionError on shared .cubin when 2 workers compile at once).
- `scripts/eos_pt.py`: `--model`, `--device`; no torch.compile on CPU
  (inductor wants MSVC cl.exe and buys nothing for an EOS scan).
- Gate A (max-autotune-no-cudagraphs): FAIL — 52.5 -> 52.0 ms/step is
  within noise and the bf16 reduction order shifts a(300K) by 0.022%
  (> 0.01% budget); reverted, default stays `compile=default`.
- **Potential survey (EOS Pt vs exp 3.92 A, CTE 300-1200K vs exp
  9.5e-6 /K)**: MACE-MP-0 stays best: CTE 98.3% of exp. MACE-MPA-0
  203%, MP-0b3 136%, MP-0b2 119% (all slightly worse on Pt position
  too). No replacement found in the foundation-model round; models
  kept in `potentials/` for reference (not shipped in the release).
- Speed story vs v1.7.1 baseline 94.2 ms/step: -> 55 (compile+bf16)
  -> 52.5 (skin cache) = x1.79.

## v1.7.3 (2026-10-19)
- LC_TABLE-based generator defaults + `--lc` documentation, release
  assets with weights.

## v1.7.2 (2026-10-18)
- Gate harness (before/after windows), phase micro-benchmark,
  torch.compile + bf16 speed mode, parallel workers.
