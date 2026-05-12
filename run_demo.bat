@echo off
chcp 65001 >nul

REM === run_demo.bat - Quick Fe-Pt MD test (2 points) ===
REM Windows-only. No WSL.
REM Uses lmp.exe from: bin/, LMP_EXE, PATH, or typical install paths.
REM Auto-detects .venv (created by bootstrap.bat) with system python fallback.

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==================================================
echo Fe-Pt MD Thermal Expansion - DEMO
echo ==================================================
echo.

REM --- Python detection: .venv first, system fallback ---
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

REM --- Create output directory ---
if not exist output\ (mkdir output)

REM --- LAMMPS detection ---
call :find_lammps
if errorlevel 1 (
    echo [ERROR] LAMMPS not found!
    echo.
    echo Options:
    echo   1. Install LAMMPS from packages.lammps.org
    echo   2. Set LMP_EXE to your lmp.exe path
    echo   3. Copy lmp.exe + DLLs into bin\
    pause
    exit /b 1
)
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
%LMP_EXE% -in scripts\in.thermal ^
    -var datafile data\data.fept_demo.lmp ^
    -var T 300 ^
    -var comp 1.0 ^
    -log output\log_demo_300.lmp
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=300K)

REM Pt=1.0, T=600K
echo [2/2] Pt=1.0, T=600K...
%LMP_EXE% -in scripts\in.thermal ^
    -var datafile data\data.fept_demo.lmp ^
    -var T 600 ^
    -var comp 1.0 ^
    -log output\log_demo_600.lmp
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=600K)

REM Generate CSV + plot from LAMMPS logs
echo.
echo [demo_report] Generating CSV and plot from raw logs...
%PYTHON% scripts\demo_report.py
if %errorlevel% equ 0 (echo [OK]) else (echo [WARN] demo_report.py - see output above)

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
exit /b 0

REM ============================================================
REM LAMMPS finder subroutine
REM Searches: bin\, LMP_EXE, PATH, typical install paths
REM ============================================================
:find_lammps

REM 1. Portable lmp.exe in bin/ next to project
if exist "%PROJ_DIR%\bin\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\bin\lmp.exe
    exit /b 0
)

REM 2. Environment variable LMP_EXE
if defined LMP_EXE (
    if exist "%LMP_EXE%" (
        exit /b 0
    )
)

REM 3. lmp.exe in PATH
where lmp.exe >nul 2>&1
if %errorlevel% equ 0 (
    set LMP_EXE=lmp.exe
    exit /b 0
)

REM 4. lmp (without .exe) in PATH
where lmp >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%P in ('where lmp') do (
        set LMP_EXE=%%P
        exit /b 0
    )
)

REM 5. Typical Windows install paths
set LMP_PATHS="C:\Program Files\LAMMPS 64-bit\bin\lmp.exe" "C:\Program Files\LAMMPS 64-bit\lmp.exe" "C:\Program Files\LAMMPS\lmp.exe" "C:\Program Files (x86)\LAMMPS\lmp.exe" "C:\LAMMPS\lmp.exe"
for %%P in (%LMP_PATHS%) do (
    if exist %%P (
        set LMP_EXE=%%~P
        exit /b 0
    )
)

REM 6. lmp.exe in project root
if exist "%PROJ_DIR%\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\lmp.exe
    exit /b 0
)

REM Not found
exit /b 1
