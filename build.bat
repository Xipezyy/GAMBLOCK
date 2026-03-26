@echo off
echo.
echo ============================================================
echo   GAMBLOCK — Build Script
echo ============================================================
echo.

:: Check PyInstaller
pyinstaller --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller --quiet
)

echo [1/3] Building GAMBLOCK.exe ...
pyinstaller ^
  --onefile ^
  --uac-admin ^
  --noconsole ^
  --name GAMBLOCK ^
  --icon installer\gamblock.ico ^
  --distpath dist ^
  --workpath build\work ^
  --specpath build ^
  --noconfirm ^
  --collect-all customtkinter ^
  site_blocker.py

echo.
echo [2/3] Building GAMBLOCK_Server.exe ...
pyinstaller ^
  --onefile ^
  --uac-admin ^
  --name GAMBLOCK_Server ^
  --icon installer\gamblock.ico ^
  --distpath dist ^
  --workpath build\work ^
  --specpath build ^
  --noconfirm ^
  blocker_server.py

echo.
echo [3/3] Done. Executables are in the dist\ folder.
echo.
echo Next step: open installer\gamblock.iss in Inno Setup and click Compile.
echo Download Inno Setup free at: https://jrsoftware.org/isdl.php
echo.
pause
