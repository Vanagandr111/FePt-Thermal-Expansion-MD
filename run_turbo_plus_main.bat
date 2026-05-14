@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ================================================================
REM run_turbo_plus_main.bat — Phase 4 Turbo Plus (parallel + faster)
REM
REM What it does:
REM   • Auto-detects CPU cores → parallel LAMMPS runs
REM   • neighbor 1.0 bin (safe)
REM   • 20k eq + 50k prod (instead of 50k+100k) — ~3× faster
REM   • Minimal quality risk: equilibrium ~10k steps for 256 atoms
REM   • Works on 1-core, 4-core, 8-core, any machine
REM ================================================================

echo.
echo ================================================================
echo   Fe-Pt Phase 4 - TURBO PLUS MODE
echo   Parallel + neighbor fix + shorter steps
echo   ~3x faster, very slight quality risk
echo ================================================================
echo.
echo   Protocol: 20k eq + 50k prod (vs 50k+100k original)
echo   Cores detected: %NUMBER_OF_PROCESSORS%
echo.
echo   NOTE: For 256 atoms, equilibrium converges in ~10k steps.
echo   20k eq is conservative. Run original 50k+100k for reference.
echo.

call .venv\Scripts\activate 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: Could NOT activate virtual environment.
    echo Make sure .venv exists or run: python -m venv .venv
    echo Then: .venv\Scripts\pip install -r requirements.txt
    echo.
    echo Falling back to system Python...
)

python scripts/run_phase4_turbo.py --turbo-plus %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE%==0 (
    echo ✅ TURBO PLUS run completed successfully!
) else (
    echo ⚠️  TURBO PLUS run finished with %EXIT_CODE% failures.
    echo Check output_v4/integrity_check_v4_turbo.txt for details.
)
echo.

pause
exit /b %EXIT_CODE%
