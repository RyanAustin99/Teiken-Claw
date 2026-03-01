# Project Status

## Current Version: 1.22.0
## Last Updated: 2026-03-01
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

## 1.20.x Program (Terminal-First Control Plane)

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
- [x] Phase 15: 1.20.2 hatch crash recovery + agent-contextual chat runtime (this update)
- [x] Phase 16: 1.20.3 install-time dynamic boot UI + `teiken-claw run` flow
- [x] Phase 17: Trust layer + autonomy parity (canonical tool envelopes, shared executor, chat/scheduler parity, receipt/audit visibility)
- [x] Phase 18: Cinematic installer terminal v2 for `scripts/setup.ps1`
- [x] Phase 19: Natural hatch boot (LLM-generated first message, hidden identity profile, onboarding preference capture)

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
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q` | PASS | `657 passed, 1 skipped` after hatch-route crash regression fix |
| 2026-02-26 | `venv\\Scripts\\python.exe -m flake8 --select=E9,F63,F7 --show-source --statistics app/ tests/ scripts/` | PASS | CI lint gate adjusted to high-signal correctness checks |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/control_plane` | PASS | `22 passed` after onboarding/profile schema + conversation service + hatch recovery tests |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/test_app.py tests/test_telegram.py tests/test_throttles_import.py` | PASS | Import/runtime regressions remained green after control-plane runtime pivot |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q` | PASS | `664 passed, 1 skipped` with full-suite validation for 1.20.2 |
| 2026-02-26 | `venv\\Scripts\\python.exe -m compileall -q app tests scripts` | PASS | Syntax gate for CI/lint parity |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/control_plane/test_install_boot.py` | PASS | New install-boot modules + `run --no-ui` report path coverage |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/control_plane` | PASS | `27 passed` after 1.20.3 install-time boot additions |
| 2026-02-26 | `venv\\Scripts\\python.exe -m flake8 --select=E9,F63,F7 --show-source --statistics app/ tests/ scripts/` | PASS | No syntax/runtime-lint blockers |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q` | PASS | `669 passed, 1 skipped` after 1.20.3 implementation |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/control_plane` | PASS | `30 passed` after hatch-delete crash hardening + tool execution loop coverage |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q` | PASS | `672 passed, 1 skipped` after agent delete/runtime cleanup and tool envelope execution changes |
| 2026-02-26 | `venv\\Scripts\\python.exe -m flake8 --select=E9,F63,F7 --show-source --statistics app/ tests/ scripts/` | PASS | CI lint parity check remains green after control-plane fixes |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/control_plane/test_hatch_screen.py tests/control_plane/test_hatch_flow.py tests/control_plane/test_tui_shell.py` | PASS | Hatch recovery UX pass: worker error guard + correlation-id recovery messaging |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q` | PASS | `674 passed, 1 skipped` after hatch-screen hardening |
| 2026-02-26 | `venv\\Scripts\\python.exe -m flake8 --select=E9,F63,F7 --show-source --statistics app/ tests/ scripts/` | PASS | Lint/syntax gate remains green after hatch UX updates |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q tests/test_tools_protocol.py tests/test_tools_executor.py tests/test_files_tool_phase17.py tests/control_plane/test_agent_conversation_service.py tests/control_plane/test_tui_command_router.py tests/test_agent_runtime.py tests/test_agent_runtime_phase17.py` | PASS | Phase 17 parser/executor/files/chat/runtime trust gates (`36 passed, 1 skipped`) |
| 2026-02-26 | `venv\\Scripts\\python.exe -m pytest -q` | PASS | `691 passed, 1 skipped` after Phase 17 trust-layer integration |
| 2026-02-26 | `powershell -ExecutionPolicy Bypass -File scripts\\e2e_control_plane.ps1 -SkipOllamaDependent` | PASS | Control-plane smoke remained green after Phase 17 runtime/tool receipt changes |
| 2026-02-26 | `powershell -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile(...TeikenInstaller.psm1...)"` | PASS | Phase 18 installer module syntax check |
| 2026-02-26 | `powershell -NoProfile -Command "Import-Module .\\scripts\\lib\\TeikenInstaller.psm1 -Force"` | PASS | Phase 18 exported installer commands importable |
| 2026-02-26 | `powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1 -CI -SkipSmokeTests -NoStart -NoUi` | PASS | Full Phase 18 setup pipeline executed in CI/plain mode with logs + summary artifacts |
| 2026-02-27 | `$env:DEBUG='false'; python -m pytest -q tests/test_tc_profile_strip.py tests/test_boot_linter.py tests/control_plane/test_hatch_boot_integration.py` | PASS | Phase 19 gate (`8 passed`) for profile strip, boot linter, and hatch onboarding integration |

