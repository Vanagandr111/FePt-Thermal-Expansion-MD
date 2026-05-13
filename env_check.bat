@echo off
chcp 65001 >nul
REM === env_check.bat - Diagnostics ===
REM Windows-only. No WSL.
REM Используем ТОЛЬКО bunded bin\lmp.exe

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

REM Очищаем внешние LAMMPS-переменные (helloplugin.so fix)
set "LAMMPS_PLUGIN_PATH="
set "LAMMPS_POTENTIALS="

REM Используем только наш портативный LAMMPS
set "LMP_EXE=%PROJ_DIR%\bin\lmp.exe"

echo ==================================================
echo Fe-Pt MD - Environment Check
echo ==================================================
echo.

REM --- Python ---
echo [1/4] Python:
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe --version
    echo        Location: .venv\Scripts\python.exe
) else (
    where python 2>nul && python --version || echo NOT FOUND
    echo   Run bootstrap.bat first
)
echo.

REM --- LAMMPS ---
echo [2/4] LAMMPS:
echo   LAMMPS_PLUGIN_PATH=%LAMMPS_PLUGIN_PATH%
echo   LAMMPS_POTENTIALS=%LAMMPS_POTENTIALS%
echo   LMP_EXE=%LMP_EXE%
if exist "%LMP_EXE%" (
    echo   bin\lmp.exe - OK
    "%LMP_EXE%" -h 2>&1 | findstr "LAMMPS"
) else (
    echo   bin\lmp.exe - MISSING
)
echo.

REM --- Packages ---
echo [3/4] Packages:
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import numpy; print('  numpy', numpy.__version__)"
    .venv\Scripts\python.exe -c "import matplotlib; print('  matplotlib', matplotlib.__version__)"
) else (
    python -c "import numpy; print('  numpy', numpy.__version__)" 2>&1 || echo "  numpy NOT INSTALLED"
    python -c "import matplotlib; print('  matplotlib', matplotlib.__version__)" 2>&1 || echo "  matplotlib NOT INSTALLED"
)
echo.

REM --- Structure ---
echo [4/4] Structure:
echo   Dir: %PROJ_DIR%
for %%D in (data potentials scripts output requirements.txt) do (
    if exist "%PROJ_DIR%\%%D" (echo   %%D - OK) else (echo   %%D - MISSING)
)
if exist "bin\lmp.exe" (echo   bin\lmp.exe - OK) else (echo   bin\lmp.exe - MISSING)
echo.

echo ==================================================
echo All checks done.
echo ==================================================
endlocal
pause
exit /b 0
