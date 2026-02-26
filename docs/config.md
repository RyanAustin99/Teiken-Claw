# Configuration Guide

Teiken Claw 1.20.2 uses a layered terminal-managed configuration model:

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
- Agent prompt template version (`agent_prompt_template_version`)
- Tool loop limits:
  - `max_tool_calls_per_message` (default `3`)
  - `max_tool_turns_per_request` (default `8`)
  - `tool_call_timeout_sec` (default `30`)

Preferred UX path is the Setup Wizard screen (Step 1..6) launched on first run,
with `Ctrl+S` save behavior on editable screens.

## Install-Time Boot UX Variables

The install/start bootstrap path (`teiken-claw run`) supports:

- `TEIKEN_ENV` (default: `local`)
- `GIT_SHA` (optional metadata in boot report)
- `OLLAMA_WARMUP` (`1`/`0`)
- `STRICT_MODEL_CHECK` (`1`/`0`; default warn/continue for missing model)
- `TEIKEN_DASHBOARD_PORT` (default: `5173`)
- `TEIKEN_PUBLIC_BASE_URL` (optional URL override for port/footer panels)
- `BOOT_REPORT` (`1`/`0`; default enabled)
- `BOOT_REPORT_DIR` (default: `./logs/boot`)
- `BOOT_REPORT_LATEST` (default: `./logs/boot_report.json`)

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

## Agent Prompt and Onboarding

Hatched agents use a versioned system prompt template (`agent_prompt_template_version`) and per-agent onboarding profile fields stored in control-plane state.

On first chat turn for an onboarding-incomplete agent, the control plane asks:

1. User preferred name
2. Agent name confirmation / rename preference
3. Agent purpose

These answers are persisted per agent and reused in future sessions.

## Tool Trust Contract

- Side effects execute only from `<TEIKEN_TOOL_CALL>...</TEIKEN_TOOL_CALL>` envelopes.
- Markdown/code-fence pseudo-calls are treated as plain text.
- Runtime emits canonical tool receipts (`<TEIKEN_TOOL_RESULT>...</TEIKEN_TOOL_RESULT>`) and chat `/receipts` shows recent receipts.
