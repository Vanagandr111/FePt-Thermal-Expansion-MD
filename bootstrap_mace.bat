@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PROJ=%CD%

echo ============================================
echo  Fe-Pt MD - MACE environment bootstrap
echo  (one-time setup: .venv-mace + torch cu128)
echo ============================================
echo.

set PYEXE=
if exist ".venv-mace\Scripts\python.exe" set "PYEXE=.venv-mace\Scripts\python.exe"

REM --- Pick a python that REALLY runs. The Microsoft Store ships a fake
REM --- "python.exe" app execution alias that prints "Python was not found"
REM --- and fails venv creation, so every candidate gets a test run and
REM --- WindowsApps entries are skipped outright.
if not defined PYEXE (
    for /f "delims=" %%P in ('where py 2^>nul') do (
        if not defined PYEXE (
            echo %%P | findstr /i /c:"WindowsApps" >nul || (
                "%%P" -3 -c "import sys" >nul 2>nul && set PYEXE="%%P" -3
            )
        )
    )
)
if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYEXE (
            echo %%P | findstr /i /c:"WindowsApps" >nul || (
                "%%P" -c "import sys" >nul 2>nul && set PYEXE="%%P"
            )
        )
    )
)
if not defined PYEXE (
    python -c "import sys" >nul 2>nul && set PYEXE=python
)
if not defined PYEXE (
    echo  ERROR: Python not found. Install Python 3.10+ from python.org
    echo  If Python IS installed but the Store alias shadows it, disable it:
    echo  Settings ^> Apps ^> Advanced app settings ^> App execution aliases
    pause
    exit /b 1
)
echo  Using Python: %PYEXE%

echo  [1/4] Creating virtualenv .venv-mace ...
if not exist ".venv-mace\Scripts\python.exe" (
    %PYEXE% -m venv .venv-mace
    if errorlevel 1 (
        echo  ERROR: venv creation failed
        pause
        exit /b 1
    )
)

echo  [2/4] Upgrading pip ...
".venv-mace\Scripts\python.exe" -m pip install -q --upgrade pip

echo  [3/4] Installing torch 2.11 cu128 (~2.8 GB, NVIDIA GPU) ...
".venv-mace\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
    echo   WARNING: cu128 install failed, falling back to default torch ...
    ".venv-mace\Scripts\python.exe" -m pip install torch
)

echo  [4/4] Installing requirements-mace.txt ...
".venv-mace\Scripts\python.exe" -m pip install -r requirements-mace.txt
if errorlevel 1 (
    echo  ERROR: requirements install failed
    pause
    exit /b 1
)

echo.
echo  Verifying ...
".venv-mace\Scripts\python.exe" -c "import torch, ase, mace; print('torch', torch.__version__, '| cuda:', torch.cuda.is_available())"
echo.
echo  Bootstrap complete. Run run_mace.bat
pause
