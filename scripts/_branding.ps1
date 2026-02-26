# Teiken Claw terminal branding helpers

Set-StrictMode -Version Latest

function Test-TeikenVtSupport {
    if ($env:TEIKEN_NO_COLOR -eq '1') { return $false }

    try {
        if ($Host -and $Host.UI -and $Host.UI.SupportsVirtualTerminal) { return $true }
    } catch {
    }

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
        $teal = "`e[38;2;0;209;178m"
        $tealBright = "`e[38;2;36;235;208m"
        $orange = "`e[38;2;255;122;24m"
        $muted = "`e[38;2;138;143;152m"
        $bold = "`e[1m"
        $reset = "`e[0m"

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
