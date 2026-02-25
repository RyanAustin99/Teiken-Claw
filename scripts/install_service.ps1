# Teiken Claw Service Installation Script
# Purpose: Register Teiken Claw as Windows startup task
# Run: powershell -ExecutionPolicy Bypass -File scripts/install_service.ps1

param(
    [switch]$Uninstall = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "[SVC] $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "[OK]    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }

$TaskName = "TeikenClaw"

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Teiken Claw - Service Installation" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

Write-Step "Project root: $ProjectRoot"

# ==============================================================================
# Check for Administrator privileges
# ==============================================================================
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    Write-Warn "This script may require Administrator privileges for Task Scheduler"
    if (-not $Force) {
        Write-Host "Use -Force to skip this check" -ForegroundColor Gray
    }
}

# ==============================================================================
# Uninstall Mode
# ==============================================================================
if ($Uninstall) {
    Write-Step "Uninstalling Teiken Claw service..."
    
    $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    
    if ($ExistingTask) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Success "Service uninstalled"
    } else {
        Write-Warn "Service not found - nothing to uninstall"
    }
    
    Write-Host ""
    Write-Host "Uninstallation complete" -ForegroundColor Green
    exit 0
}

# ==============================================================================
# Install Mode
# ==============================================================================

# Step 1: Verify virtual environment exists
Write-Step "Checking virtual environment..."

$VenvPath = Join-Path $ProjectRoot "venv"
$PythonVenv = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $PythonVenv)) {
    Write-Fail "Virtual environment not found. Run setup.ps1 first."
    exit 1
}

Write-Success "Virtual environment ready"

# Step 2: Verify app main.py exists
Write-Step "Checking application..."

$AppMain = Join-Path $ProjectRoot "app\main.py"
if (-not (Test-Path $AppMain)) {
    Write-Fail "app/main.py not found"
    exit 1
}

Write-Success "Application ready"

# Step 3: Check for existing task
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Warn "Service already exists"
    
    if ($Force) {
        Write-Step "Removing existing service..."
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Success "Existing service removed"
    } else {
        Write-Host "Use -Force to replace existing service" -ForegroundColor Yellow
        exit 1
    }
}

# Step 4: Build the startup command
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"

# Use uvicorn if available
$UvicornCheck = & $PythonExe -c "import uvicorn" 2>&1
if ($LASTEXITCODE -eq 0) {
    $AppCommand = "$PythonExe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
} else {
    $AppCommand = "$PythonExe $AppMain --port 8000"
}

# Step 5: Create the scheduled task
Write-Step "Creating scheduled task..."

$WorkingDir = $ProjectRoot
$TaskDescription = "Teiken Claw - AI Agent System"

# Create action
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c cd `"$WorkingDir`" && $AppCommand" -WorkingDirectory $WorkingDir

# Create trigger - run at logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Create principal - run as current user
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Create settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false

# Restart on failure - 3 attempts with 5 minute delay
$Settings.RestartCount = 3
$Settings.RestartInterval = (New-TimeSpan -Minutes 5)

# Register the task
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description $TaskDescription -Force | Out-Null
    Write-Success "Service registered"
} catch {
    Write-Fail "Failed to register service: $_"
    exit 1
}

# Step 6: Validate the task
Write-Step "Validating task registration..."

$RegisteredTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($RegisteredTask) {
    Write-Success "Task validated: $TaskName"
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor White
    Write-Host "  Name:       $TaskName" -ForegroundColor Gray
    Write-Host "  Trigger:    At user logon" -ForegroundColor Gray
    Write-Host "  Restart:    3 attempts, 5 min delay" -ForegroundColor Gray
    Write-Host "  WorkingDir: $WorkingDir" -ForegroundColor Gray
} else {
    Write-Fail "Task validation failed"
    exit 1
}

# ==============================================================================
# Summary
# ==============================================================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Teiken Claw has been registered as a Windows startup task." -ForegroundColor White
Write-Host ""
Write-Host "Commands:" -ForegroundColor White
Write-Host "  Start service:   Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  Stop service:    Stop-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  View status:     Get-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  Uninstall:       .\scripts\install_service.ps1 -Uninstall" -ForegroundColor Gray
Write-Host ""
