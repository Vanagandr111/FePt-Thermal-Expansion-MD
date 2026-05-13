@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Очищаем внешние LAMMPS-переменные
set "LAMMPS_PLUGIN_PATH="
set "LAMMPS_POTENTIALS="

if not exist "bin\lmp.exe" (echo LMP NOT FOUND & exit /b 1)
bin\lmp.exe %*
