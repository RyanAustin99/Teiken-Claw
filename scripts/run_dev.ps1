# Teiken Claw Development Runner
# Purpose: Start application in development mode with hot reload
# Run: powershell -ExecutionPolicy Bypass -File scripts/run_dev.ps1

param(
    [switch]$ClearLogs = $false,
    [switch]$NoReload = $false,
    [string]$Port = "8000"
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "[DEV] $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "[OK]    $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Teiken Claw v1.0 - Development Mode" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

Write-Step "Project root: $ProjectRoot"

# ==============================================================================
# Step 1: Verify Virtual Environment
# ==============================================================================
Write-Step "Checking virtual environment..."

$VenvPath = Join-Path $ProjectRoot "venv"
$PythonVenv = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $PythonVenv)) {
    Write-Fail "Virtual environment not found at: $VenvPath"
    Write-Host "Run setup first: .\scripts\setup.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Success "Virtual environment ready"

# ==============================================================================
# Step 2: Clear Logs (Optional)
# ==============================================================================
if ($ClearLogs) {
    Write-Step "Clearing logs..."
    
    $LogsPath = Join-Path $ProjectRoot "logs"
    if (Test-Path $LogsPath) {
        Get-ChildItem $LogsPath -Filter "*.log" | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Success "Logs cleared"
    }
}

# ==============================================================================
# Step 3: Determine Run Mode
# ==============================================================================
Write-Step "Configuring run mode..."

$AppMain = Join-Path $ProjectRoot "app\main.py"

if (-not (Test-Path $AppMain)) {
    Write-Fail "app/main.py not found"
    exit 1
}

# Build command
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"

# Check for uvicorn availability and use it for better dev experience
$UvicornCheck = & $PythonExe -c "import uvicorn" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "       Using uvicorn for hot reload" -ForegroundColor Gray
    $Command = @($PythonExe, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", $Port)
} else {
    Write-Host "       Using direct Python execution" -ForegroundColor Gray
    $Command = @($PythonExe, $AppMain, "--port", $Port)
}

Write-Success "Starting in development mode on port $Port"

# ==============================================================================
# Step 4: Start Application
# ==============================================================================
Write-Host ""
Write-Host "-----------------------------------------------" -ForegroundColor Cyan
Write-Host "  Teiken Claw is starting..." -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host "-----------------------------------------------" -ForegroundColor Cyan
Write-Host ""

# Run the application
try {
    & $Command[0] $Command[1..($Command.Length-1)]
} catch {
    Write-Fail "Failed to start application: $_"
    exit 1
}
