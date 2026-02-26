# Teiken Control Plane E2E Smoke
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/e2e_control_plane.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/e2e_control_plane.ps1 -SkipOllamaDependent

param(
    [string]$DataDir = ".e2e_teiken",
    [switch]$SkipOllamaDependent = $true
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host "[E2E] $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[OK]  $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "[FAIL] $Message" -ForegroundColor Red }

$ProjectRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $ProjectRoot

function Test-PythonCandidate {
    param([string]$Exe)
    if (-not $Exe) { return $false }
    if (-not (Test-Path $Exe) -and $Exe -notin @("python", "py")) { return $false }

    try {
        & $Exe -c "import typer, rich, textual; import app.control_plane.entrypoint" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-PythonExe {
    $venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
    if (Test-PythonCandidate -Exe $venvPython) {
        return $venvPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-PythonCandidate -Exe $pythonCmd.Source)) {
        return $pythonCmd.Source
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            & $pyCmd.Source -3 -c "import typer, rich, textual; import app.control_plane.entrypoint" *> $null
            if ($LASTEXITCODE -eq 0) {
                return "$($pyCmd.Source) -3"
            }
        } catch {
            # Continue to no-interpreter failure path
        }
    }

    return $null
}

$PythonExe = Resolve-PythonExe
if (-not $PythonExe) {
    Write-Fail "No Python interpreter with control-plane dependencies found. Run scripts/setup.ps1."
    exit 1
}

function Invoke-Teiken {
    param([string[]]$CommandArgs)
    $output = $null
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ($PythonExe -like "* -3") {
        $py = $PythonExe.Split(" ")[0]
        $output = & $py -3 -m app.control_plane.entrypoint --data-dir $DataDir @CommandArgs 2>&1
    } else {
        $output = & $PythonExe -m app.control_plane.entrypoint --data-dir $DataDir @CommandArgs 2>&1
    }
    $ErrorActionPreference = $previousPreference

    if ($output) {
        $output | ForEach-Object { Write-Host $_ }
    }

    if ($LASTEXITCODE -ne 0) {
        throw "teiken command failed: $($CommandArgs -join ' ')"
    }
    return $output
}

Write-Step "Using data dir: $DataDir"
Write-Step "Using Python: $PythonExe"
if (Test-Path $DataDir) {
    $timestamp = Get-Date -Format "yyyyMMddHHmmss"
    $DataDir = "$DataDir-$timestamp"
    Write-Step "Data dir exists, using isolated run dir: $DataDir"
}

try {
    Write-Step "Version"
    Invoke-Teiken -CommandArgs @("version") | Out-Null
    Write-Ok "version"

    Write-Step "Upgrade/bootstrap"
    Invoke-Teiken -CommandArgs @("upgrade") | Out-Null
    Write-Ok "upgrade"

    Write-Step "Status"
    Invoke-Teiken -CommandArgs @("status") | Out-Null
    Write-Ok "status"

    Write-Step "Config update"
    Invoke-Teiken -CommandArgs @("config", "--default-model", "llama3.2", "--dangerous-tools", "false") | Out-Null
    Write-Ok "config"

    if (-not $SkipOllamaDependent) {
        Write-Step "Models list"
        Invoke-Teiken -CommandArgs @("models", "list") | Out-Null
        Write-Ok "models list"
    } else {
        Write-Step "Skipping Ollama-dependent model checks"
    }

    Write-Step "Hatch agent"
    $hatchOutput = Invoke-Teiken -CommandArgs @("hatch", "--name", "e2e-agent", "--description", "e2e", "--no-chat")
    $agentId = $null
    foreach ($line in $hatchOutput) {
        if ($line -match "Hatched agent: .* \(([^)]+)\)") {
            $agentId = $Matches[1]
            break
        }
    }
    if (-not $agentId) {
        throw "Could not parse hatched agent id from hatch output."
    }
    Write-Ok "hatch"

    Write-Step "Agents list"
    Invoke-Teiken -CommandArgs @("agents", "list") | Out-Null
    Write-Ok "agents list"

    Write-Step "Restart and stop agent"
    Invoke-Teiken -CommandArgs @("agents", "restart", $agentId) | Out-Null
    Invoke-Teiken -CommandArgs @("agents", "stop", $agentId) | Out-Null
    Write-Ok "agent lifecycle"

    Write-Step "Doctor + exports"
    Invoke-Teiken -CommandArgs @("doctor", "--export") | Out-Null
    Invoke-Teiken -CommandArgs @("logs", "--audit", "--limit", "20") | Out-Null
    Write-Ok "doctor/logs"

    Write-Host ""
    Write-Host "E2E control-plane smoke passed." -ForegroundColor Green
    exit 0
}
catch {
    Write-Fail $_
    exit 1
}
