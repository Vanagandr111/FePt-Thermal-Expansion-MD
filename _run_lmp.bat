@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist bin\lmp.exe (echo LMP NOT FOUND & exit /b 1)
bin\lmp.exe %*
