# Teiken Claw

Teiken Claw is a local-first, Windows-first AI agent platform with a **terminal-first control plane**.

Primary user journey:
`install -> setup wizard -> hatch agent -> chat`

No manual config editing is required for standard onboarding.

## Terminal-First Control Plane

Main command surface:

- `teiken` (launch dashboard TUI)
- `teiken-claw run` (install/start boot flow: checks + server + TUI)
- `teiken-claw run --no-ui` (plain boot checks + server attach/start, no TUI)
- `teiken-claw doctor`
- `teiken status`
- `teiken doctor`
- `teiken models`
- `teiken config`
- `teiken hatch`
- `teiken agents`
- `teiken chat`
- `teiken logs`
- `teiken logs --audit`
- `teiken open`
- `teiken reset`
- `teiken upgrade`
- `teiken version`

All commands support `--data-dir`. Base path precedence:
`--data-dir` > `TEIKEN_HOME` > `%LOCALAPPDATA%\TeikenClaw`.
Use `--details` on any command to print structured error details.

## Storage Semantics

All control-plane paths derive from a base directory:

- `config/` - small human-editable JSON config (`config_version`, non-secrets)
- `state/` - durable DB state (agents, sessions, metadata)
- `run/` - ephemeral runtime files (pid/lock)
- `exports/` - diagnostic bundles and reports
- `logs/` - control-plane logs

Single-instance lock file:
`<base>/run/control_plane.lock`

Safe defaults:
- new agents default to `tool_profile=safe`
- dangerous profile changes require explicit override confirmation
- first chat turn runs per-agent onboarding (user name, agent name confirmation, purpose)

## Quick Start (Windows)

### Prerequisites

- Python 3.11+
- Ollama
- Windows 10/11

### Installation

```powershell
.\scripts\setup.ps1
```

Installer flags (Phase 18):

```powershell
.\scripts\setup.ps1 -VerboseLogs
.\scripts\setup.ps1 -NoAnsi
.\scripts\setup.ps1 -SkipSmokeTests
.\scripts\setup.ps1 -CI
```

Default setup behavior:

1. Creates/updates virtual environment
2. Installs dependencies and editable package entrypoint (`teiken`)
3. Runs install-time boot UX (`teiken-claw run`) unless `-NoStart`
4. Uses plain mode (`--no-ui`) if `-NoUi` is provided

Boot reports are written to:

- Timestamped: `./logs/boot/boot_report_*.json`
- Latest pointer: `./logs/boot_report.json`

Recommended environment overrides:

```powershell
$env:TEIKEN_ENV=\"local\"
$env:OLLAMA_BASE_URL=\"http://127.0.0.1:11434\"
$env:OLLAMA_MODEL=\"qwen2.5:7b\"
$env:OLLAMA_WARMUP=\"1\"
$env:TEIKEN_API_HOST=\"0.0.0.0\"
$env:TEIKEN_API_PORT=\"8000\"
$env:TEIKEN_DASHBOARD_PORT=\"5173\"
$env:TEIKEN_PUBLIC_BASE_URL=\"http://127.0.0.1:8000\"
$env:BOOT_REPORT_DIR=\"./logs/boot\"
$env:BOOT_REPORT=\"1\"
```

### Manual Commands

```powershell
.\scripts\run_dev.ps1
teiken
```

Inside the TUI:

1. Use clear screen-specific action buttons (for example Pull Model, Validate, Hatch, Start/Stop/Restart).
2. Use `Ctrl+K` for the global command palette (fuzzy search + grouped commands).
3. Use global keys consistently:
`F1` Help, `Esc` Back, `Ctrl+R` Refresh, `Ctrl+L` Logs, `Ctrl+S` Save, `Ctrl+C` Quit.
4. Screen map:
Boot -> Dashboard / Setup Wizard -> Models / Agents / Hatch / Chat / Status / Doctor / Logs.
5. Hatched agents are agent-contextual (not raw model passthrough): chat runs with per-agent prompt, workspace context, tool profile, and loaded skills summary.
6. First chat interaction for a new agent performs onboarding questions, then transitions to normal task execution.
7. Tool side effects are trust-checked:
`<TEIKEN_TOOL_CALL>...</TEIKEN_TOOL_CALL>` is the only executable format, code fences are plain text.
8. Runtime emits and stores tool receipts (`<TEIKEN_TOOL_RESULT>...`) and chat supports `/receipts` to inspect real execution results.

## Common Tasks

| Task | Command |
|------|---------|
| Run smoke tests | `.\scripts\smoke_test.ps1` |
| Launch control plane wrapper | `.\scripts\teiken.ps1` |
| Create backup | `.\scripts\backup.ps1` |
| Install as service | `.\scripts\install_service.ps1` |
| Reset database | `.\scripts\reset_db.ps1 -Force` |

## Documentation

- [API Documentation](docs/api.md)
- [Configuration Guide](docs/config.md)
- [Installer Guide](docs/INSTALLER.md)
- [Project Status](docs/STATUS.md)
- [Specification](teiken_claw_spec.md)

## License

MIT. See [LICENSE](LICENSE).
