# Teiken Claw Setup Script v2.0 (Cinematic Installer)
# Run: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

[CmdletBinding()]
param(
    [switch]$VerboseLogs = $false,
    [switch]$NoAnsi = $false,
    [Alias("SkipSmokeTest")][switch]$SkipSmokeTests = $false,
    [switch]$CI = $false,
    [switch]$NoStart = $false,
    [switch]$NoUi = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($PSBoundParameters.ContainsKey("Verbose") -and $PSBoundParameters["Verbose"]) {
    $VerboseLogs = $true
}

$projectRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $projectRoot

$modulePath = Join-Path $PSScriptRoot "lib\TeikenInstaller.psm1"
if (-not (Test-Path $modulePath)) {
    Write-Host "Installer module not found: $modulePath" -ForegroundColor Red
    exit 1
}

Import-Module $modulePath -Force -DisableNameChecking

function Show-SetupBranding {
    param(
        [switch]$NoColor,
        [string]$ProjectRoot
    )

    $teal = if ($NoColor) { "Gray" } else { "Cyan" }
    $muted = if ($NoColor) { "Gray" } else { "DarkGray" }
    $useTrueTeal = $false
    if (-not $NoColor) {
        try {
            if ($Host -and $Host.UI -and $Host.UI.SupportsVirtualTerminal) {
                $useTrueTeal = $true
            }
        } catch {
        }
    }
    $tealStart = if ($useTrueTeal) { "$([char]27)[38;2;0;209;178m" } else { "" }
    $tealReset = if ($useTrueTeal) { "$([char]27)[0m" } else { "" }

    $bannerPath = Join-Path $ProjectRoot "teiken_claw\terminal\assets\banner_teiken_claw.txt"
    $underlayPath = Join-Path $ProjectRoot "scripts\assets\underlay_teiken_matrix.txt"
    $banner = @()
    if (Test-Path $bannerPath) {
        $banner = Get-Content -Path $bannerPath -Encoding UTF8
    }
    if (-not $banner -or $banner.Count -eq 0) {
        $banner = @("TEIKEN CLAW")
    }

    function Normalize-TeikenAnsiLine {
        param(
            [string]$Line
        )

        if ($null -eq $Line) { return "" }
        $esc = [char]27
        return [regex]::Replace(
            $Line,
            [regex]::Escape("$esc") + "\[[0-9;?]*[ -/]*[@-~]",
            {
                param($m)
                $value = $m.Value
                if ($value.EndsWith("m")) { return $value }
                return ""
            }
        )
    }

    Write-Host ""
    foreach ($line in $banner) {
        if ($useTrueTeal) {
            Write-Host ("{0}{1}{2}" -f $tealStart, $line, $tealReset)
        } else {
            Write-Host $line -ForegroundColor $teal
        }
    }
    Write-Host ""
    if (Test-Path $underlayPath) {
        $underlayRaw = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($underlayPath))
        $underlayLines = @($underlayRaw -split "`r?`n")
        $maxRows = [Math]::Min(10, $underlayLines.Count)
        for ($i = 0; $i -lt $maxRows; $i++) {
            $line = Normalize-TeikenAnsiLine -Line $underlayLines[$i]
            [Console]::WriteLine($line)
        }
        if ($useTrueTeal) {
            [Console]::WriteLine("$([char]27)[0m")
        }
        Write-Host ""
    }
    Write-Host "Installer mode: stable plain output (no animation)" -ForegroundColor $muted
    Write-Host ""
}

function New-StepResult {
    param(
        [int]$ExitCode = 0,
        [string]$Hint = "",
        [int]$DurationMs = 0,
        [string]$LogPath = "",
        [string[]]$TailLines = @(),
        [string[]]$ErrorTailLines = @(),
        [string]$StatusOverride = ""
    )

    return [pscustomobject]@{
        ExitCode = $ExitCode
        Hint = $Hint
        DurationMs = $DurationMs
        LogPath = $LogPath
        TailLines = $TailLines
        ErrorTailLines = $ErrorTailLines
        StatusOverride = $StatusOverride
    }
}

