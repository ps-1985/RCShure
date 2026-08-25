@echo off
REM ==============================================================================
REM RCShure - PyInstaller Standalone Windows Executable Build Script
REM Generates a zero-dependency portable .exe inside the dist\ directory
REM ==============================================================================

echo [1/3] Checking PyInstaller installation...
where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller not found. Installing PyInstaller...
    pip install pyinstaller
)

echo [2/3] Building standalone portable executable (RCShure.exe)...
pyinstaller --clean --onefile --noconsole --name "RCShure" axient_monitor.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==============================================================================
    echo [3/3] BUILD SUCCESSFUL!
    echo Standalone executable created at: dist\RCShure.exe
    echo.
    echo You can now copy RCShure.exe to any Windows PC or USB drive without Python.
    echo ==============================================================================
) else (
    echo.
    echo [!] Build failed with error code %ERRORLEVEL%
)

pause
