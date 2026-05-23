@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM --- Detect Python ---
set PYTHON=
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=py -3.12
    goto python_detected
)
py -3.11 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON=py -3.11
    goto python_detected
)
python --version >nul 2>&1
if %errorlevel% equ 0 (
    python -c "import sys; ver=sys.version_info; exit(0 if (3,11) <= (ver.major,ver.minor) <= (3,12) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON=python
        goto python_detected
    )
)
echo.
echo   ERROR: Python 3.11 or 3.12 not found.
echo   Install Python from: https://www.python.org/downloads/
echo.
pause
exit /b 1
:python_detected
echo   Using: %PYTHON%
echo.

:MENU
cls
echo ============================================
echo       Fe-Pt MD - Thermal Expansion
echo ============================================
echo.
echo   [0] DEMO (50+100, 2048at, OpenMP)
echo.
echo   [1] TURBO-FAST (20k+50k, 256at, OpenMP)
echo   [2] TURBO 256at (50k+100k, OpenMP)
echo   [3] TURBO 2048at (OpenMP)
echo   [4] TURBO 2048at (KOKKOS)
echo.
echo   [5] LONG 256at (OpenMP)
echo   [6] LONG 2048at (OpenMP)
echo   [7] LONG 2048at (KOKKOS)
echo.
echo   [8] TURBO-EXPERIMENTAL 256at (OMP 4t, neigh/5)
echo.
echo   [x] Exit
echo.
echo ============================================
set /p CHOICE="Your choice (0-8,x): "

if /i "%CHOICE%"=="x" exit /b 0

echo.
echo [DIAG] CHOICE='%CHOICE%'
echo --- Seed Configuration ---
echo.
echo   [Enter]     - auto-generate new random seed
echo   [12345]     - enter a specific seed number
echo   [R]         - re-use last used seed
echo.
set /p SEED_INPUT="Seed (Enter=auto / R=reuse / number): "

set SEED_FLAG=
if not "%SEED_INPUT%"=="" (
    if /i "%SEED_INPUT%"=="R" (
        set SEED_FLAG=--seed "reuse"
    ) else (
        set SEED_FLAG=--seed "%SEED_INPUT%"
    )
)

echo.
rem --- Archive old results ---
set OUT_DIR=output_v4_256
if "%CHOICE%"=="0" set OUT_DIR=output_v4
if "%CHOICE%"=="3" set OUT_DIR=output_v4
if "%CHOICE%"=="4" set OUT_DIR=output_v4
if "%CHOICE%"=="6" set OUT_DIR=output_v4
if "%CHOICE%"=="7" set OUT_DIR=output_v4

if exist "%OUT_DIR%" (
    echo.
    echo ============================================
    echo  Archiving old %OUT_DIR%...
    powershell -NoProfile -Command ^
        "$d='%~dp0%OUT_DIR%'; " ^
        "if(Test-Path $d){ " ^
        "  $ts=Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'; " ^
        "  $b=$d+'_backup_'+$ts; " ^
        "  try{ " ^
        "    Move-Item $d $b -ErrorAction Stop; " ^
        "    Write-Host '  Archived to: ' (Split-Path $b -Leaf) " ^
        "  }catch{ " ^
        "    Write-Host '  WARNING: Move-Item failed (' $_.Exception.Message ')'; " ^
        "    Write-Host '  Trying robocopy + delete...'; " ^
        "    robocopy $d $b /E /MOVE /NFL /NDL /NJH /NJS /NP >nul 2>&1; " ^
        "    if exist $d ( " ^
        "      Write-Host '  WARNING: Could not archive — directory locked, continuing...'; " ^
        "    ) else ( " ^
        "      Write-Host '  Archived to: ' (Split-Path $b -Leaf) ' (via copy)'; " ^
        "    ) " ^
        "  } " ^
        "}"
    echo ============================================
)

echo.
echo ============================================
if "%CHOICE%"=="0" echo  Starting DEMO mode
if "%CHOICE%"=="0" %PYTHON% "%~dp0scripts\run_mode.py" --mode demo %SEED_FLAG%

if "%CHOICE%"=="1" echo  Starting TURBO-FAST (256at, OpenMP)
if "%CHOICE%"=="1" %PYTHON% "%~dp0scripts\run_mode.py" --mode turbo-fast %SEED_FLAG%

if "%CHOICE%"=="2" echo  Starting TURBO 256at (OpenMP)
if "%CHOICE%"=="2" %PYTHON% "%~dp0scripts\run_mode.py" --mode turbo --natoms 256 --backend omp %SEED_FLAG%

if "%CHOICE%"=="3" echo  Starting TURBO 2048at (OpenMP)
if "%CHOICE%"=="3" %PYTHON% "%~dp0scripts\run_mode.py" --mode turbo --natoms 2048 --backend omp %SEED_FLAG%

if "%CHOICE%"=="4" echo  Starting TURBO 2048at (KOKKOS)
if "%CHOICE%"=="4" %PYTHON% "%~dp0scripts\run_mode.py" --mode turbo --natoms 2048 --backend kokkos %SEED_FLAG%

if "%CHOICE%"=="5" echo  Starting LONG 256at (OpenMP)
if "%CHOICE%"=="5" %PYTHON% "%~dp0scripts\run_mode.py" --mode long --natoms 256 --backend omp %SEED_FLAG%

if "%CHOICE%"=="6" echo  Starting LONG 2048at (OpenMP)
if "%CHOICE%"=="6" %PYTHON% "%~dp0scripts\run_mode.py" --mode long --natoms 2048 --backend omp %SEED_FLAG%

if "%CHOICE%"=="7" echo  Starting LONG 2048at (KOKKOS)
if "%CHOICE%"=="7" %PYTHON% "%~dp0scripts\run_mode.py" --mode long --natoms 2048 --backend kokkos %SEED_FLAG%

if "%CHOICE%"=="8" echo  Starting TURBO-EXPERIMENTAL 256at (OMP 4t, neigh/5)
if "%CHOICE%"=="8" %PYTHON% "%~dp0scripts\run_mode.py" --mode turbo-experimental %SEED_FLAG%
echo ============================================
goto END

:END
echo.
echo ============================================
echo    DONE -- All calculations finished
echo    Results in %OUT_DIR%
echo ============================================
echo.
pause
exit /b 0