function Write-LocalStepLog {
    param(
        [pscustomobject]$State,
        [string]$StepId,
        [string[]]$Lines
    )

    $path = Join-Path $State.Paths.StepLogDir ("{0}_{1}.log" -f $StepId, (Get-Date -Format 'yyyyMMdd_HHmmss'))
    Set-Content -Path $path -Value ($Lines -join [Environment]::NewLine) -Encoding UTF8
    Add-Content -Path $State.Artifacts.MainLogPath -Value ("[{0}] [{1}] {2}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $StepId, ($Lines -join " | "))
    return $path
}

function Get-ShellExecutable {
    $current = (Get-Process -Id $PID -ErrorAction SilentlyContinue).Path
    if ($current -and (Test-Path $current)) { return $current }
    $pwsh = Join-Path $PSHOME "pwsh.exe"
    if (Test-Path $pwsh) { return $pwsh }
    $powershell = Join-Path $PSHOME "powershell.exe"
    if (Test-Path $powershell) { return $powershell }
    return "powershell.exe"
}

$state = Get-TeikenInstallerContext `
    -ProjectRoot $projectRoot `
    -VerboseLogs:$VerboseLogs `
    -NoAnsi:$NoAnsi `
    -SkipSmokeTests:$SkipSmokeTests `
    -CI:$CI `
    -NoStart:$NoStart `
    -NoUi:$NoUi

# Old cinematic installer menu is disabled; setup runs in stable plain mode.
$state.Mode = if ($CI) { "CI" } else { "PLAIN" }

if (-not $CI) {
    $noBrandColor = $NoAnsi -or $env:TEIKEN_NO_COLOR -eq "1"
    Show-SetupBranding -NoColor:$noBrandColor -ProjectRoot $projectRoot
}

$launchAction = "run_control_plane"
$script:setupUnhandled = $null

try {
    Start-TeikenUI -State $state

    $null = Invoke-TeikenStep -State $state -StepId "resolve_context" -Action {
        param($state, $step)

        $lines = @()
        $lines += "Project root: $($state.Paths.ProjectRoot)"
        $lines += "Mode: $($state.Mode)"

        $gitCmd = Get-Command git -ErrorAction SilentlyContinue
        if ($gitCmd) {
            try {
                $sha = (& $gitCmd.Source rev-parse --short HEAD 2>$null | Select-Object -First 1).Trim()
                if ($sha) {
                    $state.Runtime.GitSha = $sha
                    $state.Versions.Git = $sha
                    $lines += "Git sha: $sha"
                } else {
                    $lines += "Git sha unavailable"
                }
            } catch {
                $lines += "Git lookup failed: $($_.Exception.Message)"
            }
        } else {
            $lines += "Git not found"
        }

        $logPath = Write-LocalStepLog -State $state -StepId $step.Id -Lines $lines
        New-StepResult -ExitCode 0 -Hint ("Root: {0}" -f $state.Paths.ProjectRoot) -LogPath $logPath -TailLines $lines
    }

    $null = Invoke-TeikenStep -State $state -StepId "check_terminal" -Action {
        param($state, $step)

        $ansiLabel = if (-not $state.TerminalCaps.Ansi) { "OFF" } elseif ($state.TerminalCaps.TrueColor) { "TRUECOLOR" } else { "BASIC" }
        $lines = @(
            "PowerShell: $($state.TerminalCaps.PsVersion)",
            "Interactive: $($state.TerminalCaps.Interactive)",
            "ANSI: $ansiLabel",
            "Size: $($state.TerminalCaps.Width)x$($state.TerminalCaps.Height)"
        )

        $logPath = Write-LocalStepLog -State $state -StepId $step.Id -Lines $lines
        New-StepResult -ExitCode 0 -Hint ("ANSI {0}" -f $ansiLabel) -LogPath $logPath -TailLines $lines
    }

    $null = Invoke-TeikenStep -State $state -StepId "check_python" -Action {
        param($state, $step)

        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
        }

        if (-not $pythonCmd) {
            return New-StepResult -ExitCode 1 -Hint "Python not found (3.11+ required)" -TailLines @("Python command missing")
        }

        $state.Runtime.PythonCommand = $pythonCmd.Source
        $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $pythonCmd.Source -Arguments @("--version")

        $resultTail = @($result.TailLines)
        $versionLine = if ($resultTail.Count -gt 0) { $resultTail[-1] } else { "" }
        $match = [regex]::Match($versionLine, "Python\s+(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)")
        if (-not $match.Success) {
            $result.ExitCode = 1
            $result.Hint = "Unable to parse Python version"
            return $result
        }

        $major = [int]$match.Groups["major"].Value
        $minor = [int]$match.Groups["minor"].Value
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            $result.ExitCode = 1
            $result.Hint = "Python 3.11+ required ($versionLine)"
            return $result
        }

        $state.Versions.Python = $versionLine
        $result.Hint = "$versionLine OK"
        return $result
    }

    $null = Invoke-TeikenStep -State $state -StepId "check_ollama" -Action {
        param($state, $step)

        $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
        if (-not $ollamaCmd) {
            return New-StepResult -ExitCode 1 -Hint "Ollama not installed" -TailLines @("Install Ollama from https://ollama.com")
        }

        $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $ollamaCmd.Source -Arguments @("list")
        if ($result.ExitCode -eq 0) {
            $state.Versions.Ollama = "running"
            $result.Hint = "Ollama running"
        } else {
            $state.Versions.Ollama = "installed (not running)"
            $result.Hint = "Ollama installed but not running"
        }
        return $result
    }

    $null = Invoke-TeikenStep -State $state -StepId "venv" -Action {
        param($state, $step)

        if (-not $state.Runtime.PythonCommand) {
            return New-StepResult -ExitCode 1 -Hint "Python command unavailable"
        }

        $pythonVenv = Join-Path $state.Paths.VenvPath "Scripts\python.exe"
        $pipVenv = Join-Path $state.Paths.VenvPath "Scripts\pip.exe"
        if (Test-Path $pythonVenv) {
            $state.Runtime.PythonExe = $pythonVenv
            $state.Runtime.PipExe = $pipVenv
            $logPath = Write-LocalStepLog -State $state -StepId $step.Id -Lines @("Virtual environment already exists: $($state.Paths.VenvPath)")
            return New-StepResult -ExitCode 0 -Hint "venv ready" -LogPath $logPath
        }

        $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $state.Runtime.PythonCommand -Arguments @("-m", "venv", $state.Paths.VenvPath)
        if ($result.ExitCode -eq 0 -and (Test-Path $pythonVenv)) {
            $state.Runtime.PythonExe = $pythonVenv
            $state.Runtime.PipExe = $pipVenv
            $result.Hint = "venv ready"
        } else {
            $result.Hint = "Failed to create venv"
            $result.ExitCode = 1
        }
        return $result
    }

    $null = Invoke-TeikenStep -State $state -StepId "sync_dependencies" -Action {
        param($state, $step)

        if (-not $state.Runtime.PythonExe -or -not (Test-Path $state.Runtime.PythonExe)) {
            return New-StepResult -ExitCode 1 -Hint "venv python missing"
        }

        $quietArgs = @("--disable-pip-version-check", "--no-input", "--progress-bar", "off")
        if ($state.Mode -eq "CINEMATIC" -and -not $state.Ui.VerboseEnabled) {
            $quietArgs += "-q"
        }

        $upgrade = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $state.Runtime.PythonExe -Arguments (@("-m", "pip", "install", "--upgrade", "pip") + $quietArgs)
        if ($upgrade.ExitCode -ne 0) {
            $upgrade.Hint = "pip upgrade failed"
            return $upgrade
        }

        $requirements = Join-Path $state.Paths.ProjectRoot "requirements.txt"
        if (-not (Test-Path $requirements)) {
            return New-StepResult -ExitCode 1 -Hint "requirements.txt not found"
        }

        $sync = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $state.Runtime.PythonExe -Arguments (@("-m", "pip", "install", "-r", $requirements) + $quietArgs)
        if ($sync.ExitCode -ne 0) {
            $sync.Hint = "dependency sync failed"
            return $sync
        }

        $editable = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $state.Runtime.PythonExe -Arguments (@("-m", "pip", "install", "-e", ".") + $quietArgs)
        if ($editable.ExitCode -ne 0) {
            $editable.Hint = "editable install failed"
            return $editable
        }

        $pipInfo = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $state.Runtime.PythonExe -Arguments @("-m", "pip", "--version")
        $pipTail = @($pipInfo.TailLines)
        if ($pipInfo.ExitCode -eq 0 -and $pipTail.Count -gt 0) {
            $state.Versions.Pip = $pipTail[-1]
        }

        $editable.Hint = "pip sync complete"
        return $editable
    }

    $null = Invoke-TeikenStep -State $state -StepId "configure_environment" -Action {
        param($state, $step)

        $lines = @()
        $envPath = Join-Path $state.Paths.ProjectRoot ".env"
        $envExample = Join-Path $state.Paths.ProjectRoot ".env.example"

        if (-not (Test-Path $envPath) -and (Test-Path $envExample)) {
            Copy-Item -Path $envExample -Destination $envPath -Force
            $lines += "Created .env from .env.example"
        } elseif (Test-Path $envPath) {
            $lines += ".env already present"
        } else {
            $lines += "Warning: .env.example not found"
        }

        $configDir = Split-Path $state.Paths.ConfigPath -Parent
        New-Item -ItemType Directory -Force -Path $configDir | Out-Null
        if (-not (Test-Path $state.Paths.ConfigPath)) {
            '{"config_version":1}' | Set-Content -Path $state.Paths.ConfigPath -Encoding UTF8
            $lines += "Created user config: $($state.Paths.ConfigPath)"
        } else {
            $lines += "User config already present"
        }

        $logPath = Write-LocalStepLog -State $state -StepId $step.Id -Lines $lines
        New-StepResult -ExitCode 0 -Hint "config ready" -LogPath $logPath -TailLines $lines
    }

    $null = Invoke-TeikenStep -State $state -StepId "create_directories" -Action {
        param($state, $step)

        $dirs = @(
            "logs",
            "data\files",
            "data\exports",
            "data\backups",
            "data\embeddings",
            "logs\boot"
        )

        $lines = @()
        foreach ($rel in $dirs) {
            $target = Join-Path $state.Paths.ProjectRoot $rel
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            $lines += "Ensured: $target"
        }

        New-Item -ItemType Directory -Force -Path $state.Paths.LogsPath | Out-Null
        $lines += "Ensured: $($state.Paths.LogsPath)"

        $logPath = Write-LocalStepLog -State $state -StepId $step.Id -Lines $lines
        New-StepResult -ExitCode 0 -Hint "data dirs ready" -LogPath $logPath -TailLines $lines
    }

    $null = Invoke-TeikenStep -State $state -StepId "initialize_database" -Action {
        param($state, $step)

        $alembicIni = Join-Path $state.Paths.ProjectRoot "alembic.ini"
        if (-not (Test-Path $alembicIni)) {
            return New-StepResult -ExitCode 1 -Hint "alembic.ini missing"
        }

        $python = if ($state.Runtime.PythonExe -and (Test-Path $state.Runtime.PythonExe)) { $state.Runtime.PythonExe } else { $state.Runtime.PythonCommand }
        if (-not $python) {
            return New-StepResult -ExitCode 1 -Hint "python executable missing"
        }

        $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $python -Arguments @("-m", "alembic", "upgrade", "head")
        if ($result.ExitCode -eq 0) {
            $result.Hint = "db migrated"
        } else {
            $result.Hint = "db migration warning"
        }
        return $result
    }

    $null = Invoke-TeikenStep -State $state -StepId "smoke_tests" -Action {
        param($state, $step)

        if ($state.Flags.SkipSmokeTests) {
            return New-StepResult -ExitCode 0 -Hint "skipped (--SkipSmokeTests)" -StatusOverride "skipped"
        }

        $shellExe = Get-ShellExecutable
        $scriptPath = Join-Path $state.Paths.ProjectRoot "scripts\smoke_test.ps1"
        if (-not (Test-Path $scriptPath)) {
            return New-StepResult -ExitCode 1 -Hint "smoke_test.ps1 not found"
        }

        $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $shellExe -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath, "-SkipApi")

        $summary = $result.TailLines | Where-Object { $_ -match "Passed:|Failed:|Warnings:" } | Select-Object -Last 3
        if (@($summary).Count -gt 0) {
            $result.Hint = ($summary -join "; ")
        } else {
            $result.Hint = if ($result.ExitCode -eq 0) { "smoke tests complete" } else { "smoke tests warning" }
        }
        return $result
    }

    $null = Invoke-TeikenStep -State $state -StepId "boot_report" -Action {
        param($state, $step)

        $doctorExe = Join-Path $state.Paths.VenvPath "Scripts\teiken-claw.exe"
        $fallbackExe = Join-Path $state.Paths.VenvPath "Scripts\teiken.exe"

        if (Test-Path $doctorExe) {
            $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $doctorExe -Arguments @("doctor")
        } elseif (Test-Path $fallbackExe) {
            $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $fallbackExe -Arguments @("doctor")
        } elseif ($state.Runtime.PythonExe -and (Test-Path $state.Runtime.PythonExe)) {
            $result = Invoke-TeikenProcessQuiet -State $state -Step $step -FilePath $state.Runtime.PythonExe -Arguments @("-m", "app.control_plane.entrypoint", "doctor")
        } else {
            return New-StepResult -ExitCode 1 -Hint "doctor command unavailable"
        }

        $latestBoot = Join-Path $state.Paths.ProjectRoot "logs\boot_report.json"
        if (Test-Path $latestBoot) {
            $result.Hint = "boot report written"
        } else {
            $result.Hint = "doctor executed (no boot report found)"
        }
        return $result
    }

    $null = Invoke-TeikenStep -State $state -StepId "launchpad" -Action {
        param($state, $step)
        New-StepResult -ExitCode 0 -Hint "ready"
    }

    if (-not $state.Cancelled -and $state.ExitCode -eq 0 -and $state.Mode -eq "CINEMATIC") {
        $launchAction = Show-TeikenLaunchpad -State $state
        if (-not $NoStart -and $launchAction -eq "quit") {
            $launchAction = "run_control_plane"
        }
    }
}
catch {
    $script:setupUnhandled = $_
    if (-not $state.Cancelled) {
        $state.ExitCode = if ($state.ExitCode -eq 0) { 1 } else { $state.ExitCode }
        if (-not $state.Ui.FailureMessage) {
            $state.Ui.FailureMessage = $_.Exception.Message
            $state.Ui.FailureTail = @($_.Exception.ToString())
        }
    }
}
finally {
    if ($state.Cancelled -and $state.ExitCode -eq 0) {
        $state.ExitCode = 130
    }

    try {
        Write-TeikenSummaryArtifacts -State $state
    } catch {
    }

    Stop-TeikenUI -State $state
}

if ($state.Cancelled) {
    Write-Host ("Setup cancelled. Logs: {0}" -f $state.Artifacts.MainLogPath) -ForegroundColor Yellow
    Write-Host ("Summary: {0}" -f $state.Artifacts.SummaryJsonPath) -ForegroundColor Gray
    exit 130
}

if ($state.ExitCode -ne 0) {
    Write-Host ("Setup failed. Step logs: {0}" -f $state.Paths.StepLogDir) -ForegroundColor Red
    Write-Host ("Main log: {0}" -f $state.Artifacts.MainLogPath) -ForegroundColor Yellow
    Write-Host ("Summary: {0}" -f $state.Artifacts.SummaryJsonPath) -ForegroundColor Yellow
    if ($state.Artifacts.BundleZipPath) {
        Write-Host ("Bundle:  {0}" -f $state.Artifacts.BundleZipPath) -ForegroundColor Yellow
    }
    if ($script:setupUnhandled) {
        Write-Host ("Error: {0}" -f $script:setupUnhandled.Exception.Message) -ForegroundColor DarkYellow
    }
    exit $state.ExitCode
}

Write-Host ("Setup complete. Logs: {0}" -f $state.Artifacts.MainLogPath) -ForegroundColor Green
Write-Host ("Summary: {0}" -f $state.Artifacts.SummaryJsonPath) -ForegroundColor Gray

if (-not $NoStart) {
    switch ($launchAction) {
        "run_control_plane" {
            $pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
            if (Test-Path $pythonExe) {
                $args = @("-m", "app.control_plane.entrypoint", "run")
                if ($NoUi) {
                    $args += "--no-ui"
                }
                & $pythonExe @args
                exit $LASTEXITCODE
            }
        }
        "run_dev" {
            $runDev = Join-Path $projectRoot "scripts\run_dev.ps1"
            if (Test-Path $runDev) {
                & $runDev
                exit $LASTEXITCODE
            }
        }
        "doctor" {
            $doctorExe = Join-Path $projectRoot "venv\Scripts\teiken-claw.exe"
            if (Test-Path $doctorExe) {
                & $doctorExe doctor
                exit $LASTEXITCODE
            }

            $pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
            if (Test-Path $pythonExe) {
                & $pythonExe -m app.control_plane.entrypoint doctor
                exit $LASTEXITCODE
            }
        }
    }
} else {
    Write-Host "Runtime launch skipped (--NoStart)" -ForegroundColor Gray
}

exit 0
