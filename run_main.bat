@echo off
chcp 65001 >nul

REM === run_main.bat — Полный прогон Fe-Pt (20 симуляций) ===
REM Windows-first. Не требует WSL.
REM Использует lmp.exe из LMP_EXE, PATH или типовых путей установки.
REM Авто-детект .venv (создаётся bootstrap.bat) с fallback на system python

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==================================================
echo Fe-Pt MD Thermal Expansion — FULL RUN
echo 5 compositions x 4 temperatures = 20 simulations
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
    echo   Вариант 2: Задайте LMP_EXE вручную, напр.:
    echo             set LMP_EXE=C:\Program Files\LAMMPS 64-bit\bin\lmp.exe
    echo   Вариант 3: Запустите LAMMPS через WSL (если lmp.exe нет):
    echo             set LMP_EXE=wsl.exe lmp
    pause
    exit /b 1
)
echo [OK] LAMMPS: %LMP_EXE%
echo.

REM Создаём output директорию
if not exist output mkdir output

REM Запускаем полный прогон через Python (он сам вызывает LAMMPS)
echo [OK] Starting full run via Python
echo   LAMMPS: %LMP_EXE%
echo   Python: %PYTHON%
echo Time estimate: 10-20 minutes
echo.

%PYTHON% scripts\run_all.py --full
if %errorlevel% neq 0 (
    echo [ERROR] Run failed
    pause
    exit /b 1
)

echo.
echo ==================================================
echo FULL RUN COMPLETE!
echo Results: output\all_results.csv
echo Plots:   output\a_vs_T_all.png
echo          output\a_vs_comp.png
echo ==================================================
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
set "LMP_PATHS="C:\Program Files\LAMMPS 64-bit\bin\lmp.exe" "C:\Program Files\LAMMPS 64-bit\lmp.exe" "C:\Program Files\LAMMPS\lmp.exe" "C:\Program Files (x86)\LAMMPS\lmp.exe" "C:\LAMMPS\lmp.exe""
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
