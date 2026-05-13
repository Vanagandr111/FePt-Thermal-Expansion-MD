@echo off
chcp 65001 >nul

REM === run_demo.bat - Quick Fe-Pt MD test (2 points) ===
REM Windows-only. No WSL.
REM Используем ТОЛЬКО bunded bin\lmp.exe — никакого PATH / системных LAMMPS

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

REM Очищаем внешние LAMMPS-переменные (helloplugin.so fix)
set "LAMMPS_PLUGIN_PATH="
set "LAMMPS_POTENTIALS="

REM Используем только наш портативный LAMMPS
set "LMP_EXE=%PROJ_DIR%\bin\lmp.exe"
if not exist "%LMP_EXE%" (
    echo [ERROR] bundled lmp.exe not found at bin\lmp.exe
    pause
    exit /b 1
)

echo ==================================================
echo Fe-Pt MD Thermal Expansion - DEMO
echo ==================================================
echo.

REM --- Python ---
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    for /f "delims=" %%V in ('".venv\Scripts\python.exe" --version 2^>^&1') do echo [.venv] %%V
) else (
    set PYTHON=python
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found.
        echo   Run bootstrap.bat first to set up environment.
        pause
        exit /b 1
    )
    for /f "delims=" %%V in ('python --version 2^>^&1') do echo [system] %%V
)
echo [OK] Python ready
echo.

REM --- output dir ---
if not exist output\ (mkdir output)

REM --- LAMMPS ---
echo [OK] LAMMPS: %LMP_EXE%
echo.

echo Running DEMO: Pt=1.0 at 300K and 600K (2 points)
echo.

REM Generate structure
echo [gen_structure] Creating 256-atom fcc Pt supercell...
%PYTHON% scripts\gen_structure.py 4 4 4 1.0 data\data.fept_demo.lmp
if %errorlevel% neq 0 (
    echo [ERROR] Structure generation failed
    pause
    exit /b 1
)
echo [OK] Structure generated
echo.

REM Pt=1.0, T=300K
echo [1/2] Pt=1.0, T=300K...
%LMP_EXE% -in scripts\in.thermal -var datafile data\data.fept_demo.lmp -var T 300 -var comp 1.0 -log output\log_demo_300.lmp
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=300K)

REM Pt=1.0, T=600K
echo [2/2] Pt=1.0, T=600K...
%LMP_EXE% -in scripts\in.thermal -var datafile data\data.fept_demo.lmp -var T 600 -var comp 1.0 -log output\log_demo_600.lmp
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=600K)

REM Report
echo.
echo [demo_report] Generating CSV and plot from raw logs...
%PYTHON% scripts\demo_report.py
if %errorlevel% equ 0 (echo [OK]) else (echo [WARN] demo_report.py)

echo.
echo ==================================================
echo DEMO COMPLETE!
echo ==================================================
echo.

echo Files:
echo   output\log_demo_300.lmp
echo   output\log_demo_600.lmp
echo   output\demo_results.csv
echo   output\demo_a_vs_T.png
echo.

endlocal
pause
exit /b 0
