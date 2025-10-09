@echo off
setlocal enabledelayedexpansion

:: Unpackr Installation Script (Batch Version)
:: Simpler alternative to install.ps1

title Unpackr Installer

echo.
echo ===============================================
echo           UNPACKR INSTALLER
echo      Your Digital Declutterer Setup
echo ===============================================
echo.

:: Check if running from correct directory
if not exist "unpackr.py" (
    echo ERROR: unpackr.py not found!
    echo Please run this script from the Unpackr directory.
    pause
    exit /b 1
)

if not exist "unpackr.bat" (
    echo ERROR: unpackr.bat not found!
    echo Please run this script from the Unpackr directory.
    pause
    exit /b 1
)

:: Install Python dependencies
echo [1/3] Installing Python dependencies...
python -m pip install -r requirements.txt >nul 2>&1
if !errorlevel! equ 0 (
    echo ✓ Dependencies installed successfully
) else (
    echo ⚠ Warning: Could not install dependencies
    echo   Make sure Python is installed and in PATH
)

echo.
echo Choose installation method:
echo.
echo 1. Copy to System32 ^(requires admin^)
echo 2. Add to user PATH ^(recommended^)
echo 3. Exit
echo.
set /p choice="Enter choice (1-3): "

if "%choice%"=="1" goto install_system32
if "%choice%"=="2" goto install_userpath
if "%choice%"=="3" goto exit_script
echo Invalid choice. Please enter 1, 2, or 3.
goto menu

:install_system32
echo.
echo [2/3] Installing to System32...
copy "unpackr.bat" "C:\Windows\System32\" >nul 2>&1
if !errorlevel! equ 0 (
    echo ✓ Successfully installed to C:\Windows\System32\
    goto test_installation
) else (
    echo ✗ Failed to install to System32
    echo   Try running as Administrator
    pause
    exit /b 1
)

:install_userpath
echo.
echo [2/3] Adding to user PATH...
set "CURRENT_DIR=%~dp0"
set "CURRENT_DIR=!CURRENT_DIR:~0,-1!"

:: Add to user PATH using PowerShell
powershell -Command "$currentPath = [Environment]::GetEnvironmentVariable('PATH', 'User'); if ($currentPath -notlike '*%CURRENT_DIR%*') { $newPath = if ($currentPath) { \"$currentPath;%CURRENT_DIR%\" } else { \"%CURRENT_DIR%\" }; [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User'); Write-Host '✓ Added to user PATH' } else { Write-Host '✓ Already in PATH' }"

:test_installation
echo.
echo [3/3] Testing installation...
echo.
echo ✓ Installation completed!
echo.
echo NEXT STEPS:
echo   1. Restart your terminal/command prompt
echo   2. Test with: unpackr --help
echo   3. Run: unpackr --source "C:\Downloads" --destination "D:\Videos"
echo.
echo DOCUMENTATION:
echo   • README.md - Full documentation  
echo   • INSTALL.md - Detailed install guide
echo.
pause
exit /b 0

:exit_script
echo Installation cancelled.
pause
exit /b 0