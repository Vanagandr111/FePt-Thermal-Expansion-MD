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
        echo  Backing up old results...
        for /f "tokens=2 delims==." %%I in ('wmic os get localdatetime /value') do set DT=%%I
        set BACKUP_DIR=backup\results_%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%%DT:~10,2%%DT:~12,2%
        mkdir "%BACKUP_DIR%" 2>nul
        move "results" "%BACKUP_DIR%" >nul 2>nul
        if exist "%BACKUP_DIR%\results" (
            echo  Backup saved to: %BACKUP_DIR%\results
        ) else (
            rmdir /s /q "%BACKUP_DIR%" 2>nul
            echo  WARNING: Could not create backup, cleaning directly...
            rmdir /s /q "results" 2>nul
        )
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
