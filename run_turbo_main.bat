@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ================================================================
REM run_turbo_main.bat — Phase 4 Accurate Parallel
REM
REM Same validated protocol as run_main.bat but parallel:
REM   • 50k equilibration + 100k production (NO quality loss)
REM   • neighbor 1.0 bin (safe for 256 atoms)
REM   • Auto-detects CPU cores → parallel execution
REM   • Output: output_v4_parallel/ — SEPARATE from final
REM ================================================================

echo.
echo ================================================================
echo   Fe-Pt Phase 4 — ACCURATE PARALLEL MODE
echo   Same protocol as main: 50k eq + 100k prod + MEAM PtFe.meam
echo   Parallel execution (NO quality loss)
echo ================================================================
echo.
echo   Cores detected: %NUMBER_OF_PROCESSORS%

call .venv\Scripts\activate 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: Could NOT activate virtual environment.
    echo Falling back to system Python...
)

python scripts/run_phase4_turbo.py --turbo --force --output-dir output_v4_parallel %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE%==0 (
    echo ✅ ACCURATE PARALLEL run completed successfully!
    echo   Results: output_v4_parallel\all_results_v4_turbo.csv
) else (
    echo ⚠️  ACCURATE PARALLEL run finished with %EXIT_CODE% failures.
    echo   Check output_v4_parallel\integrity_check_v4_turbo.txt for details.
)
echo.

pause
exit /b %EXIT_CODE%