### Phase 12/13 Closure Notes

1. Added local control-plane audit event persistence for state-changing actions (`config`, `models`, `hatch`, `agent lifecycle`, `upgrade`, `reset`).
2. Enforced safe-by-default tool profiles and explicit guarded dangerous overrides.
3. Added `--details` error mode for actionable failure introspection.
4. Added CI workflow gate for control-plane tests and E2E smoke: `.github/workflows/control-plane-ci.yml`.
5. Integrated in-TUI command bar with direct `teiken` command parsing, `Ctrl+P/Ctrl+K` focus, and chat-mode input fallback.
6. Replaced single-screen TUI with routed multi-screen shell, shared theme/UI kit, global key contract, and grouped fuzzy command palette.

### 1.20.1 Hotfix Notes (Post-Merge)

1. Fixed TUI startup crash: `BootScreen` no longer assigns to reserved `Screen.log` property.
2. Restored Python 3.11 compatibility in Telegram command formatting (removed backslash from f-string expression).
3. Fixed lint issues in `tests/test_web_tool.py` (`F841`, `W293`) and wrapped long lines.
4. Added `tests/conftest.py` root-path bootstrap to stabilize `app` imports in CI runners.
5. Updated CI commands to use module execution and editable install for deterministic package resolution.
6. Fixed hatch-to-chat crash path by making screen construction lazy in `TeikenControlPlaneApp._build_screen` (no eager construction of unrelated screens).
7. Added regression coverage to enforce lazy screen construction during route transitions.
8. Fixed Windows `cp1252` terminal crash path by removing non-ASCII status glyphs from TUI and normalizing status markers to ASCII-safe tokens (`[OK]`, `[WARN]`, `[FAIL]`, `[WAIT]`).
9. Added `sanitize_terminal_text(...)` for dynamic TUI output safety and regression test coverage for ASCII-only TUI source literals.
10. Fixed CI build job dependency gap by installing `build` before `python -m build` in `.github/workflows/ci.yml`.
11. Corrected CI workflow placement so `pip install build` runs in the `build` job (not `lint`).

### 1.20.2 Hatch Recovery + Agent Skeleton Notes

1. Added per-agent onboarding/profile persistence fields and session onboarding status tracking in control-plane state.
2. Added versioned hatched-agent system prompt template at `app/control_plane/prompts/hatched_agent_system_prompt.md`.
3. Added `AgentPromptTemplateService` and `AgentConversationService` to build agent-contextual chat with system prompt, workspace, tools, and skills context.
4. Replaced control-plane direct model passthrough path by routing `RuntimeSupervisor.chat(...)` through conversation service.
5. Hardened hatch execution path with idempotent in-flight guard, failure isolation, and explicit `crashed` status preservation on startup errors.
6. Added crash-safe UI/command error presentation with correlation IDs and log-path hints via `uikit` mapping.
7. Added regression coverage:
   - onboarding state machine and prompt composition
   - hatch failure to `crashed` + idempotent retry
   - chat path enforcement of conversation service (no direct fallback)
8. Added strict terminal chat tool execution contract:
   - only execute `<TEIKEN_TOOL_CALL>{...}</TEIKEN_TOOL_CALL>` envelopes
   - ignore markdown code-fence pseudo-calls
   - enforce workspace-relative paths with traversal protection
9. Added runtime-safe agent deletion flow through `RuntimeSupervisor.delete_agent(...)`:
   - stops runner best-effort
   - clears runtime state + sessions
   - deletes agent record and records audit event
10. Added transcript-level tool receipts and regression tests for:
   - real file creation from tool envelope
   - no execution for markdown-fence tool text
   - delete-running-agent path not crashing TUI/runtime
11. Added hatch UX hardening pass:
   - unified recovery messages with actionable buttons and correlation metadata
   - app-level worker error guard to keep TUI alive on background action failures
   - safe status-update fallback during retry paths to avoid secondary crashes

### 1.20.3 Install-Time Dynamic Boot Notes

