@echo off
chcp 65001 >nul

REM === run_demo.bat — Быстрый тест Fe-Pt MD (1-2 точки) ===
REM Windows-first: uses C:\Windows\System32\wsl.exe lmp for LAMMPS, relative paths
REM Авто-детект .venv (создаётся bootstrap.bat) с fallback на system python

setlocal
cd /d C:\проекты\Nikolay
set PROJ_DIR=%CD%

echo ==================================================
echo Fe-Pt MD Thermal Expansion — DEMO
echo ==================================================
echo.

REM --- Детект Python: .venv prefer, fallback system ---
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    for /f "delims=" %%V in ('".venv\Scripts\python.exe" --version 2^>^&1') do echo [.venv] %%V
) else (
    set PYTHON=python
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found.
        echo   Запустите bootstrap.bat для автоматической установки.
        pause
        exit /b 1
    )
    for /f "delims=" %%V in ('python --version 2^>^&1') do echo [system] %%V
)
echo [OK] Python ready
echo.

REM Проверка wsl.exe
C:\Windows\System32\wsl.exe which lmp >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] LAMMPS not found in WSL. Run: sudo apt install lammps
    pause
    exit /b 1
)
echo [OK] LAMMPS (WSL) found
echo.

echo Running DEMO: Pt=1.0 at 300K and 600K (2 points)
echo.

REM Generate structure
echo [gen_structure] Creating 256-atom fcc Pt supercell...
%PYTHON% scripts/gen_structure.py 4 4 4 1.0 data\data.fept_demo.lmp
if %errorlevel% neq 0 (
    echo [ERROR] Structure generation failed
    pause
    exit /b 1
)
echo [OK] Structure generated
echo.

REM Pt=1.0, T=300K
echo [1/2] Pt=1.0, T=300K...
C:\Windows\System32\wsl.exe bash -c "cd /mnt/c/проекты/Nikolay && lmp -in scripts/in.thermal -var datafile data/data.fept_demo.lmp -var T 300 -var comp 1.0 -log /mnt/c/проекты/Nikolay/output/log_demo_300.lmp"
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=300K)

REM Pt=1.0, T=600K
echo [2/2] Pt=1.0, T=600K...
C:\Windows\System32\wsl.exe bash -c "cd /mnt/c/проекты/Nikolay && lmp -in scripts/in.thermal -var datafile data/data.fept_demo.lmp -var T 600 -var comp 1.0 -log /mnt/c/проекты/Nikolay/output/log_demo_600.lmp"
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=600K)

REM Generate CSV + plot from LAMMPS logs
echo.
echo [demo_report] Generating CSV and plot from raw logs...
%PYTHON% scripts/demo_report.py
if %errorlevel% equ 0 (echo [OK]) else (echo [WARN] demo_report.py — see output above)

echo.
echo ==================================================
echo DEMO COMPLETE!
echo ==================================================
echo.
echo Files created:
echo   output\log_demo_300.lmp    (LAMMPS log, T=300K)
echo   output\log_demo_600.lmp    (LAMMPS log, T=600K)
echo   output\demo_results.csv    (a(T) table)
echo   output\demo_a_vs_T.png     (graph)
echo.
endlocal
pause
