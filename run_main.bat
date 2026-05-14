@echo off
chcp 65001 >nul

REM === run_main.bat - Fe-Pt MD Phase 4 (Long Protocol) ===
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
echo Fe-Pt MD Thermal Expansion - MAIN RUN (Phase 4)
echo ==================================================
echo.
echo  Phase 4 Protocol: 50k equilibration + 100k production
echo  Potential: MEAM PtFe.meam
echo  Grid: 5 compositions x 4 temperatures = 20 points
echo  Output: output_v4\
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

REM --- LAMMPS ---
echo [OK] LAMMPS: %LMP_EXE%
echo.

REM === Phase 4 Long Protocol Run ===
echo Running Phase 4 long protocol...
echo.
%PYTHON% scripts\run_phase4.py
if %errorlevel% neq 0 (
    echo [ERROR] Phase 4 run failed
    pause
    exit /b 1
)

echo.
echo ==================================================
echo MAIN RUN COMPLETE - Phase 4!
echo ==================================================
echo.
echo Results:
echo   output_v4\all_results.csv
echo   output_v4\integrity_check_v4.txt
echo   output_v4\run_main_protocol.txt
echo   output_v4\a_vs_T_all_v4.png
echo   output_v4\a_vs_comp_v4.png
echo   output_v4\a_vs_T_facets_v4.png

REM --- Old output dirs are NOT used by Phase 4 ---
if exist output\ (
    echo.
    echo [NOTICE] Legacy output\ dir exists (Phase 2/3 results).
    echo          Phase 4 writes ONLY to output_v4\
)
if exist output_v3\ (
    echo [NOTICE] Legacy output_v3\ dir exists.
    echo          Phase 4 writes ONLY to output_v4\
)

endlocal
pause
exit /b 0
