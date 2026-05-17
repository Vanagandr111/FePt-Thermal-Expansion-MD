@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

cls
echo ============================================
echo    Fe-Pt MD — Thermal Expansion Calculator
echo ============================================
echo.

REM --- Mode selection ---
:MENU_MODE
echo  Select calculation mode:
echo.
echo    [M]  MAIN      — run_main.py (sequential, full 50k+100k, results^)
echo    [T]  TURBO     — parallel, high-accuracy (50k eq + 100k prod)
echo    [P]  TURBO-PLUS  — parallel, fast (20k eq + 50k prod)
echo    [L]  LONG      — sequential, Long Protocol (50k eq + 100k prod)
echo.
set MODE=M
set /p MODE="Choose [M/T/P/L] (default M): "
if /i "%MODE%"=="T" set MODE_LABEL=TURBO
if /i "%MODE%"=="T" set SCRIPT=scripts\run_phase4_turbo.py
if /i "%MODE%"=="T" set MODE_FLAG=--turbo
if /i "%MODE%"=="T" set OUT_DIR=output_v4
if /i "%MODE%"=="P" set MODE_LABEL=TURBO-PLUS
if /i "%MODE%"=="P" set SCRIPT=scripts\run_phase4_turbo.py
if /i "%MODE%"=="P" set MODE_FLAG=--turbo-plus
if /i "%MODE%"=="P" set OUT_DIR=output_v4
if /i "%MODE%"=="L" set MODE_LABEL=LONG
if /i "%MODE%"=="L" set SCRIPT=scripts\run_phase4.py
if /i "%MODE%"=="L" set MODE_FLAG=
if /i "%MODE%"=="L" set OUT_DIR=output_v4
if /i "%MODE%"=="M" set MODE_LABEL=MAIN
if /i "%MODE%"=="M" set SCRIPT=scripts\run_main.py
if /i "%MODE%"=="M" set MODE_FLAG=
if /i "%MODE%"=="M" set OUT_DIR=results
if not defined SCRIPT (
    echo  Invalid choice, using MAIN
    set MODE=M
    set MODE_LABEL=MAIN
    set SCRIPT=scripts\run_main.py
    set MODE_FLAG=
    set OUT_DIR=results
)

cls
echo ============================================
echo  Mode: %MODE_LABEL%
echo ============================================
echo.

REM --- Resume / Partial results check ---
set PARTIAL=0
if "%OUT_DIR%"=="results" (
    if exist "results\logs" dir /b "results\logs\log_*.lmp" >nul 2>nul
    if not errorlevel 1 set PARTIAL=1
)
if "%OUT_DIR%"=="output_v4" (
    if exist "output_v4\logs" dir /b "output_v4\logs\log_*.lmp" >nul 2>nul
    if not errorlevel 1 set PARTIAL=1
)

if "%PARTIAL%"=="1" (
    echo  [^>] Existing log files found in %OUT_DIR%\logs^\
    echo.
    set /p RESUME="Continue (resume) from where it stopped? [Y/n]: "
    if /i "!RESUME!"=="Y" set RESUME_FLAG=1
    if /i "!RESUME!"=="" set RESUME_FLAG=1
    if "!RESUME_FLAG!"=="1" (
        echo  Will resume — existing points will be kept.
        echo.
    ) else (
        set /p FORCE_RESUME="Clear all and recalculate from scratch? [y/N]: "
        if /i "!FORCE_RESUME!"=="y" (
            if "%OUT_DIR%"=="results" rmdir /s /q results >nul 2>nul & mkdir results >nul 2>nul
            if "%OUT_DIR%"=="output_v4" rmdir /s /q output_v4 >nul 2>nul
            echo  Cleared. Will start fresh.
        ) else (
            echo  Cancelled.
            pause
            exit /b 0
        )
    )
)

REM --- Seed dialog ---
echo.
echo  --- Seed Configuration ---
echo.
echo  Options:
echo    [Enter]     — auto-generate new random seed
echo    [12345]     — enter a specific seed number
echo    [R]         — re-use last used seed
echo.

set /p SEED_INPUT="Seed (Enter=auto / R=re-use / number): "

set SEED_ARGS=
if /i "!SEED_INPUT!"=="R" (
    set SEED_ARGS=--seed
    echo  Will re-use last seed.
) else if "!SEED_INPUT!"=="" (
    set SEED_ARGS=
    echo  Will auto-generate seed.
) else (
    set SEED_ARGS=--seed !SEED_INPUT!
    echo  Manual seed: !SEED_INPUT!
)

REM --- Build command ---
echo.
echo ============================================
echo   Starting %MODE_LABEL% mode
echo   Script: %SCRIPT%
echo   Args: %MODE_FLAG% %SEED_ARGS%
echo ============================================
echo.

%PYTHON% %SCRIPT% %MODE_FLAG% %SEED_ARGS%
if errorlevel 1 (
    echo.
    echo [ERROR] Calculation failed (exit code %errorlevel%^)
    pause
    exit /b 1
)

echo.
echo ============================================
echo    Done! Results saved to %OUT_DIR%^\
echo ============================================
echo.
if "%OUT_DIR%"=="results" (
    echo  results\results.csv            — data table (with seed)
    echo  results\plots\a_vs_T.png       — a(T^) plot (seed in title^)
    echo  results\plots\a_vs_comp.png    — a(comp^) plot
    echo  results\plots\a_vs_T_facets.png — detailed facets
) else (
    echo  %OUT_DIR%\all_results*.csv     — data table (with seed)
    echo  %OUT_DIR%\a_vs_T_all*.png      — a(T^) plot
    echo  %OUT_DIR%\a_vs_comp*.png       — a(comp^) plot
    echo  %OUT_DIR%\integrity_check*.txt — integrity report
)
echo  seed_info.txt in output dir      — calculation seed
echo  seed.txt in project root         — last used seed
echo.
pause
exit /b 0
