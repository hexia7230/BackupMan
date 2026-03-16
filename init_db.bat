@echo off
setlocal
cd /d "%~dp0"

echo === Backupman DB Generator (Batch Wrapper) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "init_db.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Error: Failed to initialize database.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Done.
pause
