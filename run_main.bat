@echo off
chcp 65001 >nul

REM === run_main.bat - Full Fe-Pt MD run (20 points) ===
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
echo   output\integrity_check.txt
echo   output\a_vs_T.png
echo   output\a_vs_comp.png
endlocal
pause
exit /b 0
