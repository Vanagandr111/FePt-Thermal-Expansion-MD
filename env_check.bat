@echo off
chcp 65001 >nul

REM === env_check.bat — сбор информации об окружении ===
REM Windows-first. Работает из любой копии папки проекта.

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==============================================
echo Environment Check — FePt Project
echo ==============================================
echo.

echo [1] Windows Version:
ver
echo.

echo [2] Python:
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python --version 2>&1
    .venv\Scripts\python -c "import sys; print(f'  Path: {sys.executable}')" 2>&1
) else (
    echo   [WARN] .venv не найден — создайте через bootstrap.bat
)
for /f "tokens=*" %%V in ('python --version 2^>^&1') do echo   (system) %%V
echo.

echo [3] LAMMPS (Windows-first):
call :find_lammps
if %errorlevel% equ 0 (
    echo   LMP_EXE: %LMP_EXE%
) else (
    echo   [NOT FOUND] LAMMPS не найден.
    echo   Установите LAMMPS для Windows с lammps.org
    echo   Или задайте LMP_EXE вручную
)
echo.

echo [4] Python packages (.venv):
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python -c "import numpy; print(f'  numpy: {numpy.__version__}')" 2>&1
    .venv\Scripts\python -c "import matplotlib; print(f'  matplotlib: {matplotlib.__version__}')" 2>&1
) else (
    echo   [NOT FOUND] .venv — запустите bootstrap.bat
)
echo.

echo [5] Structure check:
echo   Project folder: %PROJ_DIR%
if exist %PROJ_DIR%\scripts\ (echo   scripts/     [FOUND]) else (echo   scripts/     [MISSING])
if exist %PROJ_DIR%\data\ (echo   data/        [FOUND]) else (echo   data/        [MISSING])
if exist %PROJ_DIR%\potentials\ (echo   potentials/  [FOUND]) else (echo   potentials/  [MISSING])
if exist %PROJ_DIR%\output\ (echo   output/      [FOUND]) else (echo   output/      [MISSING])
if exist %PROJ_DIR%\run_demo.bat (echo   run_demo.bat [FOUND]) else (echo   run_demo.bat [MISSING])
if exist %PROJ_DIR%\INSTALL_AND_RUN.txt (echo   INSTALL_AND_RUN.txt [FOUND]) else (echo   INSTALL_AND_RUN.txt [MISSING])
echo.

echo ==============================================
echo Check complete.
echo ==============================================
echo.

endlocal
pause
exit /b 0

REM ============================================================
REM Подпрограмма поиска LAMMPS
REM ============================================================
:find_lammps
if defined LMP_EXE (
    if exist "%LMP_EXE%" exit /b 0
)
where lmp.exe >nul 2>&1
if %errorlevel% equ 0 (
    set LMP_EXE=lmp.exe
    exit /b 0
)
where lmp >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%P in ('where lmp') do (
        set LMP_EXE=%%P
        exit /b 0
    )
)
set LMP_PATHS="C:\Program Files\LAMMPS 64-bit\bin\lmp.exe" "C:\Program Files\LAMMPS 64-bit\lmp.exe" "C:\Program Files\LAMMPS\lmp.exe" "C:\Program Files (x86)\LAMMPS\lmp.exe" "C:\LAMMPS\lmp.exe"
for %%P in (%LMP_PATHS%) do (
    if exist %%P (
        set LMP_EXE=%%~P
        exit /b 0
    )
)
if exist "%PROJ_DIR%\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\lmp.exe
    exit /b 0
)
where wsl.exe >nul 2>&1
if %errorlevel% equ 0 (
    wsl.exe which lmp >nul 2>&1
    if %errorlevel% equ 0 (
        set LMP_EXE=wsl.exe lmp
        exit /b 0
    )
)
exit /b 1
