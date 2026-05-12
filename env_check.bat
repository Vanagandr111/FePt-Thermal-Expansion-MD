@echo off
chcp 65001 >nul

REM === env_check.bat — сбор информации об окружении ===

echo ==============================================
echo Environment Check — FePt Project
echo ==============================================
echo.

echo [1] Windows Version:
ver
echo.

echo [2] Python:
python --version 2>&1
python -c "import sys; print(f'  Python path: {sys.executable}')" 2>&1
echo.

echo [3] LAMMPS:
where lmp 2>&1
lmp -h 2>&1 | findstr "Large-scale"
echo.

echo [4] MATLAB:
where matlab 2>&1
echo (MATLAB not required for this project — LAMMPS does the MD)
echo.

echo [5] Structure check:
echo   Project folder: C:\проекты\Nikolay
if exist C:\проекты\Nikolay\scripts\ (echo   scripts/   [FOUND]) else (echo   scripts/   [MISSING])
if exist C:\проекты\Nikolay\data\ (echo   data/      [FOUND]) else (echo   data/      [MISSING])
if exist C:\проекты\Nikolay\potentials\ (echo   potentials/ [FOUND]) else (echo   potentials/ [MISSING])
if exist C:\проекты\Nikolay\output\ (echo   output/    [FOUND]) else (echo   output/    [MISSING])
if exist C:\проекты\Nikolay\run_demo.bat (echo   run_demo.bat [FOUND]) else (echo   run_demo.bat [MISSING])
if exist C:\проекты\Nikolay\run_main.bat (echo   run_main.bat [FOUND]) else (echo   run_main.bat [MISSING])
if exist C:\проекты\Nikolay\INSTALL_AND_RUN.txt (echo   INSTALL_AND_RUN.txt [FOUND]) else (echo   INSTALL_AND_RUN.txt [MISSING])
if exist C:\проекты\Nikolay\REPORT.txt (echo   REPORT.txt [FOUND]) else (echo   REPORT.txt [MISSING])

echo.
echo ==============================================
echo Check complete.
echo ==============================================
