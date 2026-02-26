# Teiken Claw terminal branding helpers

Set-StrictMode -Version Latest

$script:TeikenBrandEsc = [char]27
$script:TeikenBrandCsi = "$script:TeikenBrandEsc["

function Enable-TeikenVtSupport {
    try {
        $isWindowsHost = ($env:OS -like '*Windows*')
        if (-not $isWindowsHost) { return $true }

        Add-Type -Namespace TeikenBranding -Name Win32 -MemberDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {
  public const int STD_OUTPUT_HANDLE = -11;
  public const uint ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004;
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern IntPtr GetStdHandle(int nStdHandle);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
}
"@ -ErrorAction SilentlyContinue

        $h = [TeikenBranding.Win32]::GetStdHandle([TeikenBranding.Win32]::STD_OUTPUT_HANDLE)
        if ($h -eq [IntPtr]::Zero) { return $false }

        $mode = 0
        if (-not [TeikenBranding.Win32]::GetConsoleMode($h, [ref]$mode)) { return $false }
        return [TeikenBranding.Win32]::SetConsoleMode($h, ($mode -bor [TeikenBranding.Win32]::ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    } catch {
        return $false
    }
}

function Test-TeikenVtSupport {
    if ($env:TEIKEN_NO_COLOR -eq '1') { return $false }
    try {
        if ([Console]::IsOutputRedirected) { return $false }
    } catch {
        return $false
    }

    try {
        if ($Host -and $Host.UI -and $Host.UI.SupportsVirtualTerminal) { return $true }
    } catch {
    }

    if (Enable-TeikenVtSupport) { return $true }
    if ($env:WT_SESSION) { return $true }
    if ($env:TERM -and $env:TERM -ne 'dumb') { return $true }
    return $false
}

function Get-TeikenClawLogoLines {
    param(
        [switch]$Compact,
        [switch]$NoColor
    )

    $useAnsi = (-not $NoColor) -and (Test-TeikenVtSupport)

    if ($useAnsi) {
        $teal = "${script:TeikenBrandCsi}38;2;0;209;178m"
        $tealBright = "${script:TeikenBrandCsi}38;2;36;235;208m"
        $orange = "${script:TeikenBrandCsi}38;2;255;122;24m"
        $muted = "${script:TeikenBrandCsi}38;2;138;143;152m"
        $bold = "${script:TeikenBrandCsi}1m"
        $reset = "${script:TeikenBrandCsi}0m"

        if ($Compact) {
            return @(
                "${teal}   /\        ${orange}${bold}██████████████${reset}${teal}        /\${reset}",
                "${teal}  /**\       ${orange}${bold}   ██  ██   ${reset}${teal}       /**\${reset}",
                "${tealBright} /****\      ${orange}${bold}   ████     ${reset}${tealBright}      /****\${reset}",
                "${muted}            TEIKEN CLAW${reset}"
            )
        }

        return @(
            "${teal}      /\                          /\${reset}",
            "${teal}     /**\                        /**\${reset}",
            "${tealBright}    /****\     ${orange}${bold}██████████████${reset}${tealBright}    /****\${reset}",
            "${tealBright}   /******\    ${orange}${bold}   ██   ██   ${reset}${tealBright}   /******\${reset}",
            "${teal}  /********\   ${orange}${bold}   ██████    ${reset}${teal}  /********\${reset}",
            "${teal}      ||        ${orange}${bold}    ██      ${reset}${teal}       ||${reset}",
            "${muted}   TEIKEN CLAW • Terminal-First Agent Platform${reset}"
        )
    }

    if ($Compact) {
        return @(
            "   /\        ██████████████        /\",
            "  /**\          ██  ██           /**\",
            " /****\         ████           /****\",
            "         TEIKEN CLAW"
        )
    }

    return @(
        "      /\                          /\",
        "     /**\                        /**\",
        "    /****\     ██████████████    /****\",
        "   /******\       ██  ██       /******\",
        "  /********\      ██████      /********\",
        "      ||            ██            ||",
        "   TEIKEN CLAW • Terminal-First Agent Platform"
    )
}

function Show-TeikenClawLogo {
    param(
        [switch]$Compact,
        [switch]$NoColor
    )

    $lines = Get-TeikenClawLogoLines -Compact:$Compact -NoColor:$NoColor
    foreach ($line in $lines) {
        Write-Host $line
    }
}