1. Added `teiken-claw` console-script alias while keeping `teiken` as canonical.
2. Added `teiken run` / `teiken-claw run` command:
   - TTY mode: Rich Live startup panels + model checks + server attach/start + TUI launch.
   - Non-TTY or `--no-ui`: concise plain boot logs + server attach/start without Textual launch.
3. Added install boot modules under `app/control_plane/install/`:
   - `agent_registry.py`
   - `runtime_snapshot.py`
   - `live_boot.py`
   - `boot_report.py`
4. Added boot report outputs:
   - timestamped report in `./logs/boot/boot_report_*.json`
   - latest pointer in `./logs/boot_report.json`
5. Setup script now launches install/start flow via `teiken-claw run` (or fallback to module invocation), honoring `-NoStart` and `-NoUi`.
6. Added guardrail visibility for install boot panel/report:
   - Telegram global msg/sec (30 default baseline)
   - max inflight Ollama requests
   - max agent queue depth
7. Model presence default policy is warn/continue; strict fail mode available via `STRICT_MODEL_CHECK=1`.

### 1.20.4 Phase 17 Trust Layer Notes

1. Added canonical tool protocol module (`app/tools/protocol.py`) with strict `<TEIKEN_TOOL_CALL>` parsing and `<TEIKEN_TOOL_RESULT>` receipts.
2. Added shared executor (`app/tools/executor.py`) enforcing:
   - tool existence checks
   - profile permissions
   - control-state pause checks
   - timeouts and bounded calls per model turn
   - structured audit events (`tool_call_detected/denied/started/succeeded/failed`).
3. Added shared loop orchestration (`app/tools/loop.py`) and routed both:
   - control-plane conversation runtime
   - backend/scheduler queue runtime (`app/agent/runtime.py`)
   through the same parser/executor/receipt contract.
4. Canonical files tools are now registered with stable names:
   - `files.write`
   - `files.read`
   - `files.list`
   - `files.exists`
   while legacy `files` action API remains for compatibility.
5. Files trust contract now enforces workspace-relative path sandboxing and runtime-generated receipts (`path`, `bytes`, `sha256`, `created_at`).
6. Chat receipt visibility improved:
   - TUI chat transcript renders `[TOOL] ...` summaries
   - `/receipts` command added (CLI/TUI chat flows)
   - optional `/verbose` toggle shows full receipt JSON in TUI chat.
7. Prompt contract updated to explicitly forbid fake side-effect claims without runtime receipts and to ban code-fence pseudo tool calls.

### 1.4.0 Phase 18 Cinematic Installer Notes

1. Added dedicated installer module `scripts/lib/TeikenInstaller.psm1` with:
   - shared installer state model
   - alternate-screen renderer with animation hooks
   - quiet `.NET Process` runner
   - step orchestration and summary artifact generation
   - launchpad controls and cancellation handling.
2. Rewrote `scripts/setup.ps1` into a thin orchestrator over 12 defined installer steps.
3. Added branded helper script `scripts/_branding.ps1` for reusable terminal logo assets.
4. Added installer docs at `docs/INSTALLER.md`.
5. Added explicit ignore patterns for installer/boot logs in `.gitignore`.

### 1.20.5 Phase 19 Natural Hatch Boot Notes

1. Added natural fresh-boot orchestration with `HatchBootService` + `RuntimeSupervisor.trigger_hatch_boot(...)`.
2. Added strict hidden identity block handling (`<tc_profile>...</tc_profile>`) with safe strip before user-visible sending.
3. Added first-message linter and rewrite guardrails (`boot_linter`) for:
   - forbidden meta phrases
   - no checklist/list formatting
   - max words
   - max questions.
4. Added onboarding identity state and profile fields on control-plane agents:
   - `is_fresh`
   - `onboarding_state`
   - `profile_json`
   - `boot_directives`
   - `degraded_reason`.
5. Added onboarding preference extraction flow and persistence into memory scopes (`AGENT_SELF`, `USER_PREFS`) with compatibility-safe storage updates.
6. Added Telegram identity lifecycle commands and routing:
   - `/hatch`
   - `/identity`
   - `/rename <name>`
   - `/onboard`.
7. Added regression coverage for the Phase 19 contract:
   - `tests/test_tc_profile_strip.py`
   - `tests/test_boot_linter.py`
   - `tests/control_plane/test_hatch_boot_integration.py`.
