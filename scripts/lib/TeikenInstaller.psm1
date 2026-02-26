Set-StrictMode -Version Latest

$script:ESC = [char]27
$script:CSI = "$script:ESC["
$script:TeikenVtEnabled = $false
$script:TeikenUiStarted = $false
$script:TeikenCancelHandler = $null
$script:TeikenPrevCtrlCAsInput = $false
$script:TeikenCurrentState = $null

$brandingScript = Join-Path $PSScriptRoot '..\_branding.ps1'
if (Test-Path $brandingScript) {
    . $brandingScript
}

function Strip-Ansi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    return [regex]::Replace($Text, "\x1b\[[0-9;?]*[ -/]*[@-~]", '')
}

function Enable-VirtualTerminal {
    try {
        $isWindowsHost = ($env:OS -like '*Windows*')
        if (-not $isWindowsHost) {
            $script:TeikenVtEnabled = $true
            return $true
        }

        Add-Type -Namespace TeikenInstaller -Name Win32 -MemberDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {
  public const int STD_OUTPUT_HANDLE = -11;
  public const uint ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004;
  public const uint DISABLE_NEWLINE_AUTO_RETURN = 0x0008;
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern IntPtr GetStdHandle(int nStdHandle);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
}
"@ -ErrorAction SilentlyContinue

        $h = [TeikenInstaller.Win32]::GetStdHandle([TeikenInstaller.Win32]::STD_OUTPUT_HANDLE)
        if ($h -eq [IntPtr]::Zero) { return $false }

        $mode = 0
        if (-not [TeikenInstaller.Win32]::GetConsoleMode($h, [ref]$mode)) { return $false }

        $newMode = $mode -bor [TeikenInstaller.Win32]::ENABLE_VIRTUAL_TERMINAL_PROCESSING
        $newMode = $newMode -bor [TeikenInstaller.Win32]::DISABLE_NEWLINE_AUTO_RETURN
        $ok = [TeikenInstaller.Win32]::SetConsoleMode($h, $newMode)
        if ($ok) {
            $script:TeikenVtEnabled = $true
            return $true
        }
    } catch {
    }

    return $false
}

function Initialize-TeikenConsole {
    try {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        $global:OutputEncoding = [Console]::OutputEncoding
    } catch {
    }

    [void](Enable-VirtualTerminal)
}

function Get-TeikenAnsiSupport {
    param(
        [switch]$NoAnsi,
        [switch]$CI
    )

    if ($NoAnsi -or $CI -or $env:TEIKEN_NO_COLOR -eq '1') {
        return $false
    }

    try {
        if ([Console]::IsOutputRedirected) { return $false }
    } catch {
        return $false
    }

    if ($env:WT_SESSION) { return $true }
    if ($script:TeikenVtEnabled) { return $true }

    try {
        if ($Host -and $Host.UI -and $Host.UI.SupportsVirtualTerminal) {
            return $true
        }
    } catch {
    }

    if ($env:TERM -and $env:TERM -ne 'dumb') { return $true }
    return $false
}

function Test-TeikenAnsiSupport {
    param(
        [switch]$NoAnsi,
        [switch]$CI
    )

    return Get-TeikenAnsiSupport -NoAnsi:$NoAnsi -CI:$CI
}
function Test-TeikenTrueColorSupport {
    param(
        [bool]$AnsiEnabled
    )

    if (-not $AnsiEnabled) { return $false }
    if ($env:COLORTERM -match 'truecolor|24bit') { return $true }
    if ($env:WT_SESSION) { return $true }
    return $false
}

function Get-TeikenVisibleLength {
    param(
        [string]$Text
    )

    if (-not $Text) { return 0 }
    $plain = Strip-Ansi -Text $Text
    return $plain.Length
}

function Get-TeikenMiddleEllipsis {
    param(
        [string]$Text,
        [int]$MaxLength = 44
    )

    if (-not $Text) { return '' }
    if ($Text.Length -le $MaxLength) { return $Text }
    if ($MaxLength -lt 7) { return $Text.Substring(0, [Math]::Max(0, $MaxLength)) }

    $left = [Math]::Floor(($MaxLength - 1) / 2)
    $right = $MaxLength - 1 - $left
    return '{0}…{1}' -f $Text.Substring(0, $left), $Text.Substring($Text.Length - $right)
}

function Get-TeikenTheme {
    param(
        [pscustomobject]$State
    )

    if (-not $State.TerminalCaps.Ansi) {
        return [ordered]@{
            Reset = ''
            Bold = ''
            Dim = ''
            Teal = ''
            TealBright = ''
            TealInvert = ''
            Orange = ''
            OrangeBright = ''
            OrangeInvert = ''
            Muted = ''
            Success = ''
            Warn = ''
            Error = ''
            Border = ''
            BorderError = ''
            Status = ''
        }
    }

    $reset = "${script:CSI}0m"
    $bold = "${script:CSI}1m"
    $dim = "${script:CSI}2m"

    if ($State.TerminalCaps.TrueColor) {
        return [ordered]@{
            Reset = $reset
            Bold = $bold
            Dim = $dim
            Teal = "${script:CSI}38;2;0;209;178m"
            TealBright = "${script:CSI}38;2;36;235;208m"
            TealInvert = "${script:CSI}97;48;2;0;209;178m"
            Orange = "${script:CSI}38;2;255;122;24m"
            OrangeBright = "${script:CSI}38;2;255;162;92m"
            OrangeInvert = "${script:CSI}97;48;2;255;122;24m"
            Muted = "${script:CSI}38;2;138;143;152m"
            Success = "${script:CSI}32m"
            Warn = "${script:CSI}33m"
            Error = "${script:CSI}31m"
            Border = "${script:CSI}38;2;0;209;178m"
            BorderError = "${script:CSI}31m"
            Status = "${script:CSI}38;2;11;15;20m"
        }
    }

    return [ordered]@{
        Reset = $reset
        Bold = $bold
        Dim = $dim
        Teal = "${script:CSI}36m"
        TealBright = "${script:CSI}96m"
        TealInvert = "${script:CSI}97;46m"
        Orange = "${script:CSI}33m"
        OrangeBright = "${script:CSI}93m"
        OrangeInvert = "${script:CSI}97;43m"
        Muted = "${script:CSI}90m"
        Success = "${script:CSI}32m"
        Warn = "${script:CSI}33m"
        Error = "${script:CSI}31m"
        Border = "${script:CSI}36m"
        BorderError = "${script:CSI}31m"
        Status = "${script:CSI}30m"
    }
}

function Format-TeikenText {
    param(
        [pscustomobject]$State,
        [string]$Text,
        [string]$Style
    )

    if (-not $State.TerminalCaps.Ansi) {
        return $Text
    }

    $theme = $State.Theme
    if (-not $theme.Contains($Style)) {
        return $Text
    }

    return "{0}{1}{2}" -f $theme[$Style], $Text, $theme.Reset
}

function Write-TeikenMainLog {
    param(
        [pscustomobject]$State,
        [string]$Message
    )

    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff')
    Add-Content -Path $State.Artifacts.MainLogPath -Value "[$stamp] $Message"
}

