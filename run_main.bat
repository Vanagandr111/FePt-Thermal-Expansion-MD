@echo off
chcp 65001 >nul

REM === run_main.bat — Полный прогон Fe-Pt ===
REM Windows-first: uses C:\Windows\System32\wsl.exe python3 for the runner script
REM Авто-детект .venv (создаётся bootstrap.bat) с fallback на system python

setlocal
cd /d C:\проекты\Nikolay

echo ==================================================
echo Fe-Pt MD Thermal Expansion — FULL RUN
echo 5 compositions x 4 temperatures = 20 simulations
echo ==================================================
echo.

REM --- Детект Python: .venv prefer, fallback system ---
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    for /f "delims=" %%V in ('".venv\Scripts\python.exe" --version 2^>^&1') do echo [.venv] %%V
) else (
    set PYTHON=python
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found.
        echo   Запустите bootstrap.bat для автоматической установки.
        pause
        exit /b 1
    )
    for /f "delims=" %%V in ('python --version 2^>^&1') do echo [system] %%V
)
echo [OK] Python ready
echo.

REM Check WSL + LAMMPS
C:\Windows\System32\wsl.exe which lmp >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] LAMMPS not found in WSL.
    pause
    exit /b 1
)
echo [OK] LAMMPS (WSL) found
echo.

echo [OK] Starting full run via WSL python3
echo Time estimate: 10-20 minutes
echo.

REM Run full script in WSL (it handles all paths internally)
C:\Windows\System32\wsl.exe python3 /mnt/c/проекты/Nikolay/scripts/run_all.py
if %errorlevel% neq 0 (
    echo [ERROR] Run failed
    pause
    exit /b 1
)

echo.
echo ==================================================
echo FULL RUN COMPLETE!
echo Results: output\all_results.csv
echo Plots:   output\a_vs_T_all.png
echo          output\a_vs_comp.png
echo ==================================================
echo.
endlocal
pause
