@echo off
chcp 65001 >nul

REM === bootstrap.bat — Автоустановка + запуск Fe-Pt MD Demo ===
REM Двойной клик — и всё работает. Не требует ручных действий.
REM Создаёт .venv, ставит зависимости, запускает run_demo.bat

setlocal
cd /d "%~dp0"
set PROJ_DIR=%CD%

echo ==================================================
echo  Fe-Pt MD — Установка окружения и запуск
echo ==================================================
echo.

REM --- Шаг 1: Проверка Python ---
echo [1/5] Проверка Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python не найден!
    echo.
    echo Установите Python 3.8+ с python.org
    echo При установке ОБЯЗАТЕЛЬНО поставьте галочку "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%V in ('python --version 2^>^&1') do echo   %%V
echo [OK] Python найден
echo.

REM --- Шаг 2: Создание .venv ---
echo [2/5] Создание виртуального окружения...
if exist ".venv\Scripts\python.exe" (
    echo   .venv уже существует, пропускаем
) else (
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Не удалось создать .venv
        pause
        exit /b 1
    )
    echo   .venv создан
)
echo [OK] Виртуальное окружение готово
echo.

REM --- Шаг 3: Обновление pip внутри .venv ---
echo [3/5] Обновление pip...
call .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
echo [OK]
echo.

REM --- Шаг 4: Установка зависимостей ---
echo [4/5] Установка зависимостей (numpy, matplotlib)...
call .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Ошибка при установке зависимостей
    pause
    exit /b 1
)
echo [OK] Зависимости установлены
echo.

REM --- Шаг 5: Проверка WSL + LAMMPS ---
echo [5/5] Проверка LAMMPS в WSL...
C:\Windows\System32\wsl.exe which lmp >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] LAMMPS не найден в WSL.
    echo   Откройте терминал и выполните:
    echo     wsl --install
    echo     sudo apt update  ^&^& sudo apt install -y lammps
    echo.
    pause
    exit /b 1
)
echo [OK] LAMMPS найден
echo.

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