function New-TeikenStep {
    param(
        [string]$Id,
        [int]$Index,
        [int]$Total,
        [string]$Name,
        [string]$CommandPreview,
        [bool]$Critical,
        [bool]$WarnOnly
    )

    return [pscustomobject]@{
        Id = $Id
        Index = $Index
        Total = $Total
        Name = $Name
        CommandPreview = $CommandPreview
        Critical = $Critical
        WarnOnly = $WarnOnly
        Status = 'todo'
        Hint = ''
        StartTime = $null
        EndTime = $null
        DurationMs = 0
        LogPath = ''
        ExitCode = $null
        TailLines = @()
        ErrorTailLines = @()
    }
}

function Get-TeikenInstallerContext {
    [CmdletBinding()]
    param(
        [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
        [switch]$VerboseLogs,
        [switch]$NoAnsi,
        [switch]$SkipSmokeTests,
        [switch]$CI,
        [switch]$NoStart,
        [switch]$NoUi
    )

    Initialize-TeikenConsole

    $interactive = $true
    try {
        $interactive = -not [Console]::IsOutputRedirected
    } catch {
        $interactive = $false
    }

    $ansi = Get-TeikenAnsiSupport -NoAnsi:$NoAnsi -CI:$CI
    $trueColor = Test-TeikenTrueColorSupport -AnsiEnabled:$ansi

    $mode = if ($CI) {
        'CI'
    } elseif ($interactive -and $ansi) {
        'CINEMATIC'
    } else {
        'PLAIN'
    }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'

    $installLogDir = Join-Path $ProjectRoot 'logs\install'
    $stepLogDir = Join-Path $installLogDir 'steps'
    $bundleDir = Join-Path $installLogDir 'bundles'
    $bootReportsPath = Join-Path $ProjectRoot 'logs\boot'

    foreach ($path in @($installLogDir, $stepLogDir, $bundleDir, $bootReportsPath)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    $mainLogPath = Join-Path $installLogDir ("setup_{0}.log" -f $timestamp)
    $summaryPath = Join-Path $installLogDir ("setup_{0}.summary.json" -f $timestamp)

    New-Item -ItemType File -Force -Path $mainLogPath | Out-Null

    $hostForUrls = if ($env:TEIKEN_API_HOST) { $env:TEIKEN_API_HOST } else { '127.0.0.1' }
    if ($hostForUrls -eq '0.0.0.0') { $hostForUrls = '127.0.0.1' }
    $apiPort = if ($env:TEIKEN_API_PORT) { $env:TEIKEN_API_PORT } else { '8000' }
    $dashPort = if ($env:TEIKEN_DASHBOARD_PORT) { $env:TEIKEN_DASHBOARD_PORT } else { '5173' }
    $publicBase = if ($env:TEIKEN_PUBLIC_BASE_URL) { $env:TEIKEN_PUBLIC_BASE_URL } else { "http://$hostForUrls`:$apiPort" }

    $configPath = Join-Path $env:LOCALAPPDATA 'TeikenClaw\config\user_config.json'
    $logsPath = Join-Path $env:LOCALAPPDATA 'TeikenClaw\logs'

    $steps = @(
        New-TeikenStep -Id 'resolve_context' -Index 1 -Total 12 -Name 'Resolve Context' -CommandPreview 'Detect paths and capabilities' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'check_terminal' -Index 2 -Total 12 -Name 'Check PowerShell / Terminal' -CommandPreview 'ANSI + terminal capability check' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'check_python' -Index 3 -Total 12 -Name 'Check Python' -CommandPreview 'python --version' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'check_ollama' -Index 4 -Total 12 -Name 'Check Ollama' -CommandPreview 'ollama list' -Critical $false -WarnOnly $true
        New-TeikenStep -Id 'venv' -Index 5 -Total 12 -Name 'Virtual Environment' -CommandPreview 'python -m venv venv' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'sync_dependencies' -Index 6 -Total 12 -Name 'Sync Dependencies' -CommandPreview 'pip install (quiet)' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'configure_environment' -Index 7 -Total 12 -Name 'Configure Environment' -CommandPreview '.env + user_config' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'create_directories' -Index 8 -Total 12 -Name 'Create Data Directories' -CommandPreview 'logs/ data/ exports/ backups/' -Critical $true -WarnOnly $false
        New-TeikenStep -Id 'initialize_database' -Index 9 -Total 12 -Name 'Initialize Database' -CommandPreview 'alembic upgrade head' -Critical $false -WarnOnly $true
        New-TeikenStep -Id 'smoke_tests' -Index 10 -Total 12 -Name 'Smoke Tests' -CommandPreview 'scripts/smoke_test.ps1' -Critical $false -WarnOnly $true
        New-TeikenStep -Id 'boot_report' -Index 11 -Total 12 -Name 'Install-time Boot Report' -CommandPreview 'teiken-claw doctor' -Critical $false -WarnOnly $true
        New-TeikenStep -Id 'launchpad' -Index 12 -Total 12 -Name 'Launchpad' -CommandPreview 'Interactive controls' -Critical $true -WarnOnly $false
    )

    $termWidth = if ($interactive) { [Console]::WindowWidth } else { 120 }
    $termHeight = if ($interactive) { [Console]::WindowHeight } else { 40 }
    $unicodeSupported = $false
    try {
        $encodingName = [Console]::OutputEncoding.WebName
        $unicodeSupported = $encodingName -match 'utf'
    } catch {
        $unicodeSupported = $false
    }
    $shellLabel = if ($PSVersionTable.PSVersion.Major -ge 7) { "PowerShell $($PSVersionTable.PSVersion)" } else { "Windows PowerShell $($PSVersionTable.PSVersion)" }

    $state = [pscustomobject]@{
        Version = '1.4.0'
        Mode = $mode
        Cancelled = $false
        CancelReason = ''
        ExitCode = 0
        StartedAt = Get-Date
        EndedAt = $null
        OverallProgress = 0.0
        TerminalCaps = [pscustomobject]@{
            Ansi = $ansi
            TrueColor = $trueColor
            Interactive = $interactive
            Width = $termWidth
            Height = $termHeight
            Shell = $shellLabel
            PsVersion = $PSVersionTable.PSVersion.ToString()
            Unicode = $unicodeSupported
        }
        Theme = $null
        Flags = [pscustomobject]@{
            VerboseLogs = [bool]($VerboseLogs)
            SkipSmokeTests = [bool]($SkipSmokeTests)
            CI = [bool]($CI)
            NoAnsi = [bool]($NoAnsi)
            NoStart = [bool]($NoStart)
            NoUi = [bool]($NoUi)
        }
        Steps = $steps
        Paths = [pscustomobject]@{
            ProjectRoot = $ProjectRoot
            VenvPath = Join-Path $ProjectRoot 'venv'
            ConfigPath = $configPath
            LogsPath = $logsPath
            BootReportsPath = $bootReportsPath
            InstallLogDir = $installLogDir
            StepLogDir = $stepLogDir
            BundleDir = $bundleDir
        }
        Artifacts = [pscustomobject]@{
            MainLogPath = $mainLogPath
            SummaryJsonPath = $summaryPath
            BundleZipPath = ''
        }
        Versions = [ordered]@{
            Python = ''
            Pip = ''
            Ollama = ''
            Git = ''
            PowerShell = $PSVersionTable.PSVersion.ToString()
        }
        Urls = [ordered]@{
            Api = "http://$hostForUrls`:$apiPort"
            Dashboard = "http://$hostForUrls`:$dashPort"
            Public = $publicBase
            Webhook = "{0}/webhook/telegram" -f $publicBase.TrimEnd('/')
        }
        Runtime = [ordered]@{
            PythonCommand = ''
            PythonExe = ''
            PipExe = ''
            GitSha = ''
            ActiveProcess = $null
            LaunchpadAction = 'quit'
        }
        Ui = [pscustomobject]@{
            Frame = 0
            SpinnerFrames = @('⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏')
            SpinnerIndex = 0
            ShimmerIndex = 0
            CometIndex = 0
            PulseOn = $true
            LastTick = [DateTime]::UtcNow
            LastRender = [DateTime]::MinValue
            VerboseEnabled = [bool]($VerboseLogs)
            VerboseTail = New-Object System.Collections.Generic.List[string]
            ShowHelp = $false
            Frozen = $false
            FailureMessage = ''
            FailureTail = @()
            IntroPhase = 0
            ReadyPulse = 0
        }
    }

    $state.Theme = Get-TeikenTheme -State $state
    Write-TeikenMainLog -State $state -Message "Context initialized mode=$mode project_root=$ProjectRoot"

    return $state
}

function Get-TeikenStatusTicker {
    param(
        [pscustomobject]$State
    )

    $okGlyph = if ($State.TerminalCaps.Unicode) { '✓' } else { 'OK' }
    $failGlyph = if ($State.TerminalCaps.Unicode) { '✗' } else { 'X' }
    $pulseA = if ($State.TerminalCaps.Unicode) { '•' } else { '.' }
    $pulseB = if ($State.TerminalCaps.Unicode) { '·' } else { '.' }

    if ($State.ExitCode -ne 0) {
        return Format-TeikenText -State $State -Text $failGlyph -Style 'Error'
    }

    $allDone = -not ($State.Steps | Where-Object { $_.Status -eq 'running' })
    if ($allDone -and @($State.Steps | Where-Object { $_.Status -eq 'ok' -or $_.Status -eq 'warn' -or $_.Status -eq 'skipped' }).Count -ge 11) {
        return Format-TeikenText -State $State -Text $okGlyph -Style 'Success'
    }

    if ($State.Ui.Frame % 4 -lt 2) { return $pulseA }
    return $pulseB
}

function Get-TeikenStyledTopBorder {
    param(
        [pscustomobject]$State,
        [int]$Width,
        [bool]$Failure
    )

    $innerWidth = [Math]::Max(4, $Width - 2)

    $chars = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $innerWidth; $i++) {
        $chars.Add('━')
    }

    if (-not $Failure) {
        $comet = $State.Ui.CometIndex % $innerWidth
        for ($offset = 0; $offset -lt 3; $offset++) {
            $index = $comet - $offset
            if ($index -lt 0) { $index += $innerWidth }
            if ($offset -eq 0) {
                $chars[$index] = Format-TeikenText -State $State -Text '━' -Style 'OrangeBright'
            } elseif ($offset -eq 1) {
                $chars[$index] = Format-TeikenText -State $State -Text '━' -Style 'Orange'
            } else {
                $chars[$index] = Format-TeikenText -State $State -Text '━' -Style 'Muted'
            }
        }
    }

    $borderStyle = if ($Failure) { 'BorderError' } else { 'Border' }
    $left = Format-TeikenText -State $State -Text '┏' -Style $borderStyle
    $right = Format-TeikenText -State $State -Text '┓' -Style $borderStyle
    $middle = ($chars -join '')
    if (-not $State.TerminalCaps.Ansi) {
        $middle = '━' * $innerWidth
    }

    if (-not $Failure -and $State.TerminalCaps.Ansi) {
        $middle = "{0}{1}{2}" -f $State.Theme.Border, $middle, $State.Theme.Reset
    } elseif ($Failure -and $State.TerminalCaps.Ansi) {
        $middle = "{0}{1}{2}" -f $State.Theme.BorderError, $middle, $State.Theme.Reset
    }

    return "$left$middle$right"
}

function Get-TeikenTitleWordmark {
    param(
        [pscustomobject]$State,
        [int]$ShimmerIndex
    )

    $brand = 'TEIKEN CLAW'
    if (-not $State.TerminalCaps.Ansi) {
        return "TEIKEN CLAW • Environment Setup"
    }

    $sb = New-Object System.Text.StringBuilder
    for ($i = 0; $i -lt $brand.Length; $i++) {
        $ch = $brand[$i]
        $distance = [Math]::Abs($i - ($ShimmerIndex % $brand.Length))

        if ($i -le 5) {
            if ($distance -eq 0) {
                $style = $State.Theme.TealInvert
            } elseif ($distance -le 1) {
                $style = $State.Theme.TealBright
            } else {
                $style = $State.Theme.Teal
            }
        } elseif ($i -ge 7) {
            if ($distance -eq 0) {
                $style = $State.Theme.OrangeInvert
            } elseif ($distance -le 1) {
                $style = $State.Theme.OrangeBright
            } else {
                $style = $State.Theme.Orange
            }
        } else {
            $style = $State.Theme.Muted
        }

        [void]$sb.Append($style)
        [void]$sb.Append($State.Theme.Bold)
        [void]$sb.Append($ch)
        [void]$sb.Append($State.Theme.Reset)
    }

    [void]$sb.Append((Format-TeikenText -State $State -Text ' • Environment Setup' -Style 'Muted'))
    return $sb.ToString()
}

function New-TeikenPanel {
    param(
        [pscustomobject]$State,
        [string]$Title,
        [string[]]$Lines,
        [int]$Width,
        [string]$BorderStyle = 'Border'
    )

    $innerWidth = [Math]::Max(8, $Width - 2)

    $top = "┌" + ('─' * $innerWidth) + "┐"
    $bottom = "└" + ('─' * $innerWidth) + "┘"

    if ($State.TerminalCaps.Ansi) {
        $top = "{0}{1}{2}" -f $State.Theme[$BorderStyle], $top, $State.Theme.Reset
        $bottom = "{0}{1}{2}" -f $State.Theme[$BorderStyle], $bottom, $State.Theme.Reset
    }

    $out = New-Object System.Collections.Generic.List[string]
    $out.Add($top)

    $titlePlain = " $Title "
    if ($titlePlain.Length -gt $innerWidth) {
        $titlePlain = $titlePlain.Substring(0, $innerWidth)
    }

    $titlePad = $titlePlain.PadRight($innerWidth)
    $titleStyled = if ($State.TerminalCaps.Ansi) {
        "{0}{1}{2}" -f $State.Theme.Muted, $titlePad, $State.Theme.Reset
    } else {
        $titlePad
    }
    $out.Add("│$titleStyled│")

    foreach ($line in $Lines) {
        $raw = $line
        if ((Get-TeikenVisibleLength -Text $raw) -gt $innerWidth) {
            $plain = Strip-Ansi -Text $raw
            $plain = Get-TeikenMiddleEllipsis -Text $plain -MaxLength $innerWidth
            $raw = $plain
        }

        $padding = [Math]::Max(0, $innerWidth - (Get-TeikenVisibleLength -Text $raw))
        $out.Add("│$raw$((' ' * $padding))│")
    }

    $out.Add($bottom)
    return $out
}

function Get-TeikenProgressBar {
    param(
        [pscustomobject]$State,
        [int]$Width = 26
    )

    $done = @($State.Steps | Where-Object { $_.Status -in @('ok', 'warn', 'skipped', 'fail') }).Count
    $total = $State.Steps.Count
    $progress = if ($total -eq 0) { 0 } else { [double]$done / [double]$total }
    $State.OverallProgress = $progress

    $fillCount = [Math]::Floor($progress * $Width)
    $fillCount = [Math]::Min($Width, [Math]::Max(0, $fillCount))

    $sheen = -1
    if ($fillCount -ge 10) {
        $sheen = $State.Ui.Frame % [Math]::Max(1, $fillCount)
    }

    $segments = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $Width; $i++) {
        if ($i -lt $fillCount) {
            if ($sheen -ge 0 -and ($i -eq $sheen -or $i -eq ($sheen + 1))) {
                $cell = if ($State.TerminalCaps.Ansi) { "{0}{1}{2}" -f $State.Theme.TealBright, '█', $State.Theme.Reset } else { '#' }
                $segments.Add($cell)
            } else {
                $cell = if ($State.TerminalCaps.Ansi) { "{0}{1}{2}" -f $State.Theme.Teal, '█', $State.Theme.Reset } else { '#' }
                $segments.Add($cell)
            }
        } else {
            $segments.Add('░')
        }
    }

    $percent = [int]([Math]::Round($progress * 100))
    return "[{0}] {1,3}%" -f ($segments -join ''), $percent
}

