# Teiken Claw Database Reset Script
# Purpose: Safely reset the database with backup
# Run: powershell -ExecutionPolicy Bypass -File scripts/reset_db.ps1 -Force

param(
    [switch]$Force = $false,
    [switch]$NoBackup = $false
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "[RESET] $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "[OK]    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Teiken Claw - Database Reset" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

Write-Step "Project root: $ProjectRoot"

# ==============================================================================
# Safety Check
# ==============================================================================
if (-not $Force) {
    Write-Host ""
    Write-Warn "This will DELETE all data in the database!"
    Write-Host ""
    Write-Host "To proceed, run with -Force flag:" -ForegroundColor White
    Write-Host "  .\scripts\reset_db.ps1 -Force" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Host "CONFIRMATION: Proceeding with database reset" -ForegroundColor Yellow
Write-Host ""

# ==============================================================================
# Step 1: Verify Virtual Environment
# ==============================================================================
Write-Step "Checking virtual environment..."

$VenvPath = Join-Path $ProjectRoot "venv"
$PythonVenv = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $PythonVenv)) {
    Write-Fail "Virtual environment not found. Run setup.ps1 first."
    exit 1
}

Write-Success "Virtual environment ready"

# ==============================================================================
# Step 2: Backup Current Database
# ==============================================================================
if (-not $NoBackup) {
    Write-Step "Backing up current database..."
    
    $DbPath = Join-Path $ProjectRoot "data\teiken_claw.db"
    $BackupDir = Join-Path $ProjectRoot "data\backups"
    
    if (Test-Path $DbPath) {
        if (-not (Test-Path $BackupDir)) {
            New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
        }
        
        $Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
        $BackupPath = Join-Path $BackupDir "pre_reset_backup_$Timestamp.db"
        
        Copy-Item $DbPath $BackupPath -Force
        Write-Success "Database backed up to: pre_reset_backup_$Timestamp.db"
    } else {
        Write-Warn "No database found - skipping backup"
    }
}

# ==============================================================================
# Step 3: Drop All Tables
# ==============================================================================
Write-Step "Dropping all tables..."

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"

# Use Alembic to downgrade to base (drops all tables)
$AlembicResult = & $PythonExe -m alembic downgrade base 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Alembic downgrade had issues: $AlembicResult"
}

Write-Success "Tables dropped"

# ==============================================================================
# Step 4: Run Migrations
# ==============================================================================
Write-Step "Running migrations..."

$AlembicResult = & $PythonExe -m alembic upgrade head 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Alembic upgrade had issues: $AlembicResult"
}

Write-Success "Database reset complete"

# ==============================================================================
# Summary
# ==============================================================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "  Reset Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "The database has been reset to a clean state." -ForegroundColor White
Write-Host ""

if (-not $NoBackup) {
    Write-Host "A backup of your previous database was saved in data/backups/" -ForegroundColor Gray
}

Write-Host ""
