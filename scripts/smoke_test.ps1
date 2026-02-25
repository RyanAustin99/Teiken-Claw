# Teiken Claw Smoke Test Script
# Purpose: Verify system health and connectivity
# Run: powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1

param(
    [switch]$SkipOllama = $false,
    [switch]$SkipApi = $false
)

$ErrorActionPreference = "Continue"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "[TEST] $Message" -ForegroundColor Cyan }
function Write-Info { param([string]$Message) Write-Host "[INFO]  $Message" -ForegroundColor Gray }
function Write-Success { param([string]$Message) Write-Host "[PASS]  $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }

$Global:TestsPassed = 0
$Global:TestsFailed = 0
$Global:TestsWarning = 0

function Test-Category {
    param([string]$Name)
    Write-Host ""
    Write-Host "--- $Name ---" -ForegroundColor Magenta
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Teiken Claw - Smoke Tests" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

# ==============================================================================
# Test 1: Python Installation
# ==============================================================================
Test-Category "Python Environment"

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if ($PythonCmd) {
    $Version = & $PythonCmd.Source --version 2>&1
    Write-Success "Python: $Version"
    $Global:TestsPassed++
} else {
    Write-Fail "Python: Not found"
    $Global:TestsFailed++
}

# ==============================================================================
# Test 2: Virtual Environment
# ==============================================================================
$VenvPath = Join-Path $ProjectRoot "venv"
$PythonVenv = Join-Path $VenvPath "Scripts\python.exe"

if (Test-Path $PythonVenv) {
    Write-Success "Virtual environment: Ready"
    $Global:TestsPassed++
} else {
    Write-Fail "Virtual environment: Not found"
    $Global:TestsFailed++
}

# ==============================================================================
# Test 3: Database Connectivity
# ==============================================================================
Test-Category "Database"

$DbPath = Join-Path $ProjectRoot "data\teiken_claw.db"
if (Test-Path $DbPath) {
    Write-Success "Database file: Exists"
    $Global:TestsPassed++
    
    # Check if we can read from it
    $DbSize = (Get-Item $DbPath).Length
    Write-Info "Database size: $([math]::Round($DbSize / 1KB, 2)) KB"
} else {
    Write-Warn "Database file: Not found (may need to run migrations)"
    $Global:TestsWarning++
}

# ==============================================================================
# Test 4: Ollama Connectivity
# ==============================================================================
if (-not $SkipOllama) {
    Test-Category "Ollama"
    
    $OllamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($OllamaCmd) {
        try {
            $OllamaList = & ollama list 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Ollama: Installed and running"
                $Global:TestsPassed++
            } else {
                Write-Warn "Ollama: Installed but not running"
                $Global:TestsWarning++
            }
        } catch {
            Write-Warn "Ollama: Installed but not responding"
            $Global:TestsWarning++
        }
    } else {
        Write-Warn "Ollama: Not installed"
        $Global:TestsWarning++
    }
}

# ==============================================================================
# Test 5: Required Python Packages
# ==============================================================================
Test-Category "Python Dependencies"

$RequiredPackages = @("fastapi", "sqlalchemy", "alembic", "pydantic", "httpx")
$PythonExe = $PythonVenv

if (-not $PythonExe) {
    $PythonExe = "python"
}

foreach ($Package in $RequiredPackages) {
    $Check = & $PythonExe -c "import $Package" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Package: $Package"
        $Global:TestsPassed++
    } else {
        Write-Fail "Package: $Package (not installed)"
        $Global:TestsFailed++
    }
}

# ==============================================================================
# Test 6: Application Imports
# ==============================================================================
Test-Category "Application Imports"

$RequiredImports = @(
    "app.main",
    "app.db.session",
    "app.agent.ollama_client",
    "app.skills.loader",
    "app.soul.loader"
)

foreach ($Import in $RequiredImports) {
    $Check = & $PythonExe -c "import $Import" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Import: $Import"
        $Global:TestsPassed++
    } else {
        Write-Fail "Import: $Import"
        $Global:TestsFailed++
    }
}

# ==============================================================================
# Test 7: Configuration Files
# ==============================================================================
Test-Category "Configuration"

$ConfigFiles = @(
    "requirements.txt",
    ".env.example",
    "alembic.ini"
)

foreach ($File in $ConfigFiles) {
    $FilePath = Join-Path $ProjectRoot $File
    if (Test-Path $FilePath) {
        Write-Success "Config: $File"
        $Global:TestsPassed++
    } else {
        Write-Fail "Config: $File (missing)"
        $Global:TestsFailed++
    }
}

# ==============================================================================
# Test 8: Soul Configuration
# ==============================================================================
Test-Category "Soul Configuration"

$SoulFiles = @(
    "soul\core.md",
    "soul\goals.yaml",
    "soul\guardrails.yaml"
)

foreach ($File in $SoulFiles) {
    $FilePath = Join-Path $ProjectRoot $File
    if (Test-Path $FilePath) {
        Write-Success "Soul: $File"
        $Global:TestsPassed++
    } else {
        Write-Warn "Soul: $File (missing)"
        $Global:TestsWarning++
    }
}

# ==============================================================================
# Test 9: Health Endpoint (if server running)
# ==============================================================================
if (-not $SkipApi) {
    Test-Category "API Health Check"
    
    try {
        $Response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($Response.StatusCode -eq 200) {
            Write-Success "Health endpoint: Responding"
            $Global:TestsPassed++
        } else {
            Write-Warn "Health endpoint: Unexpected status ($($Response.StatusCode))"
            $Global:TestsWarning++
        }
    } catch {
        Write-Warn "Health endpoint: Not reachable (server may not be running)"
        Write-Info "Start server with: .\scripts\run_dev.ps1"
        $Global:TestsWarning++
    }
}

# ==============================================================================
# Summary
# ==============================================================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Test Summary" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Passed:  $($Global:TestsPassed)" -ForegroundColor Green
Write-Host "Warning: $($Global:TestsWarning)" -ForegroundColor Yellow
Write-Host "Failed:  $($Global:TestsFailed)" -ForegroundColor Red
Write-Host ""

if ($Global:TestsFailed -eq 0) {
    Write-Success "All critical tests passed!"
    Write-Host ""
    exit 0
} else {
    Write-Fail "Some tests failed - please review"
    Write-Host ""
    exit 1
}