function Get-TeikenDurationText {
    param(
        [pscustomobject]$Step
    )

    if ($Step.Status -eq 'running' -and $Step.StartTime) {
        $elapsed = ((Get-Date) - $Step.StartTime).TotalSeconds
        return ('{0,6:0.0}s' -f $elapsed)
    }

    if ($Step.DurationMs -gt 0) {
        return ('{0,6:0.0}s' -f ($Step.DurationMs / 1000.0))
    }

    return '     —'
}

function Process-TeikenUiInput {
    param(
        [pscustomobject]$State
    )

    if (-not $State.TerminalCaps.Interactive) { return }
    if (-not $script:TeikenUiStarted) { return }

    try {
        while ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)

            if ($key.Modifiers -band [ConsoleModifiers]::Control -and $key.Key -eq [ConsoleKey]::C) {
                $State.Cancelled = $true
                $State.CancelReason = 'User cancelled with Ctrl+C'
                return
            }

            switch ($key.Key) {
                ([ConsoleKey]::Q) {
                    $State.Cancelled = $true
                    $State.CancelReason = 'User cancelled with Q'
                    return
                }
                ([ConsoleKey]::V) {
                    $State.Ui.VerboseEnabled = -not $State.Ui.VerboseEnabled
                }
                ([ConsoleKey]::L) {
                    if (Test-Path $State.Paths.InstallLogDir) {
                        Start-Process explorer.exe $State.Paths.InstallLogDir | Out-Null
                    }
                }
                ([ConsoleKey]::Oem2) {
                    $State.Ui.ShowHelp = -not $State.Ui.ShowHelp
                }
            }
        }
    } catch {
        Write-TeikenMainLog -State $State -Message ("UI input handler warning: {0}" -f $_.Exception.Message)
        return
    }
}

