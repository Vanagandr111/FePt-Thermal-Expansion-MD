@echo off
chcp 65001 >nul

REM === run_main.bat - Full Fe-Pt MD run (20 points) ===
REM Windows-only. No WSL.

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==================================================
echo Fe-Pt MD Thermal Expansion - MAIN RUN
echo ==================================================
echo.

REM --- Python ---
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    for /f "delims=" %%V in ('".venv\Scripts\python.exe" --version 2^>^&1') do echo [.venv] %%V
) else (
    set PYTHON=python
)
echo [OK] Python ready
echo.

REM --- output dir ---
if not exist output\ (mkdir output)

REM --- LAMMPS ---
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

echo Running all 20 points...
echo.
%PYTHON% scripts\run_all.py
if %errorlevel% neq 0 (
    echo [ERROR] Main run failed
    pause
    exit /b 1
)

echo.
echo ==================================================
echo MAIN RUN COMPLETE!
echo ==================================================
echo.
echo Results:
echo   output\all_results.csv
echo   output\a_vs_T_all.png
echo   output\a_vs_comp.png
echo   output\a_vs_T_pure.png
echo   output\a_vs_T_residuals.png
echo   output\integrity_check.txt
endlocal
pause
exit /b 0

:find_lammps

REM 1) Portable lmp.exe in bin/ next to project
if exist "%PROJ_DIR%\bin\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\bin\lmp.exe
    exit /b 0
)

REM 2) LMP_EXE env var
if defined LMP_EXE (
    if exist "%LMP_EXE%" (
        exit /b 0
    )
)

REM 3) lmp.exe in PATH
where lmp.exe >nul 2>&1
if %errorlevel% equ 0 (
    set LMP_EXE=lmp.exe
    exit /b 0
)

REM 4) Typical install paths (one by one to avoid (x86) parsing)
if exist "%PROJ_DIR%\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\lmp.exe
    exit /b 0
)
if exist "C:\Program Files\LAMMPS 64-bit\bin\lmp.exe" (
    set LMP_EXE=C:\Program Files\LAMMPS 64-bit\bin\lmp.exe
    exit /b 0
)
if exist "C:\Program Files\LAMMPS 64-bit\lmp.exe" (
    set LMP_EXE=C:\Program Files\LAMMPS 64-bit\lmp.exe
    exit /b 0
)
if exist "C:\Program Files\LAMMPS\lmp.exe" (
    set LMP_EXE=C:\Program Files\LAMMPS\lmp.exe
    exit /b 0
)

REM Not found
exit /b 1