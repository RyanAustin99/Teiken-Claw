# Project Status

## Current Version: 1.0.0
## Last Updated: 2026-02-25
## Current Track: Recovery Program (Runnability First)

---

## Recovery Program Overview

Teiken Claw recovery executed on branch `fix/recovery-runnability` using:
1. `Runnability First`
2. Milestone commits by phase
3. `docs/STATUS.md` as the single source of truth

Program outcome on 2026-02-25:
1. Startup/import path unblocked
2. Runtime/memory/scheduler/control contracts aligned
3. `pytest -q` green locally
4. Smoke script fixed and passing critical checks

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-25 | Prioritize startup/import integrity before behavior parity | Circular imports and contract breaks blocked all execution |
| 2026-02-25 | Use single long-lived recovery branch with phase milestones | Supports controlled checkpoints and review slices |
| 2026-02-25 | Keep official plan/progress in `docs/STATUS.md` only | Prevents drift across docs and ad-hoc notes |
| 2026-02-25 | Keep scheduler control API centered on `set_state/pause_jobs/pause_tools/pause_all/resume` | One control contract across API/commands/service |
| 2026-02-25 | Run async-first persistence path in runtime flow with compatibility shims where needed | Removes sync/async boundary errors without architecture rewrite |

---

## Phase Checklist

- [x] Phase 0: Baseline and tracking setup (`0075d25`)
- [x] Phase 1: Startup and import graph unblock (`cd2055c`)
- [x] Phase 2: Runtime/memory contract normalization (`6a2c2b5`)
- [x] Phase 3: Scheduler and control-plane alignment (`9f48ed9`)
- [x] Phase 4: Observability and API route repair (`39be7b5`)
- [x] Phase 5: Queue-to-interface delivery completion (`0ca8d92`)
- [x] Phase 6: Test suite rehabilitation and CI gate (`f9e2c56`)
- [x] Phase 7: Tooling and documentation hardening (this status update + tooling/doc fixes)

---

## Validation Ledger

| Date | Phase | Command | Result | Notes |
|------|-------|---------|--------|-------|
| 2026-02-25 | 0 | `.\\venv\\Scripts\\python.exe -m app.main` | FAIL | Circular import in runtime/workers path |
| 2026-02-25 | 0 | `.\\venv\\Scripts\\python.exe -m pytest -q` | FAIL | Collection errors from import/contract issues |
| 2026-02-25 | 0 | `powershell -ExecutionPolicy Bypass -File scripts\\smoke_test.ps1` | FAIL | `Write-Info` missing plus import defects |
| 2026-02-25 | 1 | `.\\venv\\Scripts\\python.exe -c "import app.main"` | PASS | Import graph no longer crashes |
| 2026-02-25 | 1 | `.\\venv\\Scripts\\python.exe -c "import app.agent.ollama_client"` | PASS | Critical agent import path valid |
| 2026-02-25 | 1 | `.\\venv\\Scripts\\python.exe -m app.main` | PASS (boot path reached) | Command entered run loop (timed out in long-running server mode) |
| 2026-02-25 | 3 | `.\\venv\\Scripts\\python.exe -m pytest -q tests/test_scheduler.py` | PASS | Scheduler/control contract suite green |
| 2026-02-25 | 4 | `.\\venv\\Scripts\\python.exe -m pytest -q tests/test_observability.py` | PASS | Observability suite green |
| 2026-02-25 | 6 | `.\\venv\\Scripts\\python.exe -m pytest -q` | PASS | `641 passed, 1 skipped` |
| 2026-02-25 | 6 | `.\\venv\\Scripts\\python.exe -c "import app.scheduler.service"` | PASS | Module import check |
| 2026-02-25 | 6 | `.\\venv\\Scripts\\python.exe -c "import app.observability.audit"` | PASS | Module import check |
| 2026-02-25 | 7 | `powershell -ExecutionPolicy Bypass -File scripts\\smoke_test.ps1` | PASS | `Failed: 0`, one warning for optional live API reachability |

---

## Open Risks / Deferred Items

1. Test run is green but still produces deprecation/resource warnings (notably `datetime.utcnow()` and some coroutine-not-awaited warnings in non-failing paths); tracked as follow-up hardening work.
2. `python -m app.main` is an intentionally long-running server entrypoint; validation uses boot-path confirmation rather than process exit.
3. Milestone PR checkpoints were prepared through commit boundaries; opening remote PRs requires repository hosting interaction outside this local execution.