function Render-TeikenFrame {
    [CmdletBinding()]
    param(
        [pscustomobject]$State
    )

    if ($State.Mode -eq 'PLAIN' -or $State.Mode -eq 'CI') {
        return
    }

    if (-not $script:TeikenUiStarted) {
        return
    }

    try {
        $now = [DateTime]::UtcNow
        if (($now - $State.Ui.LastRender).TotalMilliseconds -lt 120) {
            return
        }

        Process-TeikenUiInput -State $State

        $State.Ui.Frame++
        $State.Ui.SpinnerIndex = ($State.Ui.SpinnerIndex + 1) % $State.Ui.SpinnerFrames.Count
        if ($State.Ui.Frame % 2 -eq 0) {
            $State.Ui.ShimmerIndex++
        }
        $State.Ui.CometIndex++
        if ($State.Ui.Frame % 6 -eq 0) {
            $State.Ui.PulseOn = -not $State.Ui.PulseOn
        }

        try {
            $State.TerminalCaps.Width = [Console]::WindowWidth
            $State.TerminalCaps.Height = [Console]::WindowHeight
        } catch {
        }

        $width = [Math]::Max(70, $State.TerminalCaps.Width)

        $frameLines = New-Object System.Collections.Generic.List[string]
        $failure = [bool]($State.ExitCode -ne 0)

        if ($State.Ui.IntroPhase -lt 4) {
            $State.Ui.IntroPhase++
        }

    $frameLines.Add((Get-TeikenStyledTopBorder -State $State -Width $width -Failure $failure))

    $titleLine = if ($State.Ui.IntroPhase -ge 2) {
        Get-TeikenTitleWordmark -State $State -ShimmerIndex $State.Ui.ShimmerIndex
    } else {
        Format-TeikenText -State $State -Text 'TEIKEN CLAW' -Style 'Teal'
    }

    $subtitle = Format-TeikenText -State $State -Text ("Environment Setup • v{0} • Windows" -f $State.Version) -Style 'Muted'

    $modeLabel = if ($State.Ui.VerboseEnabled -and $State.Mode -eq 'CINEMATIC') { 'VERBOSE' } else { $State.Mode }
    $ansiLabel = if (-not $State.TerminalCaps.Ansi) { 'OFF' } elseif ($State.TerminalCaps.TrueColor) { 'TRUECOLOR' } else { 'BASIC' }
    if ($width -lt 110) {
        $modeLabel = $modeLabel.Replace('CINEMATIC', 'CINE')
        $ansiLabel = $ansiLabel.Replace('TRUECOLOR', 'TC')
    }

    $metaEnv = if ($env:TEIKEN_ENV) { $env:TEIKEN_ENV } else { 'local' }
    $metaGit = if ($State.Runtime.GitSha) { $State.Runtime.GitSha } else { '--------' }
    $meta = "v{0} • env={1} • git={2} • mode={3} • ansi={4}" -f $State.Version, $metaEnv, $metaGit, $modeLabel, $ansiLabel
    $metaStyled = Format-TeikenText -State $State -Text $meta -Style 'Muted'
    $tagline = (Format-TeikenText -State $State -Text 'Local-first agent service • Ollama-ready • ' -Style 'Muted') + (Format-TeikenText -State $State -Text 'Diagnostics-first' -Style 'Orange')
    $innerWidth = [Math]::Max(4, $width - 4)
    $frameLines.Add(("┃  {0}{1}" -f $titleLine, ' ' * [Math]::Max(0, $innerWidth - (Get-TeikenVisibleLength $titleLine))))
    $frameLines.Add(("┃  {0}{1}" -f $subtitle, ' ' * [Math]::Max(0, $innerWidth - (Get-TeikenVisibleLength $subtitle))))
    $frameLines.Add(("┃  {0}{1}" -f $metaStyled, ' ' * [Math]::Max(0, $innerWidth - (Get-TeikenVisibleLength $metaStyled))))

    if ($width -ge 90 -and $State.Ui.IntroPhase -ge 3) {
        $line = if ($width -ge 110) { $tagline } else { Format-TeikenText -State $State -Text 'Local-first • Ollama-ready • Diagnostics-first' -Style 'Muted' }
        $frameLines.Add(("┃  {0}{1}" -f $line, ' ' * [Math]::Max(0, $innerWidth - (Get-TeikenVisibleLength $line))))
    } else {
        $frameLines.Add("┃  " + (' ' * $innerWidth))
    }

    $frameLines.Add("┃  " + (' ' * $innerWidth))
    $frameLines.Add("┗" + ('━' * [Math]::Max(2, $width - 2)) + "┛")

    if ($width -ge 90) {
        $shadowWidth = [Math]::Max(10, $width - 6)
        $shadow = (' ' * 2) + (Format-TeikenText -State $State -Text (('▁' * $shadowWidth)) -Style 'Muted')
        $frameLines.Add($shadow)
    }

    $ticker = Get-TeikenStatusTicker -State $State
    $statusLine = "{0} Mode: {1}   ANSI: {2}   Shell: {3}   Logs: {4}" -f $ticker, $modeLabel, $ansiLabel, $State.TerminalCaps.Shell, (Get-TeikenMiddleEllipsis -Text $State.Artifacts.MainLogPath -MaxLength ([Math]::Max(20, $width - 62)))
    $frameLines.Add($statusLine)

    $progressWidth = if ($width -ge 120) { 32 } else { 24 }
    $progressBar = Get-TeikenProgressBar -State $State -Width $progressWidth
    $mainHeader = "INSTALL PROGRESS  {0}" -f $progressBar

    $stepLines = New-Object System.Collections.Generic.List[string]
    $stepLines.Add($mainHeader)
    $stepLines.Add('')

    foreach ($step in $State.Steps) {
        $icon = switch ($step.Status) {
            'ok' { Format-TeikenText -State $State -Text '✓' -Style 'Success' }
            'warn' { Format-TeikenText -State $State -Text '⚠' -Style 'Warn' }
            'fail' { Format-TeikenText -State $State -Text '✗' -Style 'Error' }
            'skipped' { Format-TeikenText -State $State -Text '·' -Style 'Muted' }
            'running' {
                if ($State.TerminalCaps.Ansi -and $State.TerminalCaps.Unicode) {
                    Format-TeikenText -State $State -Text $State.Ui.SpinnerFrames[$State.Ui.SpinnerIndex] -Style 'TealBright'
                } else {
                    '|'
                }
            }
            default { Format-TeikenText -State $State -Text '•' -Style 'Muted' }
        }

        $idx = '{0:00}/{1:00}' -f $step.Index, $step.Total
        $name = $step.Name
        if ($step.Status -eq 'running' -and $State.Ui.PulseOn) {
            $name = Format-TeikenText -State $State -Text $name -Style 'TealBright'
        }

        $hint = if ($step.Hint) { $step.Hint } elseif ($step.CommandPreview) { $step.CommandPreview } else { '' }
        $hint = Get-TeikenMiddleEllipsis -Text $hint -MaxLength 34
        $dur = Get-TeikenDurationText -Step $step

        $line = "{0}  {1}  {2,-28}  {3,-36}  {4}" -f $icon, $idx, $name, $hint, $dur
        $stepLines.Add($line)
    }

    if ($State.ExitCode -ne 0) {
        $stepLines.Add('')
        $stepLines.Add((Format-TeikenText -State $State -Text 'FAILED' -Style 'Error') + " at step: $($State.Ui.FailureMessage)")
        foreach ($tailLine in $State.Ui.FailureTail) {
            $stepLines.Add((Format-TeikenText -State $State -Text (Get-TeikenMiddleEllipsis -Text $tailLine -MaxLength 76) -Style 'Muted'))
        }
    }

    $pythonDisplay = if ($State.Versions.Python) { $State.Versions.Python } else { 'detecting...' }
    $ollamaDisplay = if ($State.Versions.Ollama) { $State.Versions.Ollama } else { 'not verified yet' }
    $modelDisplay = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { 'default from config' }

    $envLines = @(
        "Python: {0}" -f $pythonDisplay,
        "Venv: {0}" -f (Get-TeikenMiddleEllipsis -Text $State.Paths.VenvPath -MaxLength 38),
        "Ollama: {0}" -f $ollamaDisplay,
        "Model: {0}" -f $modelDisplay,
        "Arch: {0}" -f $env:PROCESSOR_ARCHITECTURE,
        "Repo: {0}" -f (Get-TeikenMiddleEllipsis -Text $State.Paths.ProjectRoot -MaxLength 38)
    )

    $pathLines = @(
        "Config: {0}" -f (Get-TeikenMiddleEllipsis -Text $State.Paths.ConfigPath -MaxLength 38),
        "Logs: {0}" -f (Get-TeikenMiddleEllipsis -Text $State.Paths.LogsPath -MaxLength 38),
        "Boot: {0}" -f (Get-TeikenMiddleEllipsis -Text $State.Paths.BootReportsPath -MaxLength 38),
        "API: {0}" -f $State.Urls.Api,
        "Dashboard: {0}" -f $State.Urls.Dashboard,
        "Public: {0}" -f $State.Urls.Public
    )

    $hasWide = $width -ge 110

    if ($hasWide) {
        $leftWidth = [Math]::Floor($width * 0.62)
        $rightWidth = $width - $leftWidth - 1

        $leftPanel = New-TeikenPanel -State $State -Title 'Install Timeline' -Lines $stepLines -Width $leftWidth
        $rightEnv = New-TeikenPanel -State $State -Title 'Environment' -Lines $envLines -Width $rightWidth
        $rightPaths = New-TeikenPanel -State $State -Title 'Paths & URLs' -Lines $pathLines -Width $rightWidth

        $rightCombined = @()
        $rightCombined += $rightEnv
        $rightCombined += ''
        $rightCombined += $rightPaths

        $maxRows = [Math]::Max($leftPanel.Count, $rightCombined.Count)
        for ($row = 0; $row -lt $maxRows; $row++) {
            $left = if ($row -lt $leftPanel.Count) { $leftPanel[$row] } else { '' }
            $right = if ($row -lt $rightCombined.Count) { $rightCombined[$row] } else { '' }
            $padding = ' ' * [Math]::Max(0, $leftWidth - (Get-TeikenVisibleLength -Text $left))
            $frameLines.Add("$left$padding $right")
        }
    } else {
        $mainPanel = New-TeikenPanel -State $State -Title 'Install Timeline' -Lines $stepLines -Width $width
        $envPanel = New-TeikenPanel -State $State -Title 'Environment' -Lines $envLines -Width $width
        $pathPanel = New-TeikenPanel -State $State -Title 'Paths & URLs' -Lines $pathLines -Width $width
        $frameLines += $mainPanel
        $frameLines.Add('')
        $frameLines += $envPanel
        $frameLines.Add('')
        $frameLines += $pathPanel
    }

    if ($State.Ui.VerboseEnabled) {
        $tail = @($State.Ui.VerboseTail)
        $tailLines = if ($tail.Count -gt 20) {
            $tail[($tail.Count-20)..($tail.Count-1)]
        } else {
            $tail
        }
        if (-not $tailLines -or $tailLines.Count -eq 0) {
            $tailLines = @('No output yet...')
        }
        $outputPanel = New-TeikenPanel -State $State -Title 'Output (tail)' -Lines $tailLines -Width $width
        $frameLines.Add('')
        $frameLines += $outputPanel
    }

    if ($State.Ui.ShowHelp) {
        $helpLines = @(
            'V: Toggle verbose tail panel',
            'L: Open install logs folder',
            'Q: Cancel installer (exit 130)',
            '?: Toggle this help overlay'
        )
        $helpPanel = New-TeikenPanel -State $State -Title 'Help' -Lines $helpLines -Width $width
        $frameLines.Add('')
        $frameLines += $helpPanel
    }

    $frameLines.Add('')
    $frameLines.Add((Format-TeikenText -State $State -Text 'Press V for verbose output • Press L to open logs • Press Q to cancel • Press ? for help' -Style 'Muted'))
    $frameLines.Add((Format-TeikenText -State $State -Text ('Main log: ' + $State.Artifacts.MainLogPath) -Style 'Dim'))

    $buffer = New-Object System.Text.StringBuilder
    [void]$buffer.Append("${script:CSI}H")
    foreach ($line in $frameLines) {
        [void]$buffer.Append($line)
        [void]$buffer.Append("`n")
    }

        [Console]::Write($buffer.ToString())
        $State.Ui.LastRender = [DateTime]::UtcNow
    } catch {
        Write-TeikenMainLog -State $State -Message ("UI render failure; fallback to plain mode: {0}" -f $_.Exception.Message)
        $State.Mode = 'PLAIN'
        try { Stop-TeikenUI -State $State } catch {}
    }
}

