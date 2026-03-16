@echo off
REM build.bat - Build Backupman into a standalone .exe
REM Requirements: Python 3.11+, pip, pyinstaller installed

echo [Backupman Build]
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building executable...
pyinstaller backupman.spec --clean --noconfirm

echo.
echo Build complete. Output: dist\Backupman.exe
pause
