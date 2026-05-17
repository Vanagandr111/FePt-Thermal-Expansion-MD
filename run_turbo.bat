@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM === run_turbo.bat - Phase 4 Accurate Parallel ===
REM 50k eq + 100k prod + MEAM PtFe.meam
REM Windows-only. No WSL.

setlocal

echo.
echo ================================================================
echo Fe-Pt Phase 4 - TURBO MODE (Accurate Parallel)
echo Protocol: 50k eq + 100k prod + MEAM PtFe.meam
echo Parallel execution (NO quality loss)
echo ================================================================
echo.
echo Cores detected: %NUMBER_OF_PROCESSORS%

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
    echo Turbo run completed successfully!
    echo Results: output_v4_parallel\all_results_v4_turbo.csv
) else (
    echo Turbo run finished with %EXIT_CODE% failures.
    echo Check output_v4_parallel\integrity_check_v4_turbo.txt for details.
)
echo.

endlocal
pause
exit /b %EXIT_CODE%