function Start-TeikenUI {
    [CmdletBinding()]
    param(
        [pscustomobject]$State
    )

    $script:TeikenCurrentState = $State

    if ($State.Mode -eq 'PLAIN' -or $State.Mode -eq 'CI') {
        Write-Host "[SETUP] Mode: $($State.Mode)" -ForegroundColor Cyan
        Write-Host "[SETUP] Logs: $($State.Artifacts.MainLogPath)" -ForegroundColor Gray
        return
    }

    try {
        $script:TeikenPrevCtrlCAsInput = [Console]::TreatControlCAsInput
    } catch {
        $script:TeikenPrevCtrlCAsInput = $false
    }

    try {
        [Console]::TreatControlCAsInput = $true
    } catch {
    }

    try {
        [Console]::Write("${script:CSI}?1049h${script:CSI}?25l${script:CSI}2J${script:CSI}H")
    } catch {
        Write-TeikenMainLog -State $State -Message ("Failed to enter cinematic mode; falling back to plain: {0}" -f $_.Exception.Message)
        $State.Mode = 'PLAIN'
        return
    }
    $script:TeikenUiStarted = $true

    if ($State.TerminalCaps.Interactive) {
        $script:TeikenCancelHandler = [ConsoleCancelEventHandler]{
            param($sender, $eventArgs)
            $eventArgs.Cancel = $true
            if ($script:TeikenCurrentState) {
                $script:TeikenCurrentState.Cancelled = $true
                $script:TeikenCurrentState.CancelReason = 'User cancelled with Ctrl+C'
            }
        }
        try {
            [Console]::add_CancelKeyPress($script:TeikenCancelHandler)
        } catch {
        }
    }

    for ($i = 0; $i -lt 8; $i++) {
        if ($i -lt 2) {
            $State.Ui.IntroPhase = 1
        } elseif ($i -lt 4) {
            $State.Ui.IntroPhase = 2
        } elseif ($i -lt 6) {
            $State.Ui.IntroPhase = 3
        } else {
            $State.Ui.IntroPhase = 4
        }

        Render-TeikenFrame -State $State
        Start-Sleep -Milliseconds 120
    }
}

