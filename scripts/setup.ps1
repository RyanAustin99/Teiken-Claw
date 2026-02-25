# Teiken Claw Setup Script
# Purpose: Environment setup for Windows
# Run: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

param(
    [switch]$SkipOllama = $false,
    [switch]$SkipSmokeTest = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "[SETUP] $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "[OK]    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN]  $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "[FAIL]  $Message" -ForegroundColor Red }
function Write-Info { param([string]$Message) Write-Host "       $Message" -ForegroundColor Gray }

# Banner
Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Teiken Claw v1.0 - Environment Setup" -ForegroundColor Magenta
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}
Set-Location $ProjectRoot

Write-Step "Project root: $ProjectRoot"

# ==============================================================================
# Step 1: Verify Python Installation
# ==============================================================================
Write-Step "Checking Python installation..."

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    Write-Fail "Python not found. Please install Python 3.11 or later from https://python.org"
    exit 1
}

$PythonVersion = & $PythonCmd.Source --version 2>&1
Write-Info "Found: $PythonVersion"

$VersionMatch = $PythonVersion -match "Python (\d+)\.(\d+)"
if (-not $VersionMatch) {
    Write-Fail "Could not determine Python version"
    exit 1
}

$Major = [int]$Matches[1]
$Minor = [int]$Matches[2]

if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 11)) {
    Write-Fail "Python 3.11+ required. Found: $PythonVersion"
    exit 1
}

Write-Success "Python version OK ($PythonVersion)"

# ==============================================================================
# Step 2: Verify Ollama (Optional)
# ==============================================================================
if (-not $SkipOllama) {
    Write-Step "Checking Ollama installation..."
    
    $OllamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $OllamaCmd) {
        Write-Warn "Ollama not found. AI features will be disabled."
        Write-Info "Install from: https://ollama.ai"
    } else {
        Write-Info "Found Ollama: $($OllamaCmd.Source)"
        
        # Check if Ollama service is running
        try {
            $OllamaList = & ollama list 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Ollama is running"
            } else {
                Write-Warn "Ollama is installed but not running. Start with: ollama serve"
            }
        } catch {
            Write-Warn "Ollama is installed but not running. Start with: ollama serve"
        }
    }
}

# ==============================================================================
# Step 3: Create Virtual Environment
# ==============================================================================
Write-Step "Setting up virtual environment..."

$VenvPath = Join-Path $ProjectRoot "venv"
if (Test-Path $VenvPath) {
    Write-Info "Virtual environment already exists"
} else {
    & python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to create virtual environment"
        exit 1
    }
    Write-Success "Virtual environment created"
}

$PythonVenv = Join-Path $VenvPath "Scripts\python.exe"
$PipVenv = Join-Path $VenvPath "Scripts\pip.exe"

Write-Success "Virtual environment ready"

# ==============================================================================
# Step 4: Install Dependencies
# ==============================================================================
Write-Step "Installing dependencies..."

$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
if (-not (Test-Path $RequirementsFile)) {
    Write-Fail "requirements.txt not found"
    exit 1
}

# pip 25.3+ requires using 'python -m pip' instead of pip.exe for self-upgrade
$PythonVenvExecutable = Join-Path $VenvPath "Scripts\python.exe"
& $PythonVenvExecutable -m pip install --upgrade pip 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to upgrade pip"
    exit 1
}

& $PipVenv install -r $RequirementsFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to install dependencies"
    exit 1
}

Write-Success "Dependencies installed"

# ==============================================================================
# Step 5: Create .env File
# ==============================================================================
Write-Step "Configuring environment..."

$EnvExample = Join-Path $ProjectRoot ".env.example"
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $EnvExample)) {
    Write-Warn ".env.example not found - skipping .env creation"
} elseif (Test-Path $EnvFile) {
    # Check if .env has old comma-separated list format (invalid for pydantic-settings)
    $EnvContent = Get-Content $EnvFile -Raw -ErrorAction SilentlyContinue
    $HasOldExecFormat = $EnvContent -match "EXEC_ALLOWLIST=[a-z]"
    $HasOldWebFormat = $EnvContent -match "WEB_ALLOWED_DOMAINS=[a-z]"
    
    if ($HasOldExecFormat -or $HasOldWebFormat) {
        Write-Warn ".env has old format (comma-separated lists) - recreating from .env.example"
        Remove-Item $EnvFile -Force
        Copy-Item $EnvExample $EnvFile
        Write-Success "Recreated .env with correct JSON array format"
    } else {
        Write-Info ".env already exists - skipping"
    }
} else {
    Copy-Item $EnvExample $EnvFile
    Write-Success "Created .env from .env.example"
    Write-Warn "Please edit .env and configure your settings"
}

# ==============================================================================
# Step 6: Create Data Directories
# ==============================================================================
Write-Step "Creating data directories..."

$DataDirs = @(
    "logs",
    "data\files",
    "data\exports",
    "data\backups",
    "data\embeddings"
)

foreach ($Dir in $DataDirs) {
    $FullPath = Join-Path $ProjectRoot $Dir
    if (-not (Test-Path $FullPath)) {
        New-Item -ItemType Directory -Path $FullPath -Force | Out-Null
        Write-Info "Created: $Dir"
    } else {
        Write-Info "Exists: $Dir"
    }
}

Write-Success "Data directories ready"

# ==============================================================================
# Step 7: Initialize Database
# ==============================================================================
Write-Step "Initializing database..."

$AlembicIni = Join-Path $ProjectRoot "alembic.ini"
if (-not (Test-Path $AlembicIni)) {
    Write-Warn "alembic.ini not found - skipping database initialization"
} else {
    # Verify .env exists before running alembic
    $EnvFile = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $EnvFile)) {
        Write-Warn ".env not found - creating from .env.example"
        $EnvExample = Join-Path $ProjectRoot ".env.example"
        if (Test-Path $EnvExample) {
            Copy-Item $EnvExample $EnvFile
        }
    }
    
    # Run alembic - simpler approach, just run and check result
    try {
        # Run alembic directly, ignore stderr errors from logging
        $null = & $PythonVenv -m alembic upgrade head 2>$null
        $AlembicExitCode = $LASTEXITCODE
        
        if ($AlembicExitCode -eq 0) {
            Write-Success "Database initialized"
        } else {
            Write-Warn "Database migration had issues (exit code: $AlembicExitCode)"
            Write-Warn "This may be normal for first run or if tables already exist"
        }
    } catch {
        Write-Warn "Alembic error: $_"
    }
}

# ==============================================================================
# Step 8: Run Smoke Tests
# ==============================================================================
if (-not $SkipSmokeTest) {
    Write-Step "Running smoke tests..."
    
    $SmokeTestScript = Join-Path $ProjectRoot "scripts\smoke_test.ps1"
    if (Test-Path $SmokeTestScript) {
        & $SmokeTestScript
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Some smoke tests failed - please review"
        }
    } else {
        Write-Info "Smoke test script not found - skipping"
    }
}

# ==============================================================================
# Next Steps
# ==============================================================================
Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Edit .env and configure your settings" -ForegroundColor Gray
Write-Host "  2. Run: .\scripts\run_dev.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "Optional:" -ForegroundColor White
Write-Host "  - Install as Windows service: .\scripts\install_service.ps1" -ForegroundColor Gray
Write-Host "  - Run smoke tests: .\scripts\smoke_test.ps1" -ForegroundColor Gray
Write-Host ""
