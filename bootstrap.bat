@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ================================================================
echo  Fe-Pt MD - Interactive bootstrap
echo  Checks Python, creates/updates the venv, installs dependencies
echo ================================================================
echo.

REM ------------------------------------------------------------------
REM [0] Find a Python that REALLY runs. The Microsoft Store ships a
REM     fake "python.exe" alias that prints "Python was not found" and
REM     breaks venv, so every candidate gets a real test run and
REM     WindowsApps entries are skipped outright.
REM ------------------------------------------------------------------
set PYEXE=
if exist ".venv-mace\Scripts\python.exe" set "PYEXE=.venv-mace\Scripts\python.exe"

if not defined PYEXE (
    for /f "delims=" %%P in ('where py 2^>nul') do (
        if not defined PYEXE (
            echo %%P | findstr /i /c:"WindowsApps" >nul || (
                "%%P" -3 -c "import sys" >nul 2>nul && set "PYEXE=%%P" -3
            )
        )
    )
)
if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYEXE (
            echo %%P | findstr /i /c:"WindowsApps" >nul || (
                "%%P" -c "import sys" >nul 2>nul && set "PYEXE=%%P"
            )
        )
    )
)
if not defined PYEXE (
    echo   ERROR: Python 3.10+ not found.
    echo   Install it from https://www.python.org/downloads/
    echo   (If it IS installed but the Store alias shadows it, disable:
    echo    Settings ^> Apps ^> Advanced app settings ^> App execution aliases)
    pause
    exit /b 1
)
echo [ok] Python found: %PYEXE%

REM ------------------------------------------------------------------
REM [1] Version gate: the engine needs 3.10 .. 3.14
REM ------------------------------------------------------------------
"%PYEXE%" -c "import sys; ok = (3, 10) <= sys.version_info[:2] <= (3, 14); print('ver', sys.version_info[0], sys.version_info[1]); raise SystemExit(0 if ok else 1)" >nul 2>&1
if errorlevel 1 (
    echo   ERROR: this Python is not 3.10-3.14. Install a suitable one.
    pause
    exit /b 1
)
echo [ok] Version is 3.10-3.14

REM ------------------------------------------------------------------
REM [2] Interactive menu
REM ------------------------------------------------------------------
echo.
echo  Choose what to do:
echo    [1] Full setup: venv + GPU torch (CUDA 12.8, ~2.8 GB) + deps  (default)
echo    [2] Full setup: venv + CPU-only torch + deps
echo    [3] Deps only: venv exists, just install/update requirements
echo    [4] Check environment: no changes, report only
echo.
set CHOICE=
set /p CHOICE=  Enter 1/2/3/4 [1]: 
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="4" goto :check
if "%CHOICE%"=="3" goto :deps
if "%CHOICE%"=="2" goto :cpu

REM ---------------- [1] GPU path ----------------
echo.
echo  [1/4] Creating virtualenv .venv-mace ...
if not exist ".venv-mace\Scripts\python.exe" (
    %PYEXE% -m venv .venv-mace
    if errorlevel 1 ( echo   ERROR: venv creation failed & pause & exit /b 1 )
)
echo  [2/4] Upgrading pip ...
".venv-mace\Scripts\python.exe" -m pip install -q --upgrade pip
echo  [3/4] Installing GPU torch cu128 (~2.8 GB, this takes a while) ...
".venv-mace\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
    echo   WARNING: cu128 failed, falling back to default torch ...
    ".venv-mace\Scripts\python.exe" -m pip install torch
)
goto :deps

REM ---------------- [2] CPU path ----------------
:cpu
echo.
echo  [1/3] Creating virtualenv .venv-mace ...
if not exist ".venv-mace\Scripts\python.exe" (
    %PYEXE% -m venv .venv-mace
    if errorlevel 1 ( echo   ERROR: venv creation failed & pause & exit /b 1 )
)
echo  [2/3] Installing CPU torch ...
".venv-mace\Scripts\python.exe" -m pip install -q --upgrade pip
".venv-mace\Scripts\python.exe" -m pip install torch
goto :deps

REM ---------------- [3] requirements ----------------
:deps
echo  [..] Installing requirements-mace.txt ...
".venv-mace\Scripts\python.exe" -m pip install -r requirements-mace.txt
if errorlevel 1 (
    echo   ERROR: requirements install failed
    pause
    exit /b 1
)
goto :verify

REM ---------------- [4] check only / final verify ----------------
:check
if not exist ".venv-mace\Scripts\python.exe" (
    echo   .venv-mace does not exist yet - run options 1 or 2 first.
    pause
    exit /b 1
)
goto :verify

:verify
echo.
echo ================================================================
echo  Environment check
echo ================================================================
".venv-mace\Scripts\python.exe" -c "import sys; print('python  :', sys.version.split()[0])"
".venv-mace\Scripts\python.exe" -c "import torch; print('torch   :', torch.__version__, '| cuda available:', torch.cuda.is_available(), ('| ' + torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''))" 2>nul || echo   torch   : NOT INSTALLED
".venv-mace\Scripts\python.exe" -c "import mace; print('mace    : ok')" 2>nul || echo   mace    : NOT INSTALLED
".venv-mace\Scripts\python.exe" -c "import ase; print('ase     :', ase.__version__)" 2>nul || echo   ase     : NOT INSTALLED
echo ================================================================
echo  Next steps: run_gui.bat  (GUI at http://127.0.0.1:8321)
echo              run_mace.bat (engine from the command line)
echo ================================================================
pause
exit /b 0
