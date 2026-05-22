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

echo.
echo   ERROR: Python 3.11 or 3.12 not found.
echo   Install it from: https://www.python.org/downloads/
echo.
pause
exit /b 1

:python_ok
echo.

REM ===================================================================
REM Step 2: Virtual environment
REM ===================================================================
echo [2/5] Creating virtual environment...

if exist "%PROJ_DIR%\.venv" (
    echo   .venv already exists
) else (
    %PYTHON% -m venv "%PROJ_DIR%\.venv"
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to create .venv
        pause
        exit /b 1
    )
    echo   .venv created
)

echo.

REM ===================================================================
REM Step 3: Install dependencies
REM ===================================================================
echo [3/5] Installing dependencies (numpy, matplotlib)...

"%PROJ_DIR%\.venv\Scripts\python" -m pip install --upgrade pip >nul 2>&1
"%PROJ_DIR%\.venv\Scripts\python" -m pip install numpy matplotlib >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: pip install failed — retrying with longer timeout...
    "%PROJ_DIR%\.venv\Scripts\python" -m pip install --default-timeout=120 numpy matplotlib
    if %errorlevel% neq 0 (
        echo   ERROR: Still failed. Check internet connection.
        pause
        exit /b 1
    )
)
echo   Done.

echo.

REM ===================================================================
REM Step 4: Check LAMMPS
REM ===================================================================
echo [4/5] Checking LAMMPS...

if not exist "%PROJ_DIR%\bin\lmp.exe" (
    echo   ERROR: lmp.exe not found in bin\lmp.exe
    pause
    exit /b 1
)
REM Quick test — just check the binary exists and is runnable
"%LMP_EXE%" -help >nul 2>&1
if %errorlevel% equ 0 (
    echo   lmp.exe found and working
) else (
    echo   WARNING: lmp.exe found but -help failed.
    echo   It may still work with scripts.
)

echo.

REM ===================================================================
REM Step 5: Run DEMO
REM ===================================================================
echo [5/5] Running DEMO (2 points, ~1 minute)...

cd /d "%PROJ_DIR%"

"%PROJ_DIR%\.venv\Scripts\python" scripts/run_mode.py --mode demo
if %errorlevel% neq 0 (
    echo.
    echo   DEMO failed with error code %errorlevel%
    echo   Check the output above.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo  SETUP COMPLETE
echo ==================================================
echo.
echo  Next steps:
echo    run.bat    -- interactive menu (modes 0-8)
echo    run.bat [2]  -- TURBO 256at (main result)
echo.
echo  Results go to: output_v4_256\
echo.
pause
