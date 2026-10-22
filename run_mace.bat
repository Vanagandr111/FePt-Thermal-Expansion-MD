@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM --- MACE neural-potential runner (Windows, CPU/GPU), one-click ---
REM Usage: run_mace.bat [--quick] [--device cuda|cpu|auto] [other flags]
REM First run automatically creates .venv-mace via bootstrap_mace.bat

if not exist ".venv-mace\Scripts\python.exe" (
    echo  .venv-mace not found - first run, bootstrapping environment ...
    call bootstrap.bat
    if not exist ".venv-mace\Scripts\python.exe" (
        echo  ERROR: bootstrap failed
        pause
        exit /b 1
    )
)

".venv-mace\Scripts\python.exe" -u scripts\run_main_mace.py %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
    echo.
    echo  Exit code: %EXITCODE%
    pause
)
exit /b %EXITCODE%
