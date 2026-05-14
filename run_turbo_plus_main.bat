@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ================================================================
REM run_turbo_plus_main.bat — Phase 4 REDUCED Protocol
REM
REM ⚠️  REDUCED / APPROXIMATE MODE — NOT FOR SCIENTIFIC FINAL RESULTS
REM
REM Uses shorter steps: 20k eq + 50k prod (vs 50k+100k accurate).
REM ~3x faster but slight quality risk from reduced equilibration.
REM Output: output_v4_reduced/ — SEPARATE from final
REM ================================================================

echo.
echo ================================================================
echo   Fe-Pt Phase 4 — REDUCED PROTOCOL (Approximate)
echo   ⚠️  NOT for scientific final results
echo ================================================================
echo.
echo   Protocol: 20k eq + 50k prod (REDUCED, vs 50k+100k accurate)
echo   Cores detected: %NUMBER_OF_PROCESSORS%
echo.
echo   NOTE: For 256 atoms, equilibrium converges in ~10k steps.
echo   20k eq is conservative. Run run_main.bat for reference.
echo   Output: output_v4_reduced\ — SEPARATE from final results.
echo.

call .venv\Scripts\activate 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: Could NOT activate virtual environment.
    echo Falling back to system Python...
)

python scripts/run_phase4_turbo.py --turbo-plus --force --output-dir output_v4_reduced %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE%==0 (
    echo ✅ REDUCED run completed successfully!
    echo   Results: output_v4_reduced\all_results_v4_turbo.csv
    echo.
    echo ⚠️  These results use REDUCED protocol (20k+50k).
    echo   They are APPROXIMATE, not final scientific results.
    echo   For final results run run_main.bat.
) else (
    echo ⚠️  REDUCED run finished with %EXIT_CODE% failures.
    echo   Check output_v4_reduced\integrity_check_v4_turbo.txt for details.
)
echo.

pause
exit /b %EXIT_CODE%
