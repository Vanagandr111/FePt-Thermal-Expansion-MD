     1|@echo off
     2|chcp 65001 >nul
     3|cd /d "%~dp0"
     4|
     5|REM --- Detect Python ---
     6|set PYTHON=
     7|py -3.12 --version >nul 2>&1
     8|if %errorlevel% equ 0 (
     9|    set PYTHON=py -3.12
    10|    goto python_detected
    11|)
    12|py -3.11 --version >nul 2>&1
    13|if %errorlevel% equ 0 (
    14|    set PYTHON=py -3.11
    15|    goto python_detected
    16|)
    17|python --version >nul 2>&1
    18|if %errorlevel% equ 0 (
    19|    python -c "import sys; ver=sys.version_info; exit(0 if (3,11) <= (ver.major,ver.minor) <= (3,12) else 1)" >nul 2>&1
    20|    if %errorlevel% equ 0 (
    21|        set PYTHON=python
    22|        goto python_detected
    23|    )
    24|)
    25|echo.
    26|echo   ERROR: Python 3.11 or 3.12 not found.
    27|echo   Install Python from: https://www.python.org/downloads/
    28|echo.
    29|pause
    30|exit /b 1
    31|:python_detected
    32|echo   Using: %PYTHON%
    33|echo.
    34|
    35|:MENU
    36|cls
    37|echo ============================================
    38|echo       Fe-Pt MD - Thermal Expansion
    39|echo ============================================
    40|echo.
    41|echo   [0] DEMO (50+100, 2048at, OpenMP)
    42|echo.
    43|echo   [1] TURBO-FAST (20k+50k, 256at, OpenMP)
    44|echo   [2] TURBO 256at (50k+100k, OpenMP)
    45|echo   [3] TURBO 2048at (OpenMP)
    46|echo   [4] TURBO 2048at (KOKKOS)
    47|echo.
    48|echo   [5] LONG 256at (OpenMP)
    49|echo   [6] LONG 2048at (OpenMP)
    50|echo   [7] LONG 2048at (KOKKOS)
    51|echo.
    52|echo   [8] TURBO-EXPERIMENTAL 256at (OMP 4t, neigh/5)
    53|echo.
    54|echo   [x] Exit
    55|echo.
    56|echo ============================================
    57|set /p CHOICE="Your choice (0-8,x): "
    58|
    59|if /i "%CHOICE%"=="x" exit /b 0
    60|
    61|echo.
    62|echo [DIAG] CHOICE='%CHOICE%'
    63|echo --- Seed Configuration ---
    64|echo.
    65|echo   [Enter]     - auto-generate new random seed
    66|echo   [12345]     - enter a specific seed number
    67|echo   [R]         - re-use last used seed
    68|echo.
    69|set /p SEED_INPUT="Seed (Enter=auto / R=reuse / number): "
    70|
    71|set SEED_FLAG=
    72|if not "%SEED_INPUT%"=="" (
    73|    if /i "%SEED_INPUT%"=="R" (
    74|        set SEED_FLAG=--seed "reuse"
    75|    ) else (
    76|        set SEED_FLAG=--seed "%SEED_INPUT%"
    77|    )
    78|)
    79|
    80|echo.
    81|rem --- Archive old results ---
    82|set OUT_DIR=output_v4_256
    83|if "%CHOICE%"=="0" set OUT_DIR=output_v4
    84|if "%CHOICE%"=="3" set OUT_DIR=output_v4
    85|if "%CHOICE%"=="4" set OUT_DIR=output_v4
    86|if "%CHOICE%"=="6" set OUT_DIR=output_v4
    87|if "%CHOICE%"=="7" set OUT_DIR=output_v4
    88|
    89|if exist "%OUT_DIR%" (
    90|    echo.
    91|    echo ============================================
    92|    echo  Archiving old %OUT_DIR%...
    93|    powershell -NoProfile -Command "$d='%~dp0%OUT_DIR%'; if(Test-Path $d){$ts=Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'; $b=$d+'_backup_'+$ts; Move-Item $d $b; Write-Host '  Archived to: ' (Split-Path $b -Leaf)}"
    94|    echo ============================================
    95|)
    96|
    97|echo.
    98|echo ============================================
    99|if "%CHOICE%"=="0" echo  Starting DEMO mode
   100|if "%CHOICE%"=="0" %PYTHON% "%~dp0scripts
un_mode.py" --mode demo %SEED_FLAG%
   101|
   102|if "%CHOICE%"=="1" echo  Starting TURBO-FAST (256at, OpenMP)
   103|if "%CHOICE%"=="1" %PYTHON% "%~dp0scripts
un_mode.py" --mode turbo-fast %SEED_FLAG%
   104|
   105|if "%CHOICE%"=="2" echo  Starting TURBO 256at (OpenMP)
   106|if "%CHOICE%"=="2" %PYTHON% "%~dp0scripts
un_mode.py" --mode turbo --natoms 256 --backend omp %SEED_FLAG%
   107|
   108|if "%CHOICE%"=="3" echo  Starting TURBO 2048at (OpenMP)
   109|if "%CHOICE%"=="3" %PYTHON% "%~dp0scripts
un_mode.py" --mode turbo --natoms 2048 --backend omp %SEED_FLAG%
   110|
   111|if "%CHOICE%"=="4" echo  Starting TURBO 2048at (KOKKOS)
   112|if "%CHOICE%"=="4" %PYTHON% "%~dp0scripts
un_mode.py" --mode turbo --natoms 2048 --backend kokkos %SEED_FLAG%
   113|
   114|if "%CHOICE%"=="5" echo  Starting LONG 256at (OpenMP)
   115|if "%CHOICE%"=="5" %PYTHON% "%~dp0scripts
un_mode.py" --mode long --natoms 256 --backend omp %SEED_FLAG%
   116|
   117|if "%CHOICE%"=="6" echo  Starting LONG 2048at (OpenMP)
   118|if "%CHOICE%"=="6" %PYTHON% "%~dp0scripts
un_mode.py" --mode long --natoms 2048 --backend omp %SEED_FLAG%
   119|
   120|if "%CHOICE%"=="7" echo  Starting LONG 2048at (KOKKOS)
   121|if "%CHOICE%"=="7" %PYTHON% "%~dp0scripts
un_mode.py" --mode long --natoms 2048 --backend kokkos %SEED_FLAG%
   122|
   123|if "%CHOICE%"=="8" echo  Starting TURBO-EXPERIMENTAL 256at (OMP 4t, neigh/5)
   124|if "%CHOICE%"=="8" %PYTHON% "%~dp0scripts
un_mode.py" --mode turbo-experimental %SEED_FLAG%
   125|echo ============================================
   126|goto END
   127|
   128|:END
   129|echo.
   130|echo ============================================
   131|echo    DONE -- All calculations finished
   132|echo    Results in %OUT_DIR%echo ============================================
   133|echo.
   134|pause
   135|exit /b 0
   136|