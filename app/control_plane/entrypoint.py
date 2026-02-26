"""Native `teiken` CLI and TUI entrypoint."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
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
from app.control_plane.domain.models import RunnerType
from app.control_plane.infra.db_bootstrap import bootstrap_storage


console = Console()
app = typer.Typer(no_args_is_help=False, invoke_without_command=True, help="Teiken control plane")
models_app = typer.Typer(help="Model operations")
agents_app = typer.Typer(help="Agent management")
app.add_typer(models_app, name="models")
app.add_typer(agents_app, name="agents")
_CLI_DATA_DIR_OVERRIDE: Optional[str] = None


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
            cp.lock.acquire()
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
    console.print(f"Pulled model: {result['model']}")


@models_app.command("select")
def models_select(ctx: typer.Context, model_name: str) -> None:
    cp = _ctx_data(ctx)
    cp.model_service.select_default_model(model_name)
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
    if data_dir is not None:
        patch["data_dir"] = data_dir

    if patch:
        cfg = cp.config_service.save_patch(patch)
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
) -> None:
    cp = _ctx_data(ctx)
    if not name:
        name = typer.prompt("Agent name")
    if description is None:
        description = typer.prompt("Description (optional)", default="")
    agent = cp.agent_service.create_agent(
        name=name,
        description=description or None,
        model=model,
        runner_type=runner,
    )
    _run_async(cp.runtime_supervisor.start_agent(agent.id))
    session = cp.session_service.new_session(agent.id, title=f"{agent.name} session")
    console.print(f"Hatched agent: {agent.name} ({agent.id})")
    console.print(f"Session: {session.id}")
    if typer.confirm("Enter chat now?", default=True):
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
    console.print(f"Started: {entry.agent_id} -> {entry.status.value}")


@agents_app.command("stop")
def agents_stop(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    entry = _run_async(cp.runtime_supervisor.stop_agent(agent_id))
    console.print(f"Stopped: {entry.agent_id} -> {entry.status.value}")


@agents_app.command("restart")
def agents_restart(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    entry = _run_async(cp.runtime_supervisor.restart_agent(agent_id))
    console.print(f"Restarted: {entry.agent_id} -> {entry.status.value}")


@agents_app.command("default")
def agents_default_set(ctx: typer.Context, agent_id: str) -> None:
    cp = _ctx_data(ctx)
    cp.agent_service.set_default_agent(agent_id)
    console.print(f"Default agent set: {agent_id}")


@agents_app.command("delete")
def agents_delete(ctx: typer.Context, agent_id: str, yes: bool = typer.Option(False, "--yes")) -> None:
    cp = _ctx_data(ctx)
    if not yes and not typer.confirm(f"Delete agent {agent_id}?", default=False):
        raise typer.Exit(code=1)
    deleted = cp.agent_service.delete_agent(agent_id)
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
    if not patch:
        raise typer.BadParameter("No updates provided")
    updated = cp.agent_service.update_agent(agent_id, patch)
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
    console.print("Chat started. Commands: /help /exit /new /status /model /tools /clear")
    while True:
        text = typer.prompt("you")
        if not text.strip():
            continue
        cmd = text.strip().lower()
        if cmd in ("/exit", "/quit"):
            return
        if cmd == "/help":
            console.print("/help /exit /new /status /model /tools /clear")
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
        if cmd == "/clear":
            console.clear()
            continue

        try:
            response = _run_async(cp.runtime_supervisor.chat(agent_id=agent_id, session_id=session_id, message=text))
            console.print(f"assistant> {response}")
        except ControlPlaneError as exc:
            console.print(f"[red]{exc.user_message}[/red]")
        except Exception as exc:
            console.print(f"[red]Chat failed:[/red] {exc}")


@app.command("logs")
def logs_command(
    ctx: typer.Context,
    follow: bool = typer.Option(False, "--follow"),
    component: Optional[str] = typer.Option(None, "--component"),
    limit: int = typer.Option(100, "--limit"),
    export: bool = typer.Option(False, "--export"),
) -> None:
    cp = _ctx_data(ctx)
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
    console.print(f"Reset complete: {target}")


@app.command("upgrade")
def upgrade_command(ctx: typer.Context) -> None:
    cp = _ctx_data(ctx)
    result = bootstrap_storage(cp.paths)
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
    global _CLI_DATA_DIR_OVERRIDE
    argv = sys.argv
    if "--data-dir" in argv:
        idx = argv.index("--data-dir")
        if idx + 1 >= len(argv):
            typer.echo("Missing value for --data-dir")
            raise typer.Exit(code=2)
        _CLI_DATA_DIR_OVERRIDE = argv[idx + 1]
        del argv[idx : idx + 2]

    try:
        app()
    except ValidationError as exc:
        console.print(f"[red]{exc.user_message}[/red]")
        raise typer.Exit(code=2)
    except ControlPlaneError as exc:
        console.print(f"[red]{exc.user_message}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Command failed:[/red] {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    main()
