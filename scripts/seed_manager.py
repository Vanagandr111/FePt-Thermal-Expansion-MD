"""seed_manager.py — Seed management for Fe-Pt MD.
Generates, saves, loads seeds. Detects partial results for resume.

Usage:
    from seed_manager import *
    seed = get_or_create_seed(proj_root, output_dir, manual_seed=None)

# module-purpose: seed lifecycle — generation, persistence, resume detection
# entry-points: get_or_create_seed, write_seed_info
# main-flows:
#   1. manual seed -> resolve -> persist
#   2. resume -> read_seed_from_dir -> detect_seed_from_logs -> merge
#   3. reuse-last -> load_last_seed -> fallback to generate
#   4. auto -> generate_seed -> persist
# related-modules: lmp_helper (calls seed_manager for --seed arg parsing)
"""
import os
import re
import secrets

# -- Constants --
# intent: Path constants for seed persistence files
# sidefx: none
# purity: pure
SEED_FILE = "seed.txt"        # project root: last used seed
SEED_INFO = "seed_info.txt"   # per-output-dir: calculation metadata


# -- Seed Generation --
def generate_seed():
    """
    # intent: Generate a random seed for LAMMPS velocity create (10000-99999)
    # allies: get_or_create_seed (fallback when no manual/reuse/resume)
    # sidefx: none
    # purity: pure
    # errors: none
    """
    return secrets.randbelow(90000) + 10000


# -- Persistence - root --
def save_seed_to_project(project_root, seed):
    """
    # intent: Save last used seed to SEED_FILE in project root
    # allies: get_or_create_seed (calls on every resolution)
    # sidefx: io (writes SEED_FILE)
    # purity: impure
    # errors: IOError (unhandled, propagates up)
    """
    path = os.path.join(project_root, SEED_FILE)
    with open(path, 'w') as f:
        f.write(str(seed) + '\n')


def load_last_seed(project_root):
    """
    # intent: Load last used seed from SEED_FILE
    # allies: get_or_create_seed, read_seed_from_dir (resume fallback)
    # sidefx: io (reads SEED_FILE)
    # purity: impure
    # errors: returns None on missing file / parse error (silent)
    """
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
    """
    # intent: Write seed_info.txt to output directory for reproducibility
    # allies: get_or_create_seed, main scripts
    # sidefx: io (writes SEED_INFO)
    # purity: impure
    # errors: IOError (unhandled, propagates up)
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, SEED_INFO)
    with open(path, 'w') as f:
        f.write("SEED={}\n".format(seed))
        f.write("MODE={}\n".format(mode))
        f.write("SOURCE={}\n".format(seed_source))
    return path


def read_seed_from_dir(output_dir):
    """
    # intent: Read seed from output dir's seed_info.txt, fallback to logs
    # allies: get_or_create_seed (resume path), detect_seed_from_logs
    # sidefx: io (reads SEED_INFO / logs)
    # purity: impure
    # errors: returns None if no seed found (silent)
    """
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
    """
    # intent: Scan LAMMPS log files to extract seed from 'velocity all create'
    # allies: read_seed_from_dir (fallback path)
    # sidefx: io (reads .lmp log files)
    # purity: impure
    # errors: returns None if no log files or no seed pattern found (silent)
    """
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


# -- Resume / Partial Results Detection --
def check_partial_results_logs(logs_dir, expected=20):
    """
    # intent: Check if logs dir has partial/complete results for resume decision
    # allies: main scripts (run_* decide resume vs force), lmp_helper
    # sidefx: io (reads .lmp log files)
    # purity: impure
    # errors: returns None / "PARTIAL" / "COMPLETE" (no exception)
    """
    if not os.path.isdir(logs_dir):
        return None
    existing = [f for f in os.listdir(logs_dir)
                if f.startswith("log_") and f.endswith(".lmp")]
    if not existing:
        return None
    if len(existing) >= expected:
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


# -- Main Seed Resolution --
def get_or_create_seed(project_root, output_dir, manual_seed=None,
                       reuse_last=False, resume=False):
    """
    Resolve seed.

    Priority: manual seed > resume seed from output logs/info > last seed
    (if explicitly requested) > new random seed.

    Returns (seed, source_string).

    # intent: Central seed resolution - resolves from CLI args, resume, or auto
    # allies: generate_seed, save_seed_to_project, write_seed_info,
    #         load_last_seed, read_seed_from_dir
    # sidefx: io (writes SEED_FILE + SEED_INFO)
    # purity: impure
    # errors: int() conversion on manual_seed may raise ValueError
    """
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


# -- Console Formatting --
def format_seed_info_line(seed, source):
    """
    # intent: Format seed info for console output
    # allies: main scripts (run_* display)
    # sidefx: none
    # purity: pure
    # errors: none
    """
    return "Seed: {} ({})".format(seed, source)
