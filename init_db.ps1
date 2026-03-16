# Backupman Database Initialization Script
# This script resets the database by deleting the existing one and re-running the initialization logic.

$ErrorActionPreference = "Stop"

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

$dbDir = Join-Path $scriptDir "data"
$dbFile = Join-Path $dbDir "backupman.db"
$logDir = Join-Path $scriptDir "logs"

Write-Host "=== Backupman DB Generator ===" -ForegroundColor Cyan

# 1. Create directories if they don't exist
if (!(Test-Path $dbDir)) {
    Write-Host "Creating data directory..."
    New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
}

if (!(Test-Path $logDir)) {
    Write-Host "Creating logs directory..."
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 2. Remove existing DB files (including WAL/SHM)
Write-Host "Cleaning existing database files..." -ForegroundColor Yellow
$filesToDelete = Get-ChildItem -Path $dbDir -Filter "backupman.db*"
foreach ($file in $filesToDelete) {
    Write-Host "  Deleting: $($file.Name)"
    Remove-Item $file.FullName -Force
}

# 3. Initialize DB using the backend logic
Write-Host "Initializing database via Python..." -ForegroundColor Cyan
try {
    # We use -c to run the init_db function directly
    # Using python -u for unbuffered output
    python -c "import sys; sys.path.append('.'); from backend.db import init_db; init_db(); print('Python: Database initialized successfully.')"
} catch {
    Write-Error "Failed to initialize database via Python. Ensure Python is installed and backend/db.py is accessible."
    exit 1
}

# 4. Verify
if (Test-Path $dbFile) {
    $size = (Get-Item $dbFile).Length
    Write-Host "`nSuccess! Database created at: $dbFile ($size bytes)" -ForegroundColor Green
} else {
    Write-Host "`nError: Database file was not created." -ForegroundColor Red
    exit 1
}

Write-Host "`nPress any key to exit..."
$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
