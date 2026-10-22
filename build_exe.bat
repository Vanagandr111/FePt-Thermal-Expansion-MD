@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ================================================================
echo  Fe-Pt MD - GUI exe builder (PyInstaller, one-file)
echo  Output: dist\FePt-GUI.exe
echo ================================================================
echo.

set TOOLS=buildtools-venv\Scripts\python.exe
if not exist "%TOOLS%" (
    echo  [1/4] Creating buildtools venv ...
    python -m venv buildtools-venv || (
        echo   ERROR: cannot create buildtools-venv & pause & exit /b 1 )
    "%TOOLS%" -m pip install -q --upgrade pip
    "%TOOLS%" -m pip install -q pyinstaller
) else (
    echo  [1/4] buildtools venv exists
)

echo  [2/4] Building dist\FePt-GUI.exe (one-file; torch/mace excluded on
echo        purpose - the exe drives an external engine Python, so the
echo        bundle stays small and clean) ...
"%TOOLS%" -m PyInstaller FePt-GUI.spec --noconfirm --clean
if errorlevel 1 (
    echo   ERROR: PyInstaller failed, see the output above
    pause
    exit /b 1
)

if defined FEPT_SKIP_SMOKE goto :smoke_skipped
echo  [3/4] Smoke test: launching the exe and hitting /api/metrics ...
start "" /b dist\FePt-GUI.exe
set TRIES=0
:waitloop
timeout /t 2 /nobreak >nul
curl -s -m 3 http://127.0.0.1:8321/api/metrics >nul 2>nul
if not errorlevel 1 goto :smokeok
set /a TRIES+=1
if %TRIES% LSS 25 goto :waitloop
echo   ERROR: exe did not answer on :8321 within 50 s
goto :fail

:smokeok
echo   [ok] GUI answers on http://127.0.0.1:8321
for %%F in (dist\FePt-GUI.exe) do echo   size: %%~zF bytes

echo  [4/4] Stopping the smoke-test instance ...
curl -s -m 3 -X POST http://127.0.0.1:8321/api/stop >nul 2>nul
for /f "tokens=2" %%P in ('tasklist /fi "imagename eq FePt-GUI.exe" ^| findstr /i FePt') do taskkill /f /pid %%P >nul 2>nul

echo.
echo ================================================================
echo  DONE. dist\FePt-GUI.exe is ready for the release.
echo  Next: gh release create vX.Y.Z dist\FePt-GUI.exe
echo ================================================================
pause
exit /b 0

:smoke_skipped
echo   [skip] smoke test + pause skipped (FEPT_SKIP_SMOKE=1)
echo   DONE. dist\FePt-GUI.exe is ready for the release.
exit /b 0

:fail
for /f "tokens=2" %%P in ('tasklist /fi "imagename eq FePt-GUI.exe" ^| findstr /i FePt') do taskkill /f /pid %%P >nul 2>nul
pause
exit /b 1
