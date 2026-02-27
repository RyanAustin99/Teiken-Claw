"""Native `teiken` CLI and TUI entrypoint."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import typer
try:
    from rich.console import Console
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal env
    class Console:  # type: ignore[override]
        def print(self, *args, **kwargs) -> None:
            typer.echo(" ".join(str(arg) for arg in args))

    class Table:  # type: ignore[override]
        def __init__(self, title: str = "") -> None:
            self._lines = [title] if title else []

        def add_column(self, *_args, **_kwargs) -> None:
            return None

        def add_row(self, *args) -> None:
            self._lines.append(" | ".join(str(item) for item in args))

        def __str__(self) -> str:
            return "\n".join(self._lines)

from app import __version__
from app.control_plane.bootstrap import ControlPlaneContext, build_context
from app.control_plane.domain.errors import ControlPlaneError, SingleInstanceError, ValidationError
from app.control_plane.domain.models import RunnerType, RuntimeStatus
from app.control_plane.infra.db_bootstrap import bootstrap_storage


console = Console()
app = typer.Typer(no_args_is_help=False, invoke_without_command=True, help="Teiken control plane")
models_app = typer.Typer(help="Model operations")
agents_app = typer.Typer(help="Agent management")
app.add_typer(models_app, name="models")
app.add_typer(agents_app, name="agents")
_CLI_DATA_DIR_OVERRIDE: Optional[str] = None
_SHOW_ERROR_DETAILS: bool = False


def _ctx_data(ctx: typer.Context) -> ControlPlaneContext:
    obj = ctx.obj or {}
    cp = obj.get("cp")
    if cp is None:
        cp = build_context(cli_data_dir=obj.get("data_dir"))
        obj["cp"] = cp
        ctx.obj = obj
    return cp


def _run_async(coro):
    return asyncio.run(coro)


def _print_error(exc: ControlPlaneError) -> None:
    console.print(f"[red]{exc.user_message}[/red]")
    if _SHOW_ERROR_DETAILS and exc.details:
        console.print(f"[dim]details: {exc.details}[/dim]")


def _acquire_control_plane_lock(cp: ControlPlaneContext) -> None:
    try:
        cp.lock.acquire()
        return
    except SingleInstanceError:
        console.print("[yellow]Control plane already running[/yellow]")

    choice = typer.prompt("Choose action [exit|force unlock|open existing]", default="exit")
    normalized = choice.strip().lower()
    if normalized == "open existing":
        console.print("Open existing session is planned. Use `teiken status` for now.")
        raise typer.Exit(code=1)
    if normalized != "force unlock":
        raise typer.Exit(code=1)
    cp.lock.acquire(force_unlock=True)


def _launch_tui(cp: ControlPlaneContext) -> None:
    try:
        from app.control_plane.tui.app import TeikenControlPlaneApp

        tui = TeikenControlPlaneApp(context=cp)
        tui.run()
    except ModuleNotFoundError as exc:
        console.print(
            "TUI dependencies missing. Install with `pip install -r requirements.txt` "
            f"(details: {exc})"
        )
        raise typer.Exit(code=1)
    except Exception as exc:
        crash_path = cp.paths.logs_dir / "tui_crash.log"
        crash_path.parent.mkdir(parents=True, exist_ok=True)
        crash_path.write_text(traceback.format_exc(), encoding="utf-8")
        console.print(f"[red]TUI failed to start:[/red] {exc}")
        console.print(f"[yellow]Crash log:[/yellow] {crash_path}")
        console.print("[dim]Fallback: run with --no-ui or use `teiken status`[/dim]")
        raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="Override base data directory"),
) -> None:
    effective_data_dir = data_dir or _CLI_DATA_DIR_OVERRIDE
    ctx.obj = {"data_dir": effective_data_dir}
    if ctx.invoked_subcommand is None:
        cp = _ctx_data(ctx)
        try:
            _acquire_control_plane_lock(cp)
            _launch_tui(cp)
        except (SingleInstanceError, ValidationError):
            raise typer.Exit(code=1)
        finally:
            cp.lock.release()


@app.command("status")
def status_command(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    snapshot = cp.runtime_supervisor.snapshot()
    table = Table(title="Teiken Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Data Dir", str(cp.paths.base_dir))
    table.add_row("Dev Server", "running" if snapshot.dev_server_running else "stopped")
    table.add_row("Dev URL", snapshot.dev_server_url or "n/a")
    table.add_row(
        "Ollama Inflight",
        f"{snapshot.global_inflight_ollama}/{snapshot.max_inflight_ollama}",
    )
    table.add_row("Agents Running", str(len(snapshot.runtimes)))
    console.print(table)
    for runtime in snapshot.runtimes:
        console.print(
            f"- {runtime.agent_id}: {runtime.status.value} queued={runtime.queued} overflow={runtime.overflow_count}"
        )


@app.command("doctor")
def doctor_command(ctx: typer.Context, export: bool = typer.Option(False, "--export")) -> None:
    cp = _ctx_data(ctx)
    report = _run_async(cp.doctor_service.run_checks())
    console.print(f"[bold]Doctor overall:[/bold] {report.overall_status.value}")
    for check in report.checks:
        console.print(f"[{check.status.value}] {check.name}: {check.summary}")
        if check.suggestion:
            console.print(f"  fix: {check.suggestion}")

    if export:
        export_file = cp.paths.exports_dir / "doctor_report.txt"
        lines = [f"Doctor: {report.overall_status.value}"]
        lines.extend(f"[{check.status.value}] {check.name}: {check.summary}" for check in report.checks)
        cp.log_service.export(export_file, lines)
        console.print(f"Exported: {export_file}")


@app.command("run")
def run_command(
    ctx: typer.Context,
    no_ui: bool = typer.Option(False, "--no-ui", help="Run install bootstrap without launching the TUI."),
) -> None:
    from app.control_plane.install.agent_registry import InMemoryAgentRegistry
    from app.control_plane.install.boot_report import BootReport, write_boot_report
    from app.control_plane.install.live_boot import (
        build_console,
        build_startup_config,
        now_utc_timestamp,
        ports_and_urls,
        redact_boot_config,
        run_plain_boot,
    )
    from app.control_plane.install.runtime_snapshot import build_runtime_snapshot

    cp = _ctx_data(ctx)
    _acquire_control_plane_lock(cp)

    report_exit_code = 0
    entered_tui = False
    started_server_here = False
    started = time.monotonic()

    try:
        boot_console = build_console()
        startup_cfg = build_startup_config(cp, version=__version__)
        registry = InMemoryAgentRegistry()
        runtime_view = build_runtime_snapshot(cp, registry)
        # Stabilization: disable transient live-boot splash and go directly to LUI.
        boot_result = run_plain_boot(boot_console, context=cp, config=startup_cfg)

        report_exit_code = 0 if boot_result.ok else 1
        if boot_result.ok:
            pre_status = cp.runtime_supervisor.server_process_manager.status()
            cp.runtime_supervisor.start_dev_server()
            post_status = cp.runtime_supervisor.server_process_manager.status()
            if not pre_status.running and post_status.running:
                started_server_here = True
                console.print(f"[OK] Dev server started: {post_status.url}")
            elif pre_status.running:
                console.print(f"[OK] Dev server attached: {pre_status.url}")

        if os.getenv("BOOT_REPORT", "1") not in ("0", "false", "False"):
            report = BootReport(
                ts_utc=now_utc_timestamp(),
                duration_ms=int((time.monotonic() - started) * 1000),
                app_name=startup_cfg.app_name,
                version=startup_cfg.version,
                environment=startup_cfg.environment,
                git_sha=startup_cfg.git_sha,
                python=sys.version.split()[0],
                platform=f"{platform.system()} {platform.release()}",
                config_redacted=redact_boot_config(startup_cfg),
                ports_and_urls=ports_and_urls(startup_cfg),
                ollama={
                    "base_url": startup_cfg.ollama_base_url,
                    "model": startup_cfg.ollama_model,
                    "models_seen": boot_result.ollama_meta.get("models", []),
                },
                limits={
                    "telegram_global_msg_per_sec": runtime_view.limits.telegram_global_msg_per_sec,
                    "max_inflight_ollama_requests": runtime_view.limits.max_inflight_ollama_requests,
                    "max_agent_queue_depth": runtime_view.limits.max_agent_queue_depth,
                },
                checks=boot_result.checks,
                agents=[item.__dict__ for item in registry.snapshot()],
                workers=runtime_view.workers,
                exit_code=report_exit_code,
            )
            report_dir = os.getenv("BOOT_REPORT_DIR", "./logs/boot")
            latest_path = os.getenv("BOOT_REPORT_LATEST", "./logs/boot_report.json")
            report_path = write_boot_report(report, report_dir=report_dir, latest_path=latest_path)
            console.print(f"[muted]Boot report:[/muted] {report_path}")

        if report_exit_code != 0:
            raise typer.Exit(code=report_exit_code)

        if not no_ui:
            entered_tui = True
            _launch_tui(cp)
        else:
            console.print("[OK] run completed (no-ui/plain mode)")
    finally:
        if entered_tui and started_server_here:
            _run_async(cp.runtime_supervisor.shutdown_gracefully())
        cp.lock.release()


@models_app.command("list")
def models_list(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    models = _run_async(cp.model_service.list_models())
    default_model = cp.config_service.load().values.default_model
    console.print(f"Default model: {default_model}")
    for model in models:
        marker = "*" if model == default_model else " "
        console.print(f"{marker} {model}")


@models_app.callback(invoke_without_command=True)
def models_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        models_list(ctx)


@models_app.command("pull")
def models_pull(ctx: typer.Context, model_name: str) -> None:
    cp = _ctx_data(ctx)
    result = _run_async(
        cp.model_service.pull_model(model_name=model_name, progress_cb=lambda msg: console.print(f"  {msg}"))
    )
    cp.audit_service.log("model.pull", target=model_name, details={"progress_events": len(result.get("progress", []))}, actor="cli")
    console.print(f"Pulled model: {result['model']}")


@models_app.command("select")
def models_select(ctx: typer.Context, model_name: str) -> None:
    cp = _ctx_data(ctx)
    cp.model_service.select_default_model(model_name)
    cp.audit_service.log("model.select_default", target=model_name, details={}, actor="cli")
    console.print(f"Default model set: {model_name}")


@models_app.command("validate")
def models_validate(ctx: typer.Context, model_name: Optional[str] = None) -> None:
    cp = _ctx_data(ctx)
    result = _run_async(cp.model_service.validate_model(model_name))
    console.print(f"Validation ok={result['ok']} latency={result['latency_ms']}ms")
    console.print(result["response_preview"])


@app.command("config")
def config_command(
    ctx: typer.Context,
    ollama_endpoint: Optional[str] = typer.Option(None),
    default_model: Optional[str] = typer.Option(None),
    host: Optional[str] = typer.Option(None),
    port: Optional[int] = typer.Option(None),
    dangerous_tools: Optional[str] = typer.Option(None, "--dangerous-tools", help="Set dangerous tools: true|false"),
    data_dir: Optional[str] = typer.Option(None, help="Advanced: persist data dir in config"),
) -> None:
    cp = _ctx_data(ctx)
    patch = {}
    if ollama_endpoint is not None:
        patch["ollama_endpoint"] = ollama_endpoint
    if default_model is not None:
        patch["default_model"] = default_model
    if host is not None:
        patch["dev_server_host"] = host
    if port is not None:
        patch["dev_server_port"] = port
    if dangerous_tools is not None:
        normalized = dangerous_tools.strip().lower()
        if normalized not in {"true", "false"}:
            raise ValidationError("Invalid dangerous tools value", details={"expected": "true or false"})
        patch["dangerous_tools_enabled"] = normalized == "true"
    if data_dir is not None:
        patch["data_dir"] = data_dir

    if patch:
        cfg = cp.config_service.save_patch(patch)
        cp.audit_service.log("config.change", target="config", details={"patch_keys": sorted(patch.keys())}, actor="cli")
        if cp.config_service.requires_restart(patch.keys()):
            console.print("[yellow]Changes saved. Restart recommended.[/yellow]")
    else:
        cfg = cp.config_service.load()

    table = Table(title="Config")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column("Source")
    data = cfg.values.model_dump()
    for key, value in data.items():
        table.add_row(key, str(value), cfg.sources.get(key, "local"))
    console.print(table)


@app.command("hatch")
def hatch_command(
    ctx: typer.Context,
    name: Optional[str] = typer.Option(None),
    description: Optional[str] = typer.Option(None),
    model: Optional[str] = typer.Option(None),
    runner: RunnerType = typer.Option(RunnerType.INPROCESS),
    tool_profile: str = typer.Option("safe"),
    allow_dangerous: bool = typer.Option(False, "--allow-dangerous"),
    no_chat: bool = typer.Option(False, "--no-chat"),
) -> None:
    cp = _ctx_data(ctx)
    if not name:
        name = typer.prompt("Agent name")
    if description is None:
        description = typer.prompt("Description (optional)", default="")
    if tool_profile.strip().lower() == "dangerous" and not cp.config_service.load().values.dangerous_tools_enabled:
        raise ValidationError(
            "dangerous tool profile is disabled by config.",
            details={"hint": "Enable dangerous_tools_enabled in `teiken config` first."},
        )
    agent = cp.agent_service.create_agent(
        name=name,
        description=description or None,
        model=model,
        tool_profile=tool_profile,
        runner_type=runner,
        prompt_template_version=cp.config_service.load().values.agent_prompt_template_version,
        allow_dangerous_override=allow_dangerous,
    )
    try:
        _run_async(cp.runtime_supervisor.start_agent(agent.id))
    except Exception as exc:
        cp.agent_service.set_status(agent.id, RuntimeStatus.CRASHED, last_error=str(exc))
        console.print(f"[red]Runtime start failed:[/red] {exc}")
        console.print("Agent was kept with crashed status. Use `teiken doctor` and `teiken agents restart <id>`.")
        return
    session = cp.session_service.new_session(agent.id, title=f"{agent.name} session")
    try:
        boot_message = _run_async(
            cp.runtime_supervisor.trigger_hatch_boot(
                agent_id=agent.id,
                session_id=session.id,
                user_metadata={},
            )
        )
    except Exception as boot_exc:
        cp.agent_service.update_agent(
            agent.id,
            {"degraded_reason": f"boot_failed: {boot_exc}", "status": RuntimeStatus.DEGRADED},
        )
        console.print(f"[yellow]First message boot failed:[/yellow] {boot_exc}")
        boot_message = ""
    cp.audit_service.log(
        "agent.hatch",
        target=agent.id,
        details={"name": agent.name, "runner_type": runner.value, "tool_profile": tool_profile},
        actor="cli",
    )
    console.print(f"Hatched agent: {agent.name} ({agent.id})")
    console.print(f"Session: {session.id}")
    if boot_message:
        console.print(f"Boot: {boot_message}")
    if not no_chat and typer.confirm("Enter chat now?", default=True):
        _chat_loop(cp, agent.id, session.id)


@agents_app.callback(invoke_without_command=True)
def agents_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        agents_list(ctx)


@agents_app.command("list")
def agents_list(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    table = Table(title="Agents")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Model")
    table.add_column("Default")
    for agent in cp.agent_service.list_agents():
        table.add_row(agent.id[:8], agent.name, agent.status.value, agent.model or "(global)", "yes" if agent.is_default else "no")
    console.print(table)


@agents_app.command("start")
def agents_start(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    entry = _run_async(cp.runtime_supervisor.start_agent(agent_id))
    cp.audit_service.log("agent.start", target=agent_id, details={"status": entry.status.value}, actor="cli")
    console.print(f"Started: {entry.agent_id} -> {entry.status.value}")


@agents_app.command("stop")
def agents_stop(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    entry = _run_async(cp.runtime_supervisor.stop_agent(agent_id))
    cp.audit_service.log("agent.stop", target=agent_id, details={"status": entry.status.value}, actor="cli")
    console.print(f"Stopped: {entry.agent_id} -> {entry.status.value}")


@agents_app.command("restart")
def agents_restart(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    entry = _run_async(cp.runtime_supervisor.restart_agent(agent_id))
    cp.audit_service.log("agent.restart", target=agent_id, details={"status": entry.status.value}, actor="cli")
    console.print(f"Restarted: {entry.agent_id} -> {entry.status.value}")


@agents_app.command("default")
def agents_default_set(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    cp.agent_service.set_default_agent(agent_id)
    cp.audit_service.log("agent.set_default", target=agent_id, details={}, actor="cli")
    console.print(f"Default agent set: {agent_id}")


@agents_app.command("delete")
def agents_delete(ctx: typer.Context, agent_id: str, yes: bool = typer.Option(False, "--yes")) -> None:
    cp = _ctx_data(ctx)
    if not yes and not typer.confirm(f"Delete agent {agent_id}?", default=False):
        raise typer.Exit(code=1)
    deleted = _run_async(cp.runtime_supervisor.delete_agent(agent_id))
    console.print("Deleted" if deleted else "Agent not found")


@agents_app.command("edit")
def agents_edit(
    ctx: typer.Context,
    agent_id: str,
    name: Optional[str] = typer.Option(None),
    description: Optional[str] = typer.Option(None),
    model: Optional[str] = typer.Option(None),
    tool_profile: Optional[str] = typer.Option(None),
    max_queue_depth: Optional[int] = typer.Option(None),
    allow_dangerous: bool = typer.Option(False, "--allow-dangerous"),
) -> None:
    cp = _ctx_data(ctx)
    patch = {}
    if name is not None:
        patch["name"] = name
    if description is not None:
        patch["description"] = description
    if model is not None:
        patch["model"] = model
    if tool_profile is not None:
        patch["tool_profile"] = tool_profile
    if max_queue_depth is not None:
        patch["max_queue_depth"] = max_queue_depth
    has_user_patch = bool(patch)
    patch["_allow_dangerous_override"] = allow_dangerous
    if tool_profile and tool_profile.strip().lower() == "dangerous" and not cp.config_service.load().values.dangerous_tools_enabled:
        raise ValidationError(
            "dangerous tool profile is disabled by config.",
            details={"hint": "Enable dangerous_tools_enabled in `teiken config` first."},
        )
    if not has_user_patch:
        raise typer.BadParameter("No updates provided")
    updated = cp.agent_service.update_agent(agent_id, patch)
    cp.audit_service.log("agent.edit", target=agent_id, details={"patch_keys": sorted([k for k in patch.keys() if not k.startswith('_')])}, actor="cli")
    console.print(f"Updated {updated.name}")


@app.command("chat")
def chat_command(
    ctx: typer.Context,
    agent: str = typer.Option(..., "--agent", help="Agent id or name"),
    session: Optional[str] = typer.Option(None, "--session", help="Existing session id"),
) -> None:
    cp = _ctx_data(ctx)
    agent_record = cp.agent_service.get_agent(agent)
    if not agent_record:
        raise typer.BadParameter(f"Unknown agent: {agent}")
    if not session:
        prior = cp.session_service.list_sessions(agent_record.id, limit=1)
        if prior and typer.confirm("Continue latest session?", default=True):
            session = prior[0].id
        else:
            session = cp.session_service.new_session(agent_record.id, title=f"{agent_record.name} chat").id
    _chat_loop(cp, agent_record.id, session)


def _chat_loop(cp: ControlPlaneContext, agent_id: str, session_id: str) -> None:
    console.print("Chat started. Commands: /help /exit /new /status /model /tools /receipts /clear")
    while True:
        text = typer.prompt("you")
        if not text.strip():
            continue
        cmd = text.strip().lower()
        if cmd in ("/exit", "/quit"):
            return
        if cmd == "/help":
            console.print("/help /exit /new /status /model /tools /receipts /clear")
            continue
        if cmd == "/new":
            session_id = cp.session_service.new_session(agent_id, title="new session").id
            console.print(f"New session: {session_id}")
            continue
        if cmd == "/status":
            snapshot = cp.runtime_supervisor.snapshot()
            console.print(f"Runtimes: {len(snapshot.runtimes)} inflight={snapshot.global_inflight_ollama}")
            continue
        if cmd == "/model":
            agent = cp.agent_service.get_agent(agent_id)
            cfg = cp.config_service.load().values
            console.print(f"Model: {agent.model or cfg.default_model}")
            continue
        if cmd == "/tools":
            console.print("Tool profile view is available in agents config (safe by default).")
            continue
        if cmd.startswith("/receipts"):
            limit = 10
            parts = cmd.split()
            if len(parts) > 1 and parts[1].isdigit():
                limit = max(1, min(100, int(parts[1])))
            receipts = cp.session_service.get_tool_receipts(session_id, limit=limit)
            if not receipts:
                console.print("receipts> none")
                continue
            for item in receipts:
                if item.ok:
                    result = item.result or {}
                    path = result.get("path") if isinstance(result, dict) else None
                    bytes_written = result.get("bytes") if isinstance(result, dict) else None
                    summary = f"[TOOL] {item.tool} OK"
                    if path:
                        summary += f" -> {path}"
                    if bytes_written is not None:
                        summary += f" ({bytes_written} bytes)"
                    console.print(summary)
                else:
                    reason = item.error.get("message") if isinstance(item.error, dict) else "failed"
                    console.print(f"[TOOL] {item.tool} DENIED -> {reason}")
            continue
        if cmd == "/clear":
            console.clear()
            continue

        try:
            response = _run_async(cp.runtime_supervisor.chat(agent_id=agent_id, session_id=session_id, message=text))
            console.print(f"assistant> {response}")
        except ControlPlaneError as exc:
            _print_error(exc)
        except Exception as exc:
            console.print(f"[red]Chat failed:[/red] {exc}")


@app.command("logs")
def logs_command(
    ctx: typer.Context,
    follow: bool = typer.Option(False, "--follow"),
    component: Optional[str] = typer.Option(None, "--component"),
    limit: int = typer.Option(100, "--limit"),
    export: bool = typer.Option(False, "--export"),
    audit: bool = typer.Option(False, "--audit"),
) -> None:
    cp = _ctx_data(ctx)
    if audit:
        events = cp.audit_service.list_recent(limit=limit)
        for event in events:
            console.print(f"{event['created_at']} {event['action']} target={event['target']} details={event['details']}")
        return
    lines = cp.log_service.query(component=component, limit=limit)
    for line in lines:
        console.print(line)
    if export:
        export_file = cp.paths.exports_dir / "logs_export.txt"
        cp.log_service.export(export_file, lines)
        console.print(f"Exported logs: {export_file}")
    if follow:
        async def _follow() -> None:
            async for line in cp.log_service.follow(component=component):
                console.print(line)
        _run_async(_follow())


@app.command("open")
def open_command(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    for path in (cp.paths.base_dir, cp.paths.logs_dir):
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        console.print(f"Opened: {path}")


@app.command("reset")
def reset_command(ctx: typer.Context, yes: bool = typer.Option(False, "--yes")) -> None:
    cp = _ctx_data(ctx)
    if not yes and not typer.confirm(
        f"This wipes control-plane data under {cp.paths.base_dir}. Continue?",
        default=False,
    ):
        raise typer.Exit(code=1)
    cp.runtime_supervisor.stop_dev_server()
    target = cp.paths.base_dir
    shutil.rmtree(target, ignore_errors=True)
    cp.audit_service.log("system.reset", target=str(target), details={}, actor="cli")
    console.print(f"Reset complete: {target}")


@app.command("upgrade")
def upgrade_command(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    result = bootstrap_storage(cp.paths)
    cp.audit_service.log("system.upgrade", target=str(cp.paths.base_dir), details={"result": result.message}, actor="cli")
    console.print(result.message)


@app.command("version")
def version_command(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    cfg = cp.config_service.load().values
    console.print(f"Teiken Claw version: {__version__}")
    console.print(f"Control plane data dir: {cp.paths.base_dir}")
    console.print(f"Python: {sys.version.split()[0]}")
    console.print(f"TEIKEN_HOME: {os.getenv('TEIKEN_HOME', '<unset>')}")
    console.print(f"Default model: {cfg.default_model}")
    console.print(f"Ollama endpoint: {cfg.ollama_endpoint}")


def main() -> None:
    global _CLI_DATA_DIR_OVERRIDE, _SHOW_ERROR_DETAILS
    argv = sys.argv
    if "--data-dir" in argv:
        idx = argv.index("--data-dir")
        if idx + 1 >= len(argv):
            typer.echo("Missing value for --data-dir")
            raise SystemExit(2)
        _CLI_DATA_DIR_OVERRIDE = argv[idx + 1]
        del argv[idx : idx + 2]
    if "--details" in argv:
        _SHOW_ERROR_DETAILS = True
        argv.remove("--details")

    try:
        app()
    except ValidationError as exc:
        _print_error(exc)
        raise SystemExit(2)
    except ControlPlaneError as exc:
        _print_error(exc)
        raise SystemExit(1)
    except Exception as exc:
        console.print(f"[red]Command failed:[/red] {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
