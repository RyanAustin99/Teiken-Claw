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
