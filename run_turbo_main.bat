@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ================================================================
REM run_turbo_main.bat — Phase 4 Turbo (safe parallel + neighbor fix)
REM
REM What it does:
REM   • Auto-detects CPU cores → parallel LAMMPS runs
REM   • neighbor 1.0 bin (instead of 2.0) — safe, ~10% faster
REM   • 50k eq + 100k prod — IDENTICAL quality to original
REM   • Works on 1-core, 4-core, 8-core, any machine
REM ================================================================

echo.
echo ================================================================
echo   Fe-Pt Phase 4 - TURBO MODE
echo   Parallel + neighbor fix (NO quality loss)
echo ================================================================
echo.
echo   Cores detected: %NUMBER_OF_PROCESSORS%

call .venv\Scripts\activate 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: Could NOT activate virtual environment.
    echo Make sure .venv exists or run: python -m venv .venv
    echo Then: .venv\Scripts\pip install -r requirements.txt
    echo.
    echo Falling back to system Python...
)

python scripts/run_phase4_turbo.py --turbo %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE%==0 (
    echo ✅ TURBO run completed successfully!
) else (
    echo ⚠️  TURBO run finished with %EXIT_CODE% failures.
    echo Check output_v4/integrity_check_v4_turbo.txt for details.
)
echo.

pause
exit /b %EXIT_CODE%
