# Installer UX (Phase 18)

Teiken Claw setup now uses a cinematic installer terminal for `scripts/setup.ps1`.

## Commands

```powershell
.\scripts\setup.ps1
.\scripts\setup.ps1 -VerboseLogs
.\scripts\setup.ps1 -NoAnsi
.\scripts\setup.ps1 -SkipSmokeTests
.\scripts\setup.ps1 -CI
```

## Flags

- `-VerboseLogs`  
  Starts with verbose tail panel enabled in cinematic mode.
- `-NoAnsi`  
  Disables ANSI/truecolor rendering and forces plain output mode.
- `-SkipSmokeTests`  
  Skips step 10 (`Smoke Tests`) and marks it as skipped.
- `-CI`  
  Forces non-interactive CI output.
- `-NoStart`  
  Prevents post-setup launch actions.
- `-NoUi`  
  Preserved for compatibility in setup orchestration.

Back-compat aliases:

- `-Verbose` => `-VerboseLogs`
- `-SkipSmokeTest` => `-SkipSmokeTests`

## Output Modes

## Cinematic

- Alternate screen buffer
- Non-scrolling full frame redraw
- Animated header, progress, and step timeline
- No raw command noise in main UI
- Toggle output tail with `V`

## Plain / CI

- Deterministic single-line step updates
- No ANSI effects
- Same logs and summary artifacts

## Controls (Cinematic)

- `V` toggle verbose output tail
- `L` open install logs folder
- `Q` cancel installer (exit `130`)
- `?` help overlay

Launchpad keys after successful setup:

- `R` run `scripts/run_dev.ps1`
- `D` run doctor command
- `L` open install logs
- `B` open boot reports
- `C` copy URLs to clipboard
- `Q` quit

## Artifacts

Installer writes:

- Main log: `logs/install/setup_<timestamp>.log`
- Step logs: `logs/install/steps/<step>_<timestamp>.log`
- Summary JSON: `logs/install/setup_<timestamp>.summary.json`
- Failure bundle (on fail): `logs/install/bundles/install_fail_<timestamp>.zip`

Boot report path expected from doctor step:

- `logs/boot_report.json`
- `logs/boot/boot_report_*.json`

## Troubleshooting

If setup fails:

1. Open the main log and the failing step log listed in summary JSON.
2. Re-run with `-VerboseLogs` to inspect output tail in place.
3. Run doctor directly:

```powershell
.\venv\Scripts\python.exe -m app.control_plane.entrypoint doctor
```

If terminal rendering gets stuck:

1. Press `Q` to cancel.
2. Re-run with `-NoAnsi`.
3. Use `-CI` in non-interactive environments.
