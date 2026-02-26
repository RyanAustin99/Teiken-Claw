# Configuration Guide

Teiken Claw 1.20.0 uses a layered terminal-managed configuration model:

1. CLI `--data-dir` (for path override only)
2. Environment variables
3. Local persisted config (`config/user_config.json`)
4. Built-in defaults

## Base Path Resolution

Base path precedence:

1. `--data-dir`
2. `TEIKEN_HOME`
3. `%LOCALAPPDATA%\TeikenClaw`

All control-plane storage derives from that base path.

## Storage Split

- `config/` - small human-editable JSON, non-secret settings
- `state/` - durable state DB (agents, sessions, metadata)
- `run/` - lock and pid files
- `exports/` - doctor/log bundles
- `logs/` - runtime logs

## Terminal-Managed Config

Use `teiken config` or TUI Config screen to set:

- Ollama endpoint
- Default model
- Dev server host/port
- Logging level
- Workspace path
- Safety toggles
- Data directory (advanced)

Preferred UX path is the Setup Wizard screen (Step 1..6) launched on first run,
with `Ctrl+S` save behavior on editable screens.

Example:

```powershell
teiken config --default-model llama3.2 --dangerous-tools false
```

If a config change requires restart, the control plane prompts for restart.

## Secrets

Secrets remain env-driven. Local config file is non-secret and redacted in diagnostic exports.
Dangerous tool profiles are gated and require explicit override confirmation.

## Config Versioning

Persisted config includes `config_version` and is migrated by control-plane config store logic.
