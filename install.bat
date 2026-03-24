@echo off
:: Auto-elevate to Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo ============================================================
echo   YOU SAID YOU'D QUIT -- Installer
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo  Please install Python 3.8 or later from:
    echo  https://www.python.org/downloads/
    echo.
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python found: %PYVER%

:: Install cryptography
echo.
echo  Installing required dependency (cryptography)...
python -m pip install cryptography --quiet
if %errorLevel% neq 0 (
    echo [ERROR] Failed to install cryptography.
    echo  Try running: python -m pip install cryptography
    pause
    exit /b 1
)
echo  Dependency installed successfully.

echo.
echo ============================================================
echo   Setup complete!
echo ============================================================
echo.
echo  To activate the blocker:
echo    Right-click site_blocker.bat and choose "Run as administrator"
echo.
pause
