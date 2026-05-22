"""seed_manager.py — Seed management for Fe-Pt MD.
Generates, saves, loads seeds. Detects partial results for resume.

Usage:
    from seed_manager import *
    seed = get_or_create_seed(proj_root, output_dir, manual_seed=None)
"""
import os
import re
import secrets

# -- Constants --
SEED_FILE = "seed.txt"        # project root: last used seed
SEED_INFO = "seed_info.txt"   # per-output-dir: calculation metadata


# -- Seed Generation --
def generate_seed():
    """Generate a random seed for LAMMPS."""
    return secrets.randbelow(90000) + 10000


# -- Persistence - root --
def save_seed_to_project(project_root, seed):
    """Save last used seed to project root SEED_FILE."""
    path = os.path.join(project_root, SEED_FILE)
    with open(path, 'w') as f:
        f.write(str(seed) + '\n')


def load_last_seed(project_root):
    """Load last used seed from project root SEED_FILE."""
    path = os.path.join(project_root, SEED_FILE)
    if os.path.exists(path):
        with open(path) as f:
            try:
                return int(f.read().strip())
            except (ValueError, IOError):
                pass
    return None


# -- Persistence - per-output-dir --
def write_seed_info(output_dir, seed, mode, seed_source):
    """Write seed_info.txt to output directory for reproducibility."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, SEED_INFO)
    with open(path, 'w') as f:
        f.write("SEED={}\n".format(seed))
        f.write("MODE={}\n".format(mode))
        f.write("SOURCE={}\n".format(seed_source))
    return path


def read_seed_from_dir(output_dir):
    """Read seed from output dir seed_info.txt, fallback to logs."""
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
    """Scan LAMMPS log files to extract seed from velocity create command."""
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


# -- Main Seed Resolution --
def get_or_create_seed(project_root, output_dir, manual_seed=None,
                       reuse_last=False, resume=False):
    """Resolve seed. Priority: manual > resume > last_seed > auto."""
    if manual_seed is not None:
        seed = int(manual_seed)
        source = "manual"
    elif resume:
        seed = read_seed_from_dir(output_dir)
        if seed is not None:
            source = "resume"
        else:
            seed = load_last_seed(project_root)
            if seed is not None:
                source = "last_seed_resume_fallback"
            else:
                seed = generate_seed()
                source = "generated_resume_fallback"
    elif reuse_last:
        seed = load_last_seed(project_root)
        if seed is not None:
            source = "last_seed"
        else:
            seed = generate_seed()
            source = "generated_no_last_seed"
    else:
        seed = generate_seed()
        source = "generated"
    # Save everywhere
    save_seed_to_project(project_root, seed)
    write_seed_info(output_dir, seed, "auto", source)
    return seed, source
