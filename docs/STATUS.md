# Project Status

## Current Version: 1.20.0
## Last Updated: 2026-02-26
## Current Track: Terminal-First Control Plane

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

---

## 1.20.0 Program (Terminal-First Control Plane)

### Decisions Locked

1. TUI stack: `Textual + Rich`
2. Runtime model: hybrid runner (`inprocess` default, `subprocess` feature-flagged)
3. Base path default: `%LOCALAPPDATA%\\TeikenClaw`
4. Path precedence: `--data-dir` > `TEIKEN_HOME` > default
5. Control plane functions without FastAPI availability

### Phase Checklist

- [x] Phase 0: Product realignment docs
- [x] Phase 1: Native `teiken` command + TUI/CLI skeleton
- [x] Phase 1.5: Storage/DB bootstrap under control-plane base path
- [x] Phase 2: Layered config store with schema version and validation
- [x] Phase 3: Internal-service doctor/status path
- [x] Phase 4: Model detect/list/pull/select/validate services
- [x] Phase 5: Persistent agent registry with runtime policy fields
- [x] Phase 6: Hatch flow (create/config/start + chat entry)
- [x] Phase 7: Terminal chat session persistence
- [x] Phase 8: Runtime supervisor with runner abstraction and backpressure controls
- [x] Phase 9: Log query/follow/export diagnostics primitives
- [x] Phase 10: Supervisor-managed dev-server process controls
- [x] Phase 11: Setup script streamlining (`teiken` launch, optional no-start/no-ui)
- [x] Phase 12: Safety hardening and expanded audit coverage
- [x] Phase 13: Full E2E gate automation
- [x] Phase 14: 1.20.1 CI hotfix + multi-screen TUI shell/palette overhaul (`772f0c5`, `74c29e1`, `3256973`, `e81f64b`)

### Validation Ledger (1.20 workstream)

| Date | Command | Result | Notes |
|------|---------|--------|-------|
| 2026-02-26 | `python -m pytest -q tests/control_plane` | PASS | `5 passed` |
| 2026-02-26 | `python -m app.control_plane.entrypoint version --data-dir ./.tmp_teiken` | PASS | Native entrypoint and path override functional |
| 2026-02-26 | `python -m app.control_plane.entrypoint --data-dir ./.tmp_teiken status` | PASS | Status executes without FastAPI dependency |
| 2026-02-26 | `python -m pytest -q tests/control_plane tests/test_app.py` | PASS | Includes new audit, profile guard, and e2e programmatic flow tests |
| 2026-02-26 | `powershell -ExecutionPolicy Bypass -File scripts/e2e_control_plane.ps1 -SkipOllamaDependent` | PASS (targeted) | Added scripted E2E gate path for CI and local validation |
| 2026-02-26 | `python -m pytest -q` | PASS | `656 passed, 1 skipped` after 1.20.1 UI/test additions |
| 2026-02-26 | `powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1` | PASS | `Failed: 0` (one non-critical warning when API server is not running) |
| 2026-02-26 | `python -m pytest -q tests/control_plane` | PASS | `11 passed` after TUI command-bar routing integration |
| 2026-02-26 | `python -m app.control_plane.entrypoint --data-dir ./.tmp_teiken_ui status` | PASS | CLI remained stable after TUI command-router changes |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/test_app.py tests/test_throttles_import.py` | PASS | CI blocker fixed: no `Limiter` NameError when `aiolimiter` is unavailable |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/control_plane` | PASS | `14 passed` with multi-screen TUI + palette + service expansions |
| 2026-02-26 | `powershell -ExecutionPolicy Bypass -File scripts/e2e_control_plane.ps1 -SkipOllamaDependent` | PASS (targeted) | CLI/control-plane lifecycle path remains green after TUI shell changes |

### Phase 12/13 Closure Notes

1. Added local control-plane audit event persistence for state-changing actions (`config`, `models`, `hatch`, `agent lifecycle`, `upgrade`, `reset`).
2. Enforced safe-by-default tool profiles and explicit guarded dangerous overrides.
3. Added `--details` error mode for actionable failure introspection.
4. Added CI workflow gate for control-plane tests and E2E smoke: `.github/workflows/control-plane-ci.yml`.
5. Integrated in-TUI command bar with direct `teiken` command parsing, `Ctrl+P/Ctrl+K` focus, and chat-mode input fallback.
6. Replaced single-screen TUI with routed multi-screen shell, shared theme/UI kit, global key contract, and grouped fuzzy command palette.