function Stop-TeikenUI {
    [CmdletBinding()]
    param(
        [pscustomobject]$State
    )

    if ($script:TeikenCancelHandler) {
        try {
            [Console]::remove_CancelKeyPress($script:TeikenCancelHandler)
        } catch {
        }
        $script:TeikenCancelHandler = $null
    }

    try {
        [Console]::TreatControlCAsInput = $script:TeikenPrevCtrlCAsInput
    } catch {
    }

    if ($script:TeikenUiStarted) {
        [Console]::Write("${script:CSI}0m${script:CSI}?25h${script:CSI}?1049l")
        $script:TeikenUiStarted = $false
    }
}

function ConvertTo-TeikenArguments {
    param(
        [string[]]$Arguments
    )

    if (-not $Arguments) { return '' }

    $quoted = foreach ($arg in $Arguments) {
        if ($arg -match '[\s\"]') {
            '"{0}"' -f ($arg.Replace('"', '\"'))
        } else {
            $arg
        }
    }

    return ($quoted -join ' ')
}

function Invoke-TeikenProcessQuiet {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$State,

        [Parameter(Mandatory = $true)]
        [pscustomobject]$Step,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @(),

        [string]$WorkingDirectory = $State.Paths.ProjectRoot,

        [int]$TailLimit = 200,

        [int]$TickMs = 100
    )

    $stepTimestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $stepLog = Join-Path $State.Paths.StepLogDir ("{0}_{1}.log" -f $Step.Id, $stepTimestamp)
    $Step.LogPath = $stepLog
    New-Item -ItemType File -Force -Path $stepLog | Out-Null

    $argString = ConvertTo-TeikenArguments -Arguments $Arguments
    Write-TeikenMainLog -State $State -Message ("STEP {0} CMD: {1} {2}" -f $Step.Id, $FilePath, $argString)

    $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $FilePath
    $processInfo.Arguments = $argString
    $processInfo.WorkingDirectory = $WorkingDirectory
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $processInfo

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $stdoutText = ''
    $stderrText = ''
    $stdoutCount = 0
    $stderrCount = 0

    try {
        if (-not $process.Start()) {
            throw "Failed to start process: $FilePath"
        }

        $State.Runtime.ActiveProcess = $process

        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()

        while (-not $process.WaitForExit($TickMs)) {
            if ($State.Cancelled) {
                try {
                    if (-not $process.HasExited) {
                        $process.Kill()
                    }
                } catch {
                }
                break
            }

            if ($State.Mode -eq 'CINEMATIC') {
                Render-TeikenFrame -State $State
            }
        }

        $process.WaitForExit()
        $stdoutText = $stdoutTask.GetAwaiter().GetResult()
        $stderrText = $stderrTask.GetAwaiter().GetResult()
        $stopwatch.Stop()

        $stdoutLines = @()
        if ($stdoutText) {
            $stdoutLines = @($stdoutText -split '\r?\n' | Where-Object { $_ -ne '' })
        }

        $stderrLines = @()
        if ($stderrText) {
            $stderrLines = @($stderrText -split '\r?\n' | Where-Object { $_ -ne '' })
        }

        $stdoutCount = $stdoutLines.Count
        $stderrCount = $stderrLines.Count

        $tail = @($stdoutLines + $stderrLines)
        if ($tail.Count -gt $TailLimit) {
            $start = $tail.Count - $TailLimit
            $end = $tail.Count - 1
            $tail = $tail[$start..$end]
        }

        $errorTail = @($stderrLines)
        if ($errorTail.Count -gt $TailLimit) {
            $startErr = $errorTail.Count - $TailLimit
            $endErr = $errorTail.Count - 1
            $errorTail = $errorTail[$startErr..$endErr]
        }

        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        $stepWriter = New-Object System.IO.StreamWriter($stepLog, $true, $utf8NoBom)
        $mainWriter = New-Object System.IO.StreamWriter($State.Artifacts.MainLogPath, $true, $utf8NoBom)
        try {
            foreach ($line in $stdoutLines) {
                $stepWriter.WriteLine("[OUT] $line")
                $mainWriter.WriteLine(("[{0}][OUT] {1}" -f $Step.Id, $line))
                $State.Ui.VerboseTail.Add($line)
            }
            foreach ($line in $stderrLines) {
                $stepWriter.WriteLine("[ERR] $line")
                $mainWriter.WriteLine(("[{0}][ERR] {1}" -f $Step.Id, $line))
                $State.Ui.VerboseTail.Add($line)
            }
            while ($State.Ui.VerboseTail.Count -gt 200) {
                $State.Ui.VerboseTail.RemoveAt(0)
            }
            $stepWriter.Flush()
            $mainWriter.Flush()
        } finally {
            $stepWriter.Dispose()
            $mainWriter.Dispose()
        }

        if ($State.Mode -eq 'CINEMATIC') {
            Render-TeikenFrame -State $State
        }

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            DurationMs = [int]$stopwatch.ElapsedMilliseconds
            TailLines = @($tail)
            ErrorTailLines = @($errorTail)
            StdoutLineCount = $stdoutCount
            StderrLineCount = $stderrCount
            LogPath = $stepLog
            Hint = ''
        }
    } finally {
        $State.Runtime.ActiveProcess = $null
        try { $process.Dispose() } catch {}
    }
}

