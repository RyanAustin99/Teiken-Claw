# Project Status

## Current Version: 1.0.0
## Last Updated: 2026-02-25
## Current Track: Recovery Program (Runnability First)

---

## Recovery Program Overview

Teiken Claw is currently in a structured recovery effort to restore:
1. reliable startup/import behavior
2. contract alignment across runtime, memory, scheduler, and observability
3. passing smoke tests and full pytest coverage

Program strategy:
1. `Runnability First`
2. milestone commits on `fix/recovery-runnability`
3. `docs/STATUS.md` as the single source of truth for plan + validation

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-25 | Recovery priority is runnability before full parity | Startup is currently blocked by import cycles and contract mismatches |
| 2026-02-25 | Use milestone commits by phase on a single recovery branch | Enables incremental review and rollback-safe checkpoints |
| 2026-02-25 | Track plan + progress in `docs/STATUS.md` only | Keeps implementation and validation history centralized |

---

## Baseline Snapshot (Phase 0)

### Baseline failures captured
1. `python -m app.main` fails with circular import:
   `app.agent.runtime <-> app.queue.workers`
2. `pytest -q` fails at collection with 6 errors:
   import cycle, missing `get_context_router`, broken observability audit model
3. `scripts/smoke_test.ps1` has script defect:
   `Write-Info` is used but not defined

### Baseline target definition for Phase 1 done
Phase 1 is complete when:
1. `python -c "import app.main"` succeeds
2. `python -m app.main` no longer fails on circular import
3. smoke import checks pass for `app.main` and `app.agent.ollama_client`

---

## Phase Checklist

- [x] Phase 0: Baseline and tracking setup
- [ ] Phase 1: Startup and import graph unblock
- [ ] Phase 2: Runtime/memory contract normalization
- [ ] Phase 3: Scheduler and control-plane alignment
- [ ] Phase 4: Observability and API route repair
- [ ] Phase 5: Queue-to-interface delivery completion
- [ ] Phase 6: Test suite rehabilitation and CI gate
- [ ] Phase 7: Tooling and documentation hardening

---

## Validation Ledger

| Date | Phase | Command | Result | Notes |
|------|-------|---------|--------|-------|
| 2026-02-25 | 0 | `.\\venv\\Scripts\\python.exe -m app.main` | FAIL | Circular import in runtime/workers path |
| 2026-02-25 | 0 | `.\\venv\\Scripts\\python.exe -m pytest -q` | FAIL | 6 collection errors (runtime/context-router/audit) |
| 2026-02-25 | 0 | `powershell -ExecutionPolicy Bypass -File scripts\\smoke_test.ps1` | FAIL | Import failures + undefined `Write-Info` |

---

## Open Risks / Deferred Items

1. Scheduler tests currently encode older contracts in several places and may require compatibility shims or targeted test updates in Phase 6.
2. Memory layer currently mixes sync and async assumptions; this can trigger secondary failures after import fixes are complete.
3. Some placeholders are still intentionally present (skills LLM/subagent integration, thread summary) and will be triaged in later phases.
