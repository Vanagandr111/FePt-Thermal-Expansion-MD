@echo off
chcp 65001 >nul

REM === run_demo.bat — Быстрый тест Fe-Pt MD (2 точки) ===
REM Windows-first. Не требует WSL.
REM Использует lmp.exe из LMP_EXE, PATH или типовых путей установки.
REM Авто-детект .venv (создаётся bootstrap.bat) с fallback на system python

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==================================================
echo Fe-Pt MD Thermal Expansion — DEMO
echo ==================================================
echo.

REM --- Детект Python: .venv prefer, fallback system ---
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    for /f "delims=" %%V in ('".venv\Scripts\python.exe" --version 2^>^&1') do echo [.venv] %%V
) else (
    set PYTHON=python
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found.
        echo   Запустите bootstrap.bat для автоматической установки.
        pause
        exit /b 1
    )
    for /f "delims=" %%V in ('python --version 2^>^&1') do echo [system] %%V
)
echo [OK] Python ready
echo.

REM --- Поиск LAMMPS (Windows-first) ---
call :find_lammps
if errorlevel 1 (
    echo [ERROR] LAMMPS не найден!
    echo.
    echo Что делать:
    echo   Вариант 1: Установите LAMMPS для Windows с lammps.org
    echo             (https://packages.lammps.org/windows.html)
    echo.
    echo   Вариант 2: Если lmp.exe уже где-то лежит, задайте путь вручную:
    echo             set LMP_EXE=C:\путь\к\lmp.exe
    echo             и запустите run_demo.bat снова
    echo.
    echo   Вариант 3: Положите lmp.exe в папку bin\ проекта — его можно
    echo             скопировать из установки LAMMPS для Windows
    pause
    exit /b 1
)
echo [OK] LAMMPS: %LMP_EXE%
echo.

echo Running DEMO: Pt=1.0 at 300K and 600K (2 points)
echo.

REM Generate structure
echo [gen_structure] Creating 256-atom fcc Pt supercell...
%PYTHON% scripts\gen_structure.py 4 4 4 1.0 data\data.fept_demo.lmp
if %errorlevel% neq 0 (
    echo [ERROR] Structure generation failed
    pause
    exit /b 1
)
echo [OK] Structure generated
echo.

REM Pt=1.0, T=300K
echo [1/2] Pt=1.0, T=300K...
%LMP_EXE% -in scripts\in.thermal ^
    -var datafile data\data.fept_demo.lmp ^
    -var T 300 ^
    -var comp 1.0 ^
    -log output\log_demo_300.lmp
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=300K)

REM Pt=1.0, T=600K
echo [2/2] Pt=1.0, T=600K...
%LMP_EXE% -in scripts\in.thermal ^
    -var datafile data\data.fept_demo.lmp ^
    -var T 600 ^
    -var comp 1.0 ^
    -log output\log_demo_600.lmp
if %errorlevel% equ 0 (echo [OK]) else (echo [FAIL] T=600K)

REM Generate CSV + plot from LAMMPS logs
echo.
echo [demo_report] Generating CSV and plot from raw logs...
%PYTHON% scripts\demo_report.py
if %errorlevel% equ 0 (echo [OK]) else (echo [WARN] demo_report.py — see output above)

echo.
echo ==================================================
echo DEMO COMPLETE!
echo ==================================================
echo.
echo Files created:
echo   output\log_demo_300.lmp    (LAMMPS log, T=300K)
echo   output\log_demo_600.lmp    (LAMMPS log, T=600K)
echo   output\demo_results.csv    (a(T) table)
echo   output\demo_a_vs_T.png     (graph)
echo.
endlocal
pause
exit /b 0

REM ============================================================
REM Подпрограмма поиска LAMMPS
REM Ищет строго Windows-native lmp.exe внутри папки проекта.
REM Никакого WSL. Никаких других операционок.
REM ============================================================
:find_lammps

REM 1. lmp.exe в bin/ рядом с проектом (портативная сборка)
if exist "%PROJ_DIR%\bin\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\bin\lmp.exe
    exit /b 0
)

REM 2. Переменная окружения LMP_EXE
if defined LMP_EXE (
    if exist "%LMP_EXE%" (
        exit /b 0
    )
)

REM 3. lmp.exe в PATH
where lmp.exe >nul 2>&1
if %errorlevel% equ 0 (
    set LMP_EXE=lmp.exe
    exit /b 0
)

REM 4. lmp (без .exe) в PATH
where lmp >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%P in ('where lmp') do (
        set LMP_EXE=%%P
        exit /b 0
    )
)

REM 5. Типовые пути установки LAMMPS на Windows
set LMP_PATHS="C:\Program Files\LAMMPS 64-bit\bin\lmp.exe" "C:\Program Files\LAMMPS 64-bit\lmp.exe" "C:\Program Files\LAMMPS\lmp.exe" "C:\Program Files (x86)\LAMMPS\lmp.exe" "C:\LAMMPS\lmp.exe"
for %%P in (%LMP_PATHS%) do (
    if exist %%P (
        set LMP_EXE=%%~P
        exit /b 0
    )
)

REM 6. lmp.exe рядом с проектом (на случай если в корне)
if exist "%PROJ_DIR%\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\lmp.exe
    exit /b 0
)

REM Не нашли
exit /b 1
