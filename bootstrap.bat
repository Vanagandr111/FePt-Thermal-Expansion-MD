@echo off
chcp 65001 >nul

REM === bootstrap.bat — Автоустановка + запуск Fe-Pt MD Demo ===
REM Двойной клик — и всё работает. Не требует ручных действий.
REM Создаёт .venv, ставит зависимости, запускает run_demo.bat
REM
REM Требуется Python 3.11 или 3.12 (x64).
REM Python 3.13 и 3.14 НЕ поддерживаются — под них нет wheels для numpy.

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==================================================
echo  Fe-Pt MD — Установка окружения и запуск
echo ==================================================
echo.

REM ===================================================================
REM Шаг 1: Поиск подходящего Python (3.11 или 3.12)
REM ===================================================================
echo [1/5] Поиск Python...

REM Сначала пробуем Python Launcher: py -3.12, py -3.11
set PYTHON_CMD=

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.12 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3.12
        for /f "delims=" %%V in ('py -3.12 --version 2^>^&1') do echo   [py -3.12] %%V
        goto :found_python
    )
    py -3.11 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3.11
        for /f "delims=" %%V in ('py -3.11 --version 2^>^&1') do echo   [py -3.11] %%V
        goto :found_python
    )
)

REM Python Launcher не помог — пробуем python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V

    REM Проверяем мажорную и минорную версию
    for /f "tokens=1,2 delims=." %%A in ("%PY_VER%") do (
        set PY_MAJOR=%%A
        set PY_MINOR=%%B
    )

    if %PY_MAJOR% equ 3 (
        if %PY_MINOR% leq 12 (
            echo   [system] Python %PY_VER%
            goto :found_python
        )
    )

    REM Python 3.13/3.14 не подходит
    echo   [WARN] Системный Python %PY_VER% слишком новый.
    echo   numpy/matplotlib не имеют готовых wheels для этой версии.
    echo   Требуется Python 3.11 или 3.12.
    echo.
    goto :try_py_launcher_again
)

:try_py_launcher_again
REM Если python не подошёл, пробуем через launcher с fallback-сообщением
where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%V in ('py --version 2^>^&1') do (
        REM Проверяем, не 3.13/3.14 ли это
        echo   [py] %%V — не подходит. Нужна версия 3.11 или 3.12.
    )
)

echo [ERROR] Не найден Python 3.11 или 3.12!
echo.
echo Решение:
echo   1. Скачайте Python 3.12 с python.org:
echo      https://www.python.org/downloads/release/python-3129/
echo      (последняя 3.12.x стабильна)
echo.
echo   2. При установке ОБЯЗАТЕЛЬНО поставьте галочку
echo      "Add Python to PATH" и "py launcher".
echo.
echo   3. Если у вас Python 3.13+ — он НЕ подходит.
echo      Удалите его и поставьте 3.12.
echo.
pause
exit /b 1

:found_python
echo [OK] Python найден
echo.

REM ===================================================================
REM Шаг 2: Создание .venv
REM ===================================================================
echo [2/5] Создание виртуального окружения...
if exist ".venv\Scripts\python.exe" (
    echo   .venv уже существует, пропускаем
) else (
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Не удалось создать .venv
        pause
        exit /b 1
    )
    echo   .venv создан
)
echo [OK] Виртуальное окружение готово
echo.

REM ===================================================================
REM Шаг 3: Обновление pip
REM ===================================================================
echo [3/5] Обновление pip...
call .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo [WARN] Не удалось обновить pip, продолжаем...
) else (
    echo [OK]
)
echo.

REM ===================================================================
REM Шаг 4: Установка зависимостей (жёсткие версии)
REM ===================================================================
echo [4/5] Установка зависимостей (numpy==1.26.4, matplotlib==3.8.4)...
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Ошибка при установке зависимостей
    echo.
    echo Возможные причины:
    echo   - Нет интернета
    echo   - Нет прав на запись
    echo   - Проблемы с SSL-сертификатами (попробуйте:
    echo     .venv\Scripts\python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt)
    pause
    exit /b 1
)
echo [OK] Зависимости установлены
echo.

REM ===================================================================
REM Шаг 5: Поиск LAMMPS (Windows-first, затем WSL fallback)
REM ===================================================================
echo [5/5] Поиск LAMMPS...
call :find_lammps
if %errorlevel% neq 0 (
    echo [WARN] LAMMPS не найден.
    echo.
    echo   Проект будет работать, но запуск симуляций невозможен.
    echo   Установите LAMMPS для Windows с lammps.org:
    echo     https://packages.lammps.org/windows.html
    echo.
    echo   Или убедитесь, что lmp.exe доступен в PATH.
    echo   Либо задайте путь вручную: set LMP_EXE=C:\путь\к\lmp.exe
    echo.
    echo   Нажмите Enter, чтобы продолжить без LAMMPS (только установка Python).
    pause
    goto :boot_end
)
echo [OK] LAMMPS: %LMP_EXE%
echo.

:boot_end

echo ==================================================
echo  Всё готово! Запускаю DEMO...
echo ==================================================
echo.
echo  После демо результаты появятся в папке output\
echo  Для полного прогона (20 точек) откройте run_main.bat
echo.

REM --- Запуск demo ---
call "%~dp0run_demo.bat"

echo.
echo ==================================================
if %errorlevel% equ 0 (
    echo  DEMO ЗАВЕРШЁН УСПЕШНО!
    echo  Результаты: output\demo_results.csv
    echo  График:     output\demo_a_vs_T.png
) else (
    echo  DEMO завершён с ошибками (см. выше)
)
echo ==================================================
echo.
pause
endlocal

REM ============================================================
REM Подпрограмма поиска LAMMPS
REM ============================================================
:find_lammps

REM 1. Переменная окружения LMP_EXE
if defined LMP_EXE (
    if exist "%LMP_EXE%" (
        exit /b 0
    )
)

REM 2. lmp.exe в PATH
where lmp.exe >nul 2>&1
if %errorlevel% equ 0 (
    set LMP_EXE=lmp.exe
    exit /b 0
)

REM 3. lmp (без .exe) в PATH
where lmp >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%P in ('where lmp') do (
        set LMP_EXE=%%P
        exit /b 0
    )
)

REM 4. Типовые пути установки LAMMPS на Windows
set LMP_PATHS="C:\Program Files\LAMMPS 64-bit\bin\lmp.exe" "C:\Program Files\LAMMPS 64-bit\lmp.exe" "C:\Program Files\LAMMPS\lmp.exe" "C:\Program Files (x86)\LAMMPS\lmp.exe" "C:\LAMMPS\lmp.exe"
for %%P in (%LMP_PATHS%) do (
    if exist %%P (
        set LMP_EXE=%%~P
        exit /b 0
    )
)

REM 5. lmp.exe рядом с проектом
if exist "%PROJ_DIR%\lmp.exe" (
    set LMP_EXE=%PROJ_DIR%\lmp.exe
    exit /b 0
)

REM 6. Fallback: WSL
where wsl.exe >nul 2>&1
if %errorlevel% equ 0 (
    wsl.exe which lmp >nul 2>&1
    if %errorlevel% equ 0 (
        set LMP_EXE=wsl.exe lmp
        exit /b 0
    )
)

exit /b 1
