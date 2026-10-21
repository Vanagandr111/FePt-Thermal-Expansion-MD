@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ============================================================
REM  FePt Web GUI — one-click launcher (no frozen exe needed).
REM  Starts gui/server.py and opens http://127.0.0.1:8321/ in
REM  the default browser.  Engine deps (torch/mace/ase, LAMMPS)
REM  are resolved from the project folders, never bundled.
REM ============================================================

set PYTHON=

REM 1) project venv (fully equipped: torch + mace + ase)
if exist ".venv-mace\Scripts\python.exe" (
    set "PYTHON=.venv-mace\Scripts\python.exe"
    goto python_detected
)

REM 2) plain interpreters, same fallback order as run.bat
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=py -3.12"
    goto python_detected
)
py -3.11 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=py -3.11"
    goto python_detected
)
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=python"
    goto python_detected
)

echo.
echo   ERROR: Python not found (venv .venv-mace or Python 3.11+).
echo   Install Python from: https://www.python.org/downloads/
echo   or run bootstrap_mace.bat first.
echo.
pause
exit /b 1

:python_detected
echo   Using: %PYTHON%
echo   GUI:   http://127.0.0.1:8321/  (opens automatically)
echo.
%PYTHON% -u gui\server.py
pause
