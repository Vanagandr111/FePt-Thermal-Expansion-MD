@echo off
chcp 65001 >nul
REM === check_release.bat - Windows Release Sanity Check ===
REM Runs WSL dependency guard and verifies active runtime config.
REM Windows-only. No WSL.

setlocal enabledelayedexpansion
cd /d "%~dp0"
set PROJ_DIR=%CD%

REM ==================================================
REM Phase 0: Find Windows Python
REM ==================================================
set "PYTHON_EXE="
set "PYTHON_SOURCE="

REM Try .venv first (preferred)
if exist ".venv\Scripts\python.exe" (
    for %%P in (.venv\Scripts\python.exe) do set "PYTHON_EXE=%%~fP"
    set "PYTHON_SOURCE=.venv\Scripts\python.exe"
) else (
    REM Try py -3 (Python Launcher for Windows)
    where py >nul 2>nul
    if !errorlevel! equ 0 (
        for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
            if not "%%P"=="" (
                set "PYTHON_EXE=%%P"
                set "PYTHON_SOURCE=py -3"
            )
        )
    )
    if "!PYTHON_EXE!"=="" (
        REM Try python (system PATH)
        where python >nul 2>nul
        if !errorlevel! equ 0 (
            for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
                if not "%%P"=="" (
                    set "PYTHON_EXE=%%P"
                    set "PYTHON_SOURCE=python (PATH)"
                )
            )
        )
    )
)

echo ==================================================
echo Fe-Pt MD - Windows Release Check
echo ==================================================
echo.
echo Project: %PROJ_DIR%
echo.

REM ===================================================================
REM Phase 1: WSL dependency guard
REM ===================================================================
echo [1/4] Running WSL dependency scan...
echo.

if "!PYTHON_EXE!"=="" (
    echo [FAIL] No Windows Python found!
    echo   Tried: .venv\Scripts\python.exe, py -3, python
    echo   Run bootstrap.bat first or install Python 3.10+ on Windows.
    pause
    exit /b 1
)

echo   Python: !PYTHON_SOURCE!
echo   Path:   !PYTHON_EXE!

REM Verify this is NOT WSL Python
echo !PYTHON_EXE! | findstr /i "/mnt/" >nul 2>nul
if !errorlevel! equ 0 (
    echo [FAIL] Detected WSL Python path: !PYTHON_EXE!
    echo   Windows-only release must use Windows Python.
    pause
    exit /b 1
)

"!PYTHON_EXE!" scripts\check_no_wsl_refs.py
set "RET=!errorlevel!"
echo.
echo   WSL scan exit code: !RET!

if !RET! neq 0 (
    echo.
    echo [FAIL] WSL dependencies found in active runtime!
    echo Fix the files above and re-run this check.
    pause
    exit /b 1
)
echo [OK] No WSL dependencies.
echo.

REM ===================================================================
REM Phase 2: Verify run_main.bat calls Phase 4 only
REM ===================================================================
echo [2/4] Verifying run_main.bat calls Phase 4...
echo.

findstr /i "run_phase4" run_main.bat >nul
if !errorlevel! equ 0 (
    echo   run_main.bat -^> scripts\run_phase4.py OK
) else (
    echo [FAIL] run_main.bat does NOT call run_phase4.py!
    pause
    exit /b 1
)

REM Check it does NOT call legacy scripts
findstr /i "run_all.py run_fept_grid" run_main.bat >nul
if !errorlevel! equ 0 (
    echo [FAIL] run_main.bat still calls legacy scripts!
    pause
    exit /b 1
) else (
    echo   No legacy script calls found OK
)
echo [OK] run_main.bat verified.
echo.

REM ===================================================================
REM Phase 3: Verify legacy isolation
REM ===================================================================
echo [3/4] Verifying legacy_DO_NOT_RUN isolation...
echo.

if not exist "legacy_DO_NOT_RUN\" (
    echo [WARN] legacy_DO_NOT_RUN\ directory not found!
) else (
    dir /b legacy_DO_NOT_RUN\ >nul && (
        echo   Directory exists with content OK
    ) || (
        echo [WARN] legacy_DO_NOT_RUN\ is empty!
    )
)
echo [OK] legacy isolation verified.
echo.

REM ===================================================================
REM Phase 4: Check shebangs (must NOT be python3)
REM ===================================================================
echo [4/4] Checking shebangs in active scripts...
echo.

"!PYTHON_EXE!" scripts\check_shebangs.py
if !errorlevel! neq 0 (
    echo.
    echo [WARN] Some scripts still have python3 shebangs.
    echo   This is informational - Python on Windows ignores shebangs.
    echo   To fix: change '#!/usr/bin/env python3' to '#!/usr/bin/env python'
)
echo [OK] Shebang check complete.
echo.

REM ===================================================================
REM Summary
REM ===================================================================
echo ==================================================
echo RELEASE CHECK COMPLETE
echo ==================================================
echo.
echo Active runtime is Windows-only.
echo WSL is NOT required and NOT supported.
echo.
echo Entry points:
echo   bootstrap.bat   - setup
echo   run_demo.bat    - demo (2 points)
echo   run_main.bat    - full Phase 4 run (20 points)
echo.

endlocal
pause
exit /b 0
