# API Documentation

Teiken Claw exposes HTTP endpoints via FastAPI.

## Core Endpoints

- `GET /` - Service metadata and run status
- `GET /health` - Liveness and dependency health summary
- `GET /health/ready` - Readiness check
- `GET /health/live` - Liveness check

## Status Endpoints

- `GET /status` - High-level runtime status
- `GET /api/v1/status` - Versioned status payload
- `GET /api/v1/queue/status` - Queue metrics
- `GET /api/v1/queue/dead-letter` - Dead-letter summary

## Admin Endpoints

- `POST /admin/pause` - Pause system operations
- `POST /admin/resume` - Resume system operations
- `GET /admin/state` - Current control state
- `GET /admin/jobs/dead-letter` - List dead-letter entries
- `POST /admin/jobs/dead-letter/{job_id}/replay` - Replay dead-letter job
- `DELETE /admin/jobs/dead-letter/{job_id}` - Remove dead-letter job
- `GET /admin/metrics` - Metrics snapshot
- `GET /admin/metrics/prometheus` - Prometheus-formatted metrics
- `GET /admin/audit` - Audit event query

## Notes

- Most write/admin operations assume trusted local deployment.
- Telegram command surfaces map to the same scheduler/control contracts used by HTTP routes.
- The terminal control plane (`teiken`) does **not** require FastAPI to be up for `status`, `doctor`, config, model, or agent registry operations.
- Dev-server lifecycle is supervised via control-plane runtime process management (`start/stop/restart/attach`).

## Terminal Control Plane

Top-level command interface:

- `teiken`
- `teiken-claw run`
- `teiken-claw run --no-ui`
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
- `teiken --details <command>` for expanded error details

TUI command bar:

- `teiken` launches the Textual multi-screen control plane.
- The control plane uses explicit screen actions + a global command palette.
- `Ctrl+K` opens command palette (fuzzy search) with grouped commands:
Navigation / Actions / Diagnostics / Runtime.
- Global key contract:
`F1` help, `Esc` back, `Ctrl+S` save, `Ctrl+R` refresh, `Ctrl+L` logs, `Ctrl+C` graceful quit.

Screen map:
`Boot -> Dashboard/Setup Wizard -> Models -> Agents -> Hatch -> Chat -> Status -> Doctor -> Logs`

Agent chat contract (control plane):

- Hatch creates persistent agent + runtime policy + workspace path.
- Runtime supervisor routes chat through agent-contextual conversation service (system prompt + session history), not bare single-turn model passthrough.
- First-chat onboarding is per-agent and persisted:
  - user preferred name
  - agent name confirmation/rename
  - primary purpose
- Hatch/runtime start failure keeps agent record in `crashed` status with recovery actions (`doctor`, `models`, restart/edit).
- Tool execution trust contract:
  - only `<TEIKEN_TOOL_CALL>...</TEIKEN_TOOL_CALL>` envelopes are executable
  - markdown/code-fence pseudo-calls are never executed
  - runtime emits `<TEIKEN_TOOL_RESULT>...</TEIKEN_TOOL_RESULT>` receipts
  - receipts are visible in chat and retrievable via `/receipts`.

Install-time boot UX contract:

- `teiken-claw run` uses Rich Live startup panels when TTY is available.
- Non-TTY (or `--no-ui`) uses concise plain logs and still emits boot reports.
- Boot report outputs:
  - `./logs/boot/boot_report_*.json`
  - `./logs/boot_report.json`
