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
where py >nul 2>nul && for /f "delims=" %%V in ('py -3 --version 2^>^>nul') do set PYVER=%%V
if exist ".venv-mace\Scripts\python.exe" (
    set PYEXE=.venv-mace\Scripts\python.exe
) else (
    where python >nul 2>nul && set PYEXE=python
)
if "%PYEXE%"=="" (
    echo  ERROR: Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

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
