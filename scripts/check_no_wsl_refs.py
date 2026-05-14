#!/usr/bin/env python
"""
check_no_wsl_refs.py — Automated WSL dependency guard for Windows-only release.

Scans active runtime files for forbidden Linux/WSL patterns and fails if any found
outside legacy_DO_NOT_RUN/ directory.

Exit codes:
  0 — all clean, no WSL refs in active runtime
  1 — forbidden patterns found in active runtime files

Usage:
    python scripts/check_no_wsl_refs.py          # scan project
    python scripts/check_no_wsl_refs.py --fix    # scan only (no fix mode yet)
"""
import os
import sys
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Forbidden patterns (must appear as /mnt/c, not just mnt)
FORBIDDEN = [
    r'/mnt/[cdefgh]',      # /mnt/c, /mnt/d, etc. (WSL paths)
    r'/tmp',               # WSL tmp
    r'\bbash\b',           # bash shell (not errorlevel, .bashrc)
    r'\bpython3\b',        # python3 (Linux command)
    r'\bwsl\b',            # wsl references
    r'\bubuntu\b',         # ubuntu distro
    r'\brm\s+-rf\b',      # rm -rf (Linux)
    r'\bexport\b',         # export env (Linux)
    r'~/',                 # home ref
    r'/root',              # WSL root dir
]

# Shebang check
SHEBANG_FORBIDDEN = '#!/usr/bin/env python3'

# Directories to skip completely
SKIP_DIRS = [
    '.git',
    '.venv',
    'legacy_DO_NOT_RUN',
    '__pycache__',
    'bin',         # LAMMPS binary bundle (not text)
    'potentials',  # LAMMPS potential files
    'data',        # LAMMPS data files
    'output',      # simulation output
    'output_v2',
    'output_v3',
    'output_v4',
    'figures',
    'plots',
    'cal_pt',      # moved to legacy_DO_NOT_RUN
]

# Files to skip (self-exclusion for checker itself)
SKIP_FILES = ['check_no_wsl_refs.py']


def should_skip(dirpath):
    """Check if directory path should be skipped entirely."""
    parts = dirpath.replace('\\', '/').split('/')
    for skip in SKIP_DIRS:
        if skip in parts:
            return True
    return False


def is_binary(filepath):
    """Quick binary detection — check first 8KB for null bytes."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
            return b'\0' in chunk
    except Exception:
        return True  # assume binary if unreadable


def scan_active_runtime():
    """Scan all active runtime files for forbidden patterns."""
    findings = []
    files_scanned = 0

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip excluded dirs
        if should_skip(root):
            dirs[:] = []  # don't recurse into skipped dirs
            continue

        for fname in files:
            # Skip self-excluded files
            if fname in SKIP_FILES:
                continue

            # Only scan text files
            if not any(fname.endswith(ext) for ext in [
                '.bat', '.py', '.md', '.txt', '.json', '.yml', '.yaml', '.m'
            ]):
                continue

            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, PROJECT_ROOT)

            if is_binary(fpath):
                continue

            files_scanned += 1

            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
            except Exception:
                continue

            for i, line in enumerate(lines, 1):
                line_stripped = line.rstrip('\n\r')

                # Skip Python comment-only lines
                if fname.endswith('.py') and line_stripped.strip().startswith('#'):
                    continue

                # Check shebang
                if i == 1 and SHEBANG_FORBIDDEN in line:
                    findings.append((relpath, i, 'shebang(python3)', line_stripped[:100]))
                    continue

                # Check for forbidden patterns
                for pat in FORBIDDEN:
                    match = re.search(pat, line_stripped)
                    if not match:
                        continue
                    # False positive filtering
                    matched_text = match.group()
                    lower_line = line_stripped.lower()

                    if matched_text == 'bash' and (
                        'errorlevel' in lower_line or '.bashrc' in lower_line
                        or '.bash' in lower_line or 'bash_prompt' in lower_line
                        or 'bash_aliases' in lower_line or 'bash_profile' in lower_line
                    ):
                        continue
                    if matched_text == 'export' and (
                        'exporterrors' in lower_line or 'noprettyexport' in lower_line
                    ):
                        continue
                    if matched_text == '/tmp' and '\\temp' in lower_line:
                        continue  # Windows \temp
                    if matched_text == 'python3' and fname.endswith('.bat'):
                        continue  # .bat file mentioning python3 is validation text, not usage
                    if re.match(r'/mnt/[cdefgh]', matched_text):
                        # Comment documenting the scanner itself — skip
                        if 'forbidden patterns' in lower_line or 'WSL paths' in lower_line:
                            continue
                        if 'no hardcoded /mnt/c/' in lower_line:
                            continue
                        if 'никаких хардкоженых /mnt/c/' in lower_line:
                            continue

                    findings.append((relpath, i, matched_text, line_stripped[:100]))

    return findings, files_scanned


def main():
    print("=" * 60)
    print("Fe-Pt MD — WSL Dependency Check")
    print("=" * 60)
    print()

    print("Project root:", PROJECT_ROOT)
    print()

    findings, files_scanned = scan_active_runtime()
    print(f"Files scanned: {files_scanned}")
    print(f"Findings: {len(findings)}")
    print()

    if not findings:
        print("✅ ALL CLEAN — No WSL/Linux dependencies in active runtime!")
        return 0

    print("❌ Forbidden patterns found in active runtime files:")
    print()

    for relpath, lineno, pattern, context in findings:
        print(f"  {relpath}:{lineno} [{pattern}]")
        print(f"    {context}")
        print()

    print()
    print("Files in legacy_DO_NOT_RUN/ are exempt from this check.")
    print("To fix: update the files listed above to use Windows-native equivalents.")
    print()
    print("❌ FAIL")
    return 1


if __name__ == '__main__':
    sys.exit(main())
