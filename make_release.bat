@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ============================================
echo  Fe-Pt MD - Release Archive Builder
echo ============================================
echo.

REM ── Get version ──
set VERSION=
for /f "delims=" %%V in ('git describe --tags --abbrev=0 2^>nul') do set VERSION=%%V
if "%VERSION%"=="" set VERSION=v1.6.7
echo  Version: %VERSION%
echo.

set ZIP_NAME=FePt-Thermal-Expansion-MD-%VERSION%-release.zip
set BUILD_DIR=%TEMP%\fept-release-%VERSION%

REM ── Clean build dir ──
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
mkdir "%BUILD_DIR%"

REM ── Root files ──
echo  [1/7] Copying root files...
copy run.bat                 "%BUILD_DIR%\" >nul
copy _run_lmp.bat            "%BUILD_DIR%\" >nul
copy bootstrap.bat           "%BUILD_DIR%\" >nul
copy bootstrap.bat           "%BUILD_DIR%\" >nul
copy bootstrap.sh            "%BUILD_DIR%\" >nul
copy run_mace.bat            "%BUILD_DIR%\" >nul
copy requirements.txt        "%BUILD_DIR%\" >nul
copy requirements-mace.txt   "%BUILD_DIR%\" >nul
copy README.md               "%BUILD_DIR%\" >nul
copy .gitattributes          "%BUILD_DIR%\" >nul
copy _regenerate_plots.py    "%BUILD_DIR%\" >nul

REM ── Scripts (exclude __pycache__) ──
echo  [2/7] Copying scripts...
mkdir "%BUILD_DIR%\scripts"
xcopy scripts\*.py "%BUILD_DIR%\scripts\" >nul
copy scripts
un_main_mace.sh "%BUILD_DIR%\scripts\" >nul

REM ── Data (pre-generated structures) ──
echo  [3/7] Copying data files...
mkdir "%BUILD_DIR%\data"
xcopy data\*.lmp "%BUILD_DIR%\data\" >nul

REM ── Potentials ──
echo  [4/7] Copying potentials...
mkdir "%BUILD_DIR%\potentials"
xcopy potentials\* "%BUILD_DIR%\potentials\" >nul

REM ── Docs ──
echo  [5/7] Copying docs...
mkdir "%BUILD_DIR%\docs"
xcopy docs\*.md "%BUILD_DIR%\docs\" >nul

REM ── LAMMPS binary (bin/) ──
echo  [6/7] Copying LAMMPS binary and DLLs...
if exist "bin\lmp.exe" (
    mkdir "%BUILD_DIR%\bin"
    xcopy bin\* "%BUILD_DIR%\bin\" >nul
) else (
    echo   WARNING: bin\lmp.exe not found! LAMMPS will not work.
)

REM ── Pre-calculated results (output_v4_256/) ──
echo  [7/7] Copying pre-calculated results...
if exist "output_v4_256\run_protocol.txt" (
    mkdir "%BUILD_DIR%\output_v4_256"
    xcopy output_v4_256\* "%BUILD_DIR%\output_v4_256\" /e >nul
) else (
    echo   No pre-calculated results found, skipping.
)

REM ── Create zip ──
echo.
echo ============================================
echo  Creating archive: %ZIP_NAME%
echo ============================================
if exist "%ZIP_NAME%" del "%ZIP_NAME%"

powershell -NoProfile -Command ^
    "Compress-Archive -Path '%BUILD_DIR%\\*' -DestinationPath '%PROJ_DIR%\\%ZIP_NAME%'" ^
    >nul 2>&1

if %errorlevel% equ 0 (
    echo  Done!
) else (
    echo  ERROR: compress failed, trying fallback...
    REM Fallback: Python zipfile
    python -c ^
        "import zipfile, os; z=zipfile.ZipFile(r'%ZIP_NAME%','w',zipfile.ZIP_DEFLATED);" ^
        "for root,dirs,files in os.walk(r'%BUILD_DIR%'):" ^
        "  for f in files:" ^
        "    fp=os.path.join(root,f);" ^
        "    z.write(fp,os.path.relpath(fp,r'%BUILD_DIR%'));" ^
        "z.close(); print('Done',z.filename)"
)

REM ── Verify ──
echo.
echo ============================================
echo  Verifying archive...
echo ============================================
python "%~dp0scripts\verify_release.py" "%ZIP_NAME%"
if %errorlevel% neq 0 (
    echo  WARNING: Verification script failed!
)


REM ── Cleanup ──
rmdir /s /q "%BUILD_DIR%" >nul 2>&1

echo ============================================
if %errorlevel% equ 0 (
    echo  Release archive created successfully!
) else (
    echo  ERROR: Something went wrong.
)
echo ============================================
echo.
echo  %ZIP_NAME%
echo.
pause