function Invoke-TeikenStep {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$State,

        [Parameter(Mandatory = $true)]
        [string]$StepId,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    $step = $State.Steps | Where-Object { $_.Id -eq $StepId } | Select-Object -First 1
    if (-not $step) {
        throw "Unknown step id: $StepId"
    }

    if ($State.Cancelled) {
        $step.Status = 'skipped'
        $step.Hint = 'Cancelled before execution'
        return $step
    }

    $step.Status = 'running'
    $step.StartTime = Get-Date
    $step.Hint = ''

    if ($State.Mode -eq 'CINEMATIC') {
        Render-TeikenFrame -State $State
    } else {
        Write-Host ("[STEP {0:00}/{1:00}] {2}" -f $step.Index, $step.Total, $step.Name) -ForegroundColor Cyan
    }

    $result = $null
    $errText = ''

    try {
        $result = & $Action $State $step
    } catch {
        $errText = $_.Exception.Message
        $result = [pscustomobject]@{
            ExitCode = 1
            DurationMs = 0
            TailLines = @($errText)
            ErrorTailLines = @($errText)
            LogPath = $step.LogPath
            Hint = $errText
        }
    }

    if ($null -eq $result) {
        $result = [pscustomobject]@{
            ExitCode = 0
            DurationMs = 0
            TailLines = @()
            ErrorTailLines = @()
            LogPath = $step.LogPath
            Hint = ''
        }
    }

    $step.EndTime = Get-Date
    $step.DurationMs = [int](($step.EndTime - $step.StartTime).TotalMilliseconds)
    if ($result.DurationMs -and $result.DurationMs -gt 0) {
        $step.DurationMs = [int]$result.DurationMs
    }

    $step.ExitCode = $result.ExitCode
    if ($result.LogPath) { $step.LogPath = $result.LogPath }
    $step.TailLines = @($result.TailLines)
    $step.ErrorTailLines = @($result.ErrorTailLines)

    if ($result.PSObject.Properties.Name -contains 'StatusOverride' -and $result.StatusOverride -eq 'skipped') {
        $step.Status = 'skipped'
        $step.Hint = if ($result.Hint) { $result.Hint } else { 'Skipped' }
        $step.ExitCode = 0
    } elseif ($State.Cancelled) {
        $step.Status = 'fail'
        $step.Hint = 'Cancelled'
        $State.ExitCode = 130
    } elseif ($result.ExitCode -eq 0) {
        $step.Status = 'ok'
        if ($result.Hint) {
            $step.Hint = $result.Hint
        } else {
            $step.Hint = 'Completed'
        }
    } else {
        if ($step.WarnOnly) {
            $step.Status = 'warn'
            $step.Hint = if ($result.Hint) { $result.Hint } else { 'Warning (non-critical)' }
        } else {
            $step.Status = 'fail'
            $step.Hint = if ($result.Hint) { $result.Hint } else { 'Failed' }
            $State.ExitCode = if ($State.ExitCode -eq 0) { 1 } else { $State.ExitCode }
            $State.Ui.FailureMessage = "{0:00}/{1:00} {2}" -f $step.Index, $step.Total, $step.Name
            $tail = @($result.ErrorTailLines)
            if ($tail.Count -eq 0) { $tail = @($result.TailLines) }
            if ($tail.Count -gt 30) {
                $tail = $tail[($tail.Count-30)..($tail.Count-1)]
            }
            $State.Ui.FailureTail = $tail
        }
    }

    $done = @($State.Steps | Where-Object { $_.Status -in @('ok', 'warn', 'skipped', 'fail') }).Count
    $State.OverallProgress = [double]$done / [double]$State.Steps.Count

    if ($State.Mode -eq 'CINEMATIC') {
        Render-TeikenFrame -State $State
    } else {
        $label = switch ($step.Status) {
            'ok' { '[OK]' }
            'warn' { '[WARN]' }
            'fail' { '[FAIL]' }
            'skipped' { '[SKIP]' }
            default { '[..]' }
        }
        Write-Host ("{0} {1} - {2}" -f $label, $step.Name, $step.Hint)
    }

    if ($step.Status -eq 'fail' -and -not $step.WarnOnly) {
        throw "Critical step failed: $($step.Name)"
    }

    return $step
}

