@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

cls
echo ============================================
echo    Fe-Pt MD — Thermal Expansion Calculator
echo ============================================
echo.

REM --- Check for existing results ---
set HAS_RESULTS=0
if exist "results\logs" (
    dir /b "results\logs\log_*.lmp" >nul 2>nul
    if not errorlevel 1 set HAS_RESULTS=1
)

if "%HAS_RESULTS%"=="1" (
    echo  Existing results found in results\
    echo.
    set /p CLEAN="Clear and recalculate? [y/N]: "
    if /i "%CLEAN%"=="y" (
        echo.
        echo  Cleaning results...
        rmdir /s /q "results" 2>nul
        echo  Done.
    ) else (
        echo  Cancelled.
        pause
        exit /b 0
    )
)

echo.
echo  Starting calculations...
echo.

%PYTHON% scripts\run_main.py
if errorlevel 1 (
    echo [ERROR] Calculation failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo    Done! Results saved to results\
echo ============================================
echo.
echo  results\results.csv         — data table
echo  results\plots\a_vs_T.png    — a(T)
echo  results\plots\a_vs_comp.png — a(comp)
echo  results\plots\a_vs_T_facets.png — detailed
echo.
pause
exit /b 0
