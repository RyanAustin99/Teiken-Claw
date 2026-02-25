# Teiken Claw Backup Script
# Purpose: Backup database, configs, and critical data
# Run: powershell -ExecutionPolicy Bypass -File scripts/backup.ps1

param(
    [int]$KeepBackups = 10,
    [switch]$NoClean = $false
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "[BACKUP] $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "[OK]    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Teiken Claw - Backup Script" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

Write-Step "Project root: $ProjectRoot"

# ==============================================================================
# Configuration
# ==============================================================================
$BackupDir = Join-Path $ProjectRoot "data\backups"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$BackupName = "teiken_claw_backup_$Timestamp"
$BackupPath = Join-Path $BackupDir $BackupName

# Files to backup
$DbPath = Join-Path $ProjectRoot "data\teiken_claw.db"
$SoulDir = Join-Path $ProjectRoot "soul"
$EnvFile = Join-Path $ProjectRoot ".env"

# ==============================================================================
# Step 1: Create Backup Directory
# ==============================================================================
Write-Step "Creating backup directory..."

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
Write-Success "Backup directory: $BackupName"

# ==============================================================================
# Step 2: Backup Database
# ==============================================================================
Write-Step "Backing up database..."

if (Test-Path $DbPath) {
    $DbBackupPath = Join-Path $BackupPath "teiken_claw.db"
    Copy-Item $DbPath $DbBackupPath -Force
    $DbSize = (Get-Item $DbBackupPath).Length
    Write-Success "Database backed up ($([math]::Round($DbSize / 1MB, 2)) MB)"
} else {
    Write-Warn "Database not found at $DbPath - skipping"
}

# ==============================================================================
# Step 3: Backup Soul Configuration
# ==============================================================================
Write-Step "Backing up soul configuration..."

if (Test-Path $SoulDir) {
    $SoulBackupPath = Join-Path $BackupPath "soul"
    Copy-Item -Recurse $SoulDir $SoulBackupPath -Force
    Write-Success "Soul config backed up"
} else {
    Write-Warn "Soul directory not found - skipping"
}

# ==============================================================================
# Step 4: Backup Environment File
# ==============================================================================
Write-Step "Backing up environment configuration..."

if (Test-Path $EnvFile) {
    $EnvBackupPath = Join-Path $BackupPath ".env"
    Copy-Item $EnvFile $EnvBackupPath -Force
    Write-Success "Environment config backed up"
} else {
    Write-Warn ".env file not found - skipping"
}

# ==============================================================================
# Step 5: Backup Skills Definitions
# ==============================================================================
Write-Step "Backing up skills definitions..."

$SkillsDir = Join-Path $ProjectRoot "app\skills\definitions"
if (Test-Path $SkillsDir) {
    $SkillsBackupPath = Join-Path $BackupPath "skills"
    Copy-Item -Recurse $SkillsDir $SkillsBackupPath -Force
    Write-Success "Skills definitions backed up"
} else {
    Write-Warn "Skills directory not found - skipping"
}

# ==============================================================================
# Step 6: Create Archive
# ==============================================================================
Write-Step "Creating archive..."

$ArchivePath = "$BackupPath.zip"
if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}

Compress-Archive -Path $BackupPath -DestinationPath $ArchivePath -Force
$ArchiveSize = (Get-Item $ArchivePath).Length
Write-Success "Archive created ($([math]::Round($ArchiveSize / 1MB, 2)) MB): $BackupName.zip"

# ==============================================================================
# Step 7: Clean Old Backups
# ==============================================================================
if (-not $NoClean) {
    Write-Step "Cleaning old backups (keeping last $KeepBackups)..."
    
    $ExistingBackups = Get-ChildItem $BackupDir -Filter "teiken_claw_backup_*.zip" | Sort-Object LastWriteTime -Descending
    
    if ($ExistingBackups.Count -gt $KeepBackups) {
        $ToDelete = $ExistingBackups | Select-Object -Skip $KeepBackups
        foreach ($Backup in $ToDelete) {
            Remove-Item $Backup.FullName -Force
            Write-Info "Removed: $($Backup.Name)"
        }
        Write-Success "Cleaned up $($ToDelete.Count) old backup(s)"
    } else {
        Write-Info "No cleanup needed - $($ExistingBackups.Count) backup(s) exist"
    }
}

# ==============================================================================
# Summary
# ==============================================================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "  Backup Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backup location: $ArchivePath" -ForegroundColor White
Write-Host ""

# List what's in the backup
Write-Host "Backup contents:" -ForegroundColor White
Get-ChildItem $BackupPath -Recurse | ForEach-Object {
    $RelPath = $_.FullName.Replace($BackupPath, "").TrimStart("\")
    Write-Host "  - $RelPath" -ForegroundColor Gray
}

Write-Host ""
