# Configuration Guide

Teiken Claw configuration is loaded from environment variables (typically via `.env`).

## Startup

- Copy `.env.example` to `.env`
- Set required values before running `scripts/run_dev.ps1`

## Common Settings

- `APP_NAME` / `APP_VERSION` - Service metadata
- `ENVIRONMENT` - Deployment mode (`dev`, `staging`, `prod`)
- `DATABASE_URL` - SQLAlchemy connection string
- `TELEGRAM_BOT_TOKEN` - Telegram bot auth token
- `ADMIN_CHAT_IDS` - Comma-separated Telegram admin chat IDs

## Ollama

- `OLLAMA_BASE_URL` - Ollama endpoint (default local)
- `OLLAMA_CHAT_MODEL` - Default chat model
- `OLLAMA_EMBED_MODEL` - Default embedding model
- `OLLAMA_TIMEOUT_SEC` - Request timeout

## Scheduler

- `SCHEDULER_ENABLED` - Enables APScheduler/control-state stack

## Observability

- `AUDIT_ENABLED` - Enable audit event persistence
- `TRACING_ENABLED` - Enable trace collection

## Notes

- Runtime behavior and safe defaults are implemented in `app/config/settings.py`.
- Use `scripts/smoke_test.ps1` after config changes.
