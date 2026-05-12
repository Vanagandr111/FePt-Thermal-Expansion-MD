@echo off
chcp 65001 >nul
REM === env_check.bat - Diagnostics ===
REM Windows-only. No WSL.

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

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
call :find_lammps
if not errorlevel 1 (
    echo   LMP_EXE=%LMP_EXE%
    "%LMP_EXE%" -h 2>&1 | findstr "LAMMPS"
) else (
    echo   NOT FOUND
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