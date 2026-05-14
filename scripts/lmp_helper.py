#!/usr/bin/env python
"""
lmp_helper.py — общий модуль для Fe-Pt MD проекта.
Windows-first, no hardcoded /mnt/c/ paths.
Автоопределение корня проекта, поиск lmp.exe, запуск LAMMPS.
"""
import os
import shutil
import subprocess
import sys
import time

# ── Автоопределение корня проекта ──────────────────────────────────
def get_projdir():
    """Корень проекта = родитель scripts/."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(this_dir)  # на уровень выше scripts/

PROJDIR = os.environ.get('FEPT_PROJECT_DIR') or get_projdir()
DATA_DIR = os.path.join(PROJDIR, 'data')
POT_DIR  = os.path.join(PROJDIR, 'potentials')
OUTPUT   = os.path.join(PROJDIR, 'output')
SCRIPTS  = os.path.join(PROJDIR, 'scripts')

# ── Поиск lmp.exe ──────────────────────────────────────────────────
def find_lmp():
    """
    Поиск LAMMPS. Порядок:
      1. PROJDIR/bin/lmp.exe (портативная сборка в папке проекта)
      2. env var LMP_EXE (если задана пользователем вручную)
      3. lmp.exe / lmp в PATH
      4. Типовые пути установки LAMMPS на Windows
      5. lmp.exe в корне проекта (на случай если вручную положили)
    Возвращает команду (список строк) для subprocess, либо None.
    """
    # 0. lmp.exe рядом с проектом в bin/ (портативная сборка)
    bin_lmp = os.path.join(PROJDIR, 'bin', 'lmp.exe')
    if os.path.isfile(bin_lmp):
        return [bin_lmp]

    # 1. Переменная окружения
    env_lmp = os.environ.get('LMP_EXE')
    if env_lmp:
        if os.path.isfile(env_lmp) or shutil.which(env_lmp):
            return [env_lmp]

    # 2. which / shutil
    for name in ('lmp.exe', 'lmp'):
        path = shutil.which(name)
        if path:
            return [path]

    # 3. Типовые пути Windows
    typical_paths = [
        r'C:\Program Files\LAMMPS 64-bit\bin\lmp.exe',
        r'C:\Program Files\LAMMPS 64-bit\lmp.exe',
        r'C:\Program Files\LAMMPS\lmp.exe',
        r'C:\Program Files (x86)\LAMMPS\lmp.exe',
        r'C:\LAMMPS\lmp.exe',
        # Возможна установка вручную рядом с проектом
        os.path.join(PROJDIR, 'lmp.exe'),
    ]
    for p in typical_paths:
        if os.path.isfile(p):
            return [p]

    return None


def find_lmp_display():
    """Человекочитаемое описание найденного LAMMPS."""
    cmd = find_lmp()
    if cmd is None:
        return None
    if os.path.isfile(cmd[0]):
        return cmd[0]
    return 'PATH: ' + cmd[0]


# ── Запуск LAMMPS ──────────────────────────────────────────────────
_RUN_LMP_BAT = os.path.join(PROJDIR, '_run_lmp.bat')

def run_lmp(infile, logfile=None, timeout=900, lmp_label="", **kwargs):
    """
    Запуск LAMMPS через _run_lmp.bat (helper с %~dp0).
    Пути относительные от PROJDIR.

    Returns: dict with keys:
        'ok': bool — True if LAMMPS exited with code 0
        'stdout': str — stdout output
        'stderr': str — stderr output (decoded cp1251 → utf-8)
        'exit_code': int
        'cmd': str — command that was run
        'timeout': bool — True if timed out
    """
    cmd = find_lmp()
    if cmd is None:
        return {
            'ok': False,
            'stdout': '',
            'stderr': 'LAMMPS not found',
            'exit_code': -1,
            'cmd': 'N/A',
            'timeout': False,
        }

    # Use relative paths (no cyrillic in the cmd.exe command string)
    infile_rel = os.path.relpath(infile, PROJDIR)
    bat_args = [_RUN_LMP_BAT, '-in', infile_rel]
    if logfile:
        logfile_rel = os.path.relpath(logfile, PROJDIR)
        bat_args += ['-log', logfile_rel]

    # Windows-only: запуск через cmd.exe /c с _run_lmp.bat
    shell_cmd = subprocess.list2cmdline(bat_args)

    start = time.time()
    timed_out = False
    try:
        proc = subprocess.Popen(
            ['cmd.exe', '/c', shell_cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PROJDIR,
            **kwargs
        )
        try:
            stdout_b, stderr_b = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_b, stderr_b = proc.communicate(timeout=5)
            timed_out = True
    except Exception as e:
        return {
            'ok': False,
            'stdout': '',
            'stderr': 'EXCEPTION: {}'.format(e),
            'exit_code': -1,
            'cmd': shell_cmd,
            'timeout': False,
        }

    elapsed = time.time() - start
    stdout_text = stdout_b.decode('cp1251', errors='replace') if stdout_b else ''
    stderr_text = stderr_b.decode('cp1251', errors='replace') if stderr_b else ''

    return {
        'ok': proc.returncode == 0 and not timed_out,
        'stdout': stdout_text,
        'stderr': stderr_text,
        'exit_code': proc.returncode,
        'cmd': shell_cmd,
        'timeout': timed_out,
        'elapsed': elapsed,
        'label': lmp_label,
    }


def parse_result_line(line):
    """Парсит RESULT-строку из LAMMPS. Гибкий формат — ищет по обязательным полям."""
    import re
    # Check only for the essential fields we actually print
    m_T = re.search(r'T=(\d+)', line)
    m_A = re.search(r'A=([\d.]+)', line)
    if not (m_T and m_A):
        return None
    fields = {
        'T': int(m_T.group(1)),
        'a': float(m_A.group(1)),
    }
    # Optional fields — may or may not be present
    m_comp = re.search(r'COMP=([\d.]+)', line)
    if m_comp:
        fields['comp'] = float(m_comp.group(1))
    m_vol = re.search(r'VOL=([\d.]+)', line)
    if m_vol:
        fields['vol'] = float(m_vol.group(1))
    m_lx = re.search(r'LX=([\d.]+)', line)
    if m_lx:
        fields['lx'] = float(m_lx.group(1))
    m_ly = re.search(r'LY=([\d.]+)', line)
    if m_ly:
        fields['ly'] = float(m_ly.group(1))
    m_lz = re.search(r'LZ=([\d.]+)', line)
    if m_lz:
        fields['lz'] = float(m_lz.group(1))
    m_natoms = re.search(r'NATOMS=(\d+)', line)
    if m_natoms:
        fields['natoms'] = int(m_natoms.group(1))
    return fields


def extract_result_from_log(logfile):
    """Извлекает RESULT из файла лога LAMMPS."""
    if not os.path.exists(logfile):
        return None
    with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    for line in content.split('\n'):
        if line.startswith('RESULT:'):
            r = parse_result_line(line)
            if r:
                return r
    for line in content.split('\n'):
        if 'RESULT:' in line and 'T=' in line and 'A=' in line:
            r = parse_result_line(line)
            if r:
                return r
    return None


def extract_result_from_stdout(result):
    """Извлекает RESULT из stdout (dict с ключом 'stdout' или объект с атрибутом .stdout)."""
    stdout_text = result.get('stdout') if isinstance(result, dict) else getattr(result, 'stdout', None)
    if not stdout_text:
        return None
    for line in stdout_text.split('\n'):
        if line.startswith('RESULT:'):
            r = parse_result_line(line)
            if r:
                return r
    return None


def gen_structure(comp, nx=4, ny=4, nz=4):
    """Генерирует структуру через gen_structure.py."""
    import sys
    gen_script = os.path.join(SCRIPTS, 'gen_structure.py')
    outfile = os.path.join(DATA_DIR, f"data.fept_c{comp:.2f}.lmp")
    if os.path.exists(outfile):
        return outfile
    subprocess.run(
        [sys.executable, gen_script, str(nx), str(ny), str(nz), str(comp), outfile],
        capture_output=True, timeout=30
    )
    return outfile
