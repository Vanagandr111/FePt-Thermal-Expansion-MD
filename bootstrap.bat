@echo off
chcp 65001 >nul
REM === bootstrap.bat - One-click setup + run ===
REM Windows-only. No WSL.

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

REM Очищаем внешние LAMMPS-переменные (helloplugin.so fix)
set "LAMMPS_PLUGIN_PATH="
set "LAMMPS_POTENTIALS="

REM Используем только наш портативный LAMMPS
set "LMP_EXE=%PROJ_DIR%\bin\lmp.exe"

echo ==================================================
echo Fe-Pt MD Thermal Expansion - SETUP
echo ==================================================
echo.

REM ===================================================================
REM Step 1: Python
REM ===================================================================
echo [1/5] Checking Python...

py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=py -3.12
    for /f "delims=" %%V in ('py -3.12 --version 2^>^&1') do echo   Found: %%V
    goto :python_ok
)

py -3.11 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=py -3.11
    for /f "delims=" %%V in ('py -3.11 --version 2^>^&1') do echo   Found: %%V
    goto :python_ok
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    python -c "import sys; ver=sys.version_info; exit(0 if (3,11) <= (ver.major,ver.minor) <= (3,12) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON=python
        for /f "delims=" %%V in ('python --version 2^>^&1') do echo   Found: %%V
        goto :python_ok
    )
)

echo [ERROR] Python 3.11 or 3.12 (x64) required.
echo   https://www.python.org/downloads/release/python-3129/
pause
exit /b 1

:python_ok
echo [OK] Python ready
echo.

REM ===================================================================
REM Step 2: Virtual environment
REM ===================================================================
echo [2/5] Virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo   .venv exists, skipping
) else (
    echo   Creating .venv...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (echo [ERROR] Failed to create .venv & pause & exit /b 1)
    echo   .venv created
)
echo [OK]
echo.

REM ===================================================================
REM Step 3: Dependencies
REM ===================================================================
echo [3/5] Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (echo [ERROR] pip install failed & pause & exit /b 1)
echo [OK]
echo.

REM ===================================================================
REM Step 4: LAMMPS
REM ===================================================================
echo [4/5] Checking LAMMPS...
call :find_lammps
if %errorlevel% neq 0 (
    echo [WARN] LAMMPS not found.
    echo Options:
    echo   1. Install LAMMPS from packages.lammps.org
    echo   2. Set LMP_EXE
    echo   3. Copy lmp.exe + DLLs into bin\
) else (
    echo [OK] LAMMPS: %LMP_EXE%
    where lmp.exe >nul 2>&1 && echo [OK] LMP in PATH also: lmp.exe || echo [OK] LMP only in bin\
)
echo   LAMMPS_PLUGIN_PATH=%LAMMPS_PLUGIN_PATH%
echo   LAMMPS_POTENTIALS=%LAMMPS_POTENTIALS%
echo.

REM ===================================================================
REM Step 5: Run demo
REM ===================================================================
echo [5/5] Starting DEMO...
echo.
call run_demo.bat

echo.
echo ==================================================
echo SETUP COMPLETE!
echo ==================================================
echo.
echo Next: run_main.bat for full 20-point run
echo.
endlocal
pause

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
