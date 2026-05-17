"""seed_manager.py — Seed management for Fe-Pt MD.
Generates, saves, loads seeds. Detects partial results for resume.

Usage:
    from seed_manager import *
    seed = get_or_create_seed(proj_root, output_dir, manual_seed=None)
"""
import os
import re
import random
import time

SEED_FILE = "seed.txt"       # project root: last used seed
SEED_INFO = "seed_info.txt"   # per-output-dir: calculation metadata


def generate_seed():
    """Generate a random seed for LAMMPS velocity create."""
    random.seed(time.time())
    return random.randint(10000, 99999)


def save_seed_to_project(project_root, seed):
    """Save last used seed to project root."""
    path = os.path.join(project_root, SEED_FILE)
    with open(path, 'w') as f:
        f.write(str(seed) + '\n')


def load_last_seed(project_root):
    """Load last used seed from project root."""
    path = os.path.join(project_root, SEED_FILE)
    if os.path.exists(path):
        with open(path) as f:
            try:
                return int(f.read().strip())
            except (ValueError, IOError):
                pass
    return None


def write_seed_info(output_dir, seed, mode, seed_source):
    """Write seed_info.txt to output directory."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, SEED_INFO)
    with open(path, 'w') as f:
        f.write("SEED={}\n".format(seed))
        f.write("MODE={}\n".format(mode))
        f.write("SOURCE={}\n".format(seed_source))
    return path


def read_seed_from_dir(output_dir):
    """Read seed from an output directory's seed_info.txt."""
    path = os.path.join(output_dir, SEED_INFO)
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.startswith("SEED="):
                    try:
                        return int(line.strip().split("=")[1])
                    except (ValueError, IndexError):
                        pass
    # Fallback: scan log files
    logs_dir = os.path.join(output_dir, 'logs')
    return detect_seed_from_logs(logs_dir)


def detect_seed_from_logs(log_dir):
    """Scan LAMMPS log files to detect seed from 'velocity all create'."""
    if not os.path.isdir(log_dir):
        return None
    for fname in sorted(os.listdir(log_dir)):
        if fname.startswith("log_") and fname.endswith(".lmp"):
            fpath = os.path.join(log_dir, fname)
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    m = re.search(r'velocity\s+all\s+create\s+\d+\s+(\d+)', line)
                    if m:
                        return int(m.group(1))
    return None


def check_partial_results_logs(logs_dir, expected=20):
    """Check if logs directory has partial complete results.
    Returns: None (no logs), "PARTIAL" (some but incomplete),
             "COMPLETE" (all 20 done).
    """
    if not os.path.isdir(logs_dir):
        return None
    existing = [f for f in os.listdir(logs_dir)
                if f.startswith("log_") and f.endswith(".lmp")]
    if not existing:
        return None
    if len(existing) >= expected:
        # Verify all have RESULT or DONE
        valid = 0
        for fname in existing:
            fpath = os.path.join(logs_dir, fname)
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if 'RESULT:' in content or 'DONE' in content:
                valid += 1
        if valid >= expected:
            return "COMPLETE"
    return "PARTIAL"


def get_or_create_seed(project_root, output_dir, manual_seed=None):
    """Resolve seed: manual > existing in output dir > last used > random.
    Returns (seed, source_string).
    """
    if manual_seed is not None:
        seed = int(manual_seed)
        source = "manual"
    else:
        # Try reading from output dir (resume)
        seed = read_seed_from_dir(output_dir)
        if seed is not None:
            source = "resume"
        else:
            # Last used
            seed = load_last_seed(project_root)
            if seed is not None:
                source = "last_seed"
            else:
                seed = generate_seed()
                source = "generated"
    # Save everywhere
    save_seed_to_project(project_root, seed)
    write_seed_info(output_dir, seed, "auto", source)
    return seed, source


def format_seed_info_line(seed, source):
    """Return a formatted line for console output."""
    return "Seed: {} ({})".format(seed, source)