function Write-TeikenSummaryArtifacts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$State
    )

    $State.EndedAt = Get-Date

    $summary = [ordered]@{
        start_ts = $State.StartedAt.ToString('o')
        end_ts = $State.EndedAt.ToString('o')
        duration_ms = [int](($State.EndedAt - $State.StartedAt).TotalMilliseconds)
        mode = if ($State.Ui.VerboseEnabled -and $State.Mode -eq 'CINEMATIC') { 'VERBOSE' } else { $State.Mode }
        terminal_caps = [ordered]@{
            ansi = $State.TerminalCaps.Ansi
            truecolor = $State.TerminalCaps.TrueColor
            interactive = $State.TerminalCaps.Interactive
            width = $State.TerminalCaps.Width
            height = $State.TerminalCaps.Height
            shell = $State.TerminalCaps.Shell
            ps_version = $State.TerminalCaps.PsVersion
        }
        versions = $State.Versions
        paths = [ordered]@{
            project_root = $State.Paths.ProjectRoot
            config_path = $State.Paths.ConfigPath
            logs_path = $State.Paths.LogsPath
            boot_reports_path = $State.Paths.BootReportsPath
            main_log = $State.Artifacts.MainLogPath
            summary_json = $State.Artifacts.SummaryJsonPath
            bundle_zip = $State.Artifacts.BundleZipPath
        }
        urls = $State.Urls
        steps = @($State.Steps | ForEach-Object {
            [ordered]@{
                id = $_.Id
                index = $_.Index
                name = $_.Name
                status = $_.Status
                hint = $_.Hint
                start_time = if ($_.StartTime) { $_.StartTime.ToString('o') } else { $null }
                end_time = if ($_.EndTime) { $_.EndTime.ToString('o') } else { $null }
                duration_ms = $_.DurationMs
                log_path = $_.LogPath
                exit_code = $_.ExitCode
            }
        })
        exit_code = $State.ExitCode
        cancelled = $State.Cancelled
        cancellation_reason = $State.CancelReason
    }

    $summaryJson = $summary | ConvertTo-Json -Depth 8
    Set-Content -Path $State.Artifacts.SummaryJsonPath -Value $summaryJson -Encoding UTF8

    if ($State.ExitCode -ne 0 -and -not $State.Cancelled) {
        $bundleName = "install_fail_{0}.zip" -f (Get-Date -Format 'yyyyMMdd_HHmmss')
        $bundlePath = Join-Path $State.Paths.BundleDir $bundleName
        $items = New-Object System.Collections.Generic.List[string]

        if (Test-Path $State.Artifacts.MainLogPath) { $items.Add($State.Artifacts.MainLogPath) }
        if (Test-Path $State.Artifacts.SummaryJsonPath) { $items.Add($State.Artifacts.SummaryJsonPath) }

        foreach ($step in $State.Steps) {
            if ($step.LogPath -and (Test-Path $step.LogPath)) {
                $items.Add($step.LogPath)
            }
        }

        if (Test-Path $State.Paths.BootReportsPath) {
            foreach ($file in Get-ChildItem -Path $State.Paths.BootReportsPath -File -ErrorAction SilentlyContinue) {
                $items.Add($file.FullName)
            }
        }

        if ($items.Count -gt 0) {
            Compress-Archive -Path @($items.ToArray()) -DestinationPath $bundlePath -Force
            $State.Artifacts.BundleZipPath = $bundlePath
        }
    }

    Write-TeikenMainLog -State $State -Message "Summary written: $($State.Artifacts.SummaryJsonPath)"
}

function Show-TeikenLaunchpad {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$State
    )

    $launchpadStep = $State.Steps | Where-Object { $_.Id -eq 'launchpad' } | Select-Object -First 1
    if ($launchpadStep) {
        $launchpadStep.Status = 'ok'
        $launchpadStep.Hint = 'ready'
        $launchpadStep.StartTime = Get-Date
        $launchpadStep.EndTime = Get-Date
        $launchpadStep.DurationMs = 1
    }

    if ($State.Mode -eq 'PLAIN' -or $State.Mode -eq 'CI') {
        Write-Host ''
        Write-Host 'SETUP COMPLETE' -ForegroundColor Green
        Write-Host "Config: $($State.Paths.ConfigPath)"
        Write-Host "Logs:   $($State.Paths.InstallLogDir)"
        Write-Host "Boot:   $($State.Paths.BootReportsPath)"
        Write-Host "API:    $($State.Urls.Api)"
        Write-Host "Dash:   $($State.Urls.Dashboard)"
        Write-Host ''
        Write-Host 'Run dev server: .\scripts\run_dev.ps1'
        Write-Host 'Run doctor:     .\venv\Scripts\python.exe -m app.control_plane.entrypoint doctor'
        return 'quit'
    }

    $State.Ui.Frozen = $true
    for ($pulse = 0; $pulse -lt 6; $pulse++) {
        $State.Ui.ReadyPulse = $pulse
        Render-TeikenFrame -State $State
        Start-Sleep -Milliseconds 120
    }

    while ($true) {
        $width = [Math]::Max(70, [Console]::WindowWidth)
        $readyStyle = if (($State.Ui.ReadyPulse % 2) -eq 0) { 'Success' } else { 'TealBright' }
        $ready = Format-TeikenText -State $State -Text 'READY' -Style $readyStyle

        $launchLines = @(
            "SETUP COMPLETE  [$ready]",
            '',
            "Config:    $($State.Paths.ConfigPath)",
            "Logs:      $($State.Paths.InstallLogDir)",
            "Boot:      $($State.Paths.BootReportsPath)",
            "API URL:   $($State.Urls.Api)",
            "Dash URL:  $($State.Urls.Dashboard)",
            "Public:    $($State.Urls.Public)",
            '',
            'R: run dev server (scripts/run_dev.ps1)',
            'D: run doctor',
            'L: open logs folder',
            'B: open boot reports folder',
            'C: copy URLs to clipboard',
            'Q: quit'
        )

        $panel = New-TeikenPanel -State $State -Title 'Launchpad' -Lines $launchLines -Width $width
        $buffer = New-Object System.Text.StringBuilder
        [void]$buffer.Append("${script:CSI}H${script:CSI}2J${script:CSI}H")
        foreach ($line in $panel) {
            [void]$buffer.Append($line)
            [void]$buffer.Append("`n")
        }

        [Console]::Write($buffer.ToString())

        if (-not [Console]::KeyAvailable) {
            Start-Sleep -Milliseconds 120
            $State.Ui.ReadyPulse++
            continue
        }

        $key = [Console]::ReadKey($true)
        switch ($key.Key) {
            ([ConsoleKey]::R) { return 'run_dev' }
            ([ConsoleKey]::D) { return 'doctor' }
            ([ConsoleKey]::L) {
                if (Test-Path $State.Paths.InstallLogDir) {
                    Start-Process explorer.exe $State.Paths.InstallLogDir | Out-Null
                }
            }
            ([ConsoleKey]::B) {
                if (Test-Path $State.Paths.BootReportsPath) {
                    Start-Process explorer.exe $State.Paths.BootReportsPath | Out-Null
                }
            }
            ([ConsoleKey]::C) {
                $payload = @(
                    "API: $($State.Urls.Api)",
                    "Dashboard: $($State.Urls.Dashboard)",
                    "Public: $($State.Urls.Public)",
                    "Webhook: $($State.Urls.Webhook)"
                ) -join [Environment]::NewLine
                try {
                    Set-Clipboard -Value $payload
                } catch {
                }
            }
            ([ConsoleKey]::Q) { return 'quit' }
        }
    }
}

Export-ModuleMember -Function @(
    'Get-TeikenInstallerContext',
    'Start-TeikenUI',
    'Stop-TeikenUI',
    'Invoke-TeikenStep',
    'Invoke-TeikenProcessQuiet',
    'Render-TeikenFrame',
    'Show-TeikenLaunchpad',
    'Write-TeikenSummaryArtifacts'
)

