"""Rich live boot dashboard for install/start flow."""

from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from app.control_plane.bootstrap import ControlPlaneContext
from app.control_plane.install.agent_registry import AgentRegistry
from app.control_plane.install.boot_report import BootCheckResult
from app.control_plane.install.runtime_snapshot import RuntimeSnapshotView


TEIKEN_THEME = Theme(
    {
        "brand": "bold #00D1B2",
        "accent": "bold #FF7A18",
        "muted": "dim",
        "ok": "bold green",
        "warn": "bold yellow",
        "err": "bold red",
        "key": "bold",
        "val": "",
    }
)


@dataclass(frozen=True)
class StartupConfig:
    app_name: str
    version: str
    environment: str
    git_sha: str
    ollama_base_url: str
    ollama_model: str
    ollama_warmup: bool
    api_host: str
    api_port: int
    dashboard_port: int
    public_base_url: str
    strict_model_check: bool


@dataclass(frozen=True)
class BootRunResult:
    ok: bool
    checks: List[BootCheckResult]
    ollama_meta: Dict[str, Any]


def build_console() -> Console:
    return Console(theme=TEIKEN_THEME, highlight=False)


def supports_unicode(console: Console) -> bool:
    encoding = (console.encoding or "").lower()
    return "utf" in encoding


def ports_and_urls(config: StartupConfig) -> Dict[str, str]:
    host_for_local = "127.0.0.1" if config.api_host in ("0.0.0.0", "") else config.api_host
    api_local = f"http://{host_for_local}:{config.api_port}"
    dashboard_local = f"http://{host_for_local}:{config.dashboard_port}"
    public_base = config.public_base_url.strip() or api_local
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip() or f"{public_base.rstrip('/')}/webhook/telegram"

    return {
        "API": api_local,
        "Dashboard (dev)": dashboard_local,
        "Webhook": webhook_url,
        "Public Base": public_base,
        "Ollama": config.ollama_base_url,
    }


def _logo_frame(tick: int) -> Text:
    title = "TEIKEN CLAW"
    subtitle = "Install Boot | Agent Service"
    shimmer = tick % (len(title) + 8)
    text = Text()

    for index, char in enumerate(title):
        distance = abs(index - shimmer)
        if distance <= 1:
            style = "bold #FFFFFF on #00D1B2"
        elif distance <= 3:
            style = "bold #00D1B2"
        else:
            style = "brand"
        text.append(char, style=style)

    text.append("\n")
    text.append(subtitle, style="accent")
    return text


def _config_panel(config: StartupConfig) -> Panel:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="key", no_wrap=True)
    table.add_column(style="val")
    table.add_row("Version", config.version)
    table.add_row("Env", config.environment)
    if config.git_sha:
        table.add_row("Git", config.git_sha[:8])
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Platform", f"{platform.system()} {platform.release()}")
    table.add_row("Model", config.ollama_model)
    return Panel(table, title="[accent]config[/accent]", border_style="accent")


def _ports_panel(config: StartupConfig) -> Panel:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="key", no_wrap=True)
    table.add_column(style="val")
    for key, value in ports_and_urls(config).items():
        table.add_row(key, value)
    return Panel(table, title="[accent]ports & urls[/accent]", border_style="accent")


def _agents_panel(registry: Optional[AgentRegistry]) -> Panel:
    table = Table(show_header=True, header_style="key", pad_edge=False)
    table.add_column("Agent", no_wrap=True)
    table.add_column("Kind", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Queue", justify="right", no_wrap=True)
    table.add_column("Task")
    table.add_column("Heartbeat", justify="right", no_wrap=True)

    snapshots = registry.snapshot() if registry else []
    now = time.time()
    if not snapshots:
        table.add_row("-", "-", "-", "-", "-", "-")
    else:
        for item in snapshots[:12]:
            age = max(0, int(now - item.last_heartbeat_s)) if item.last_heartbeat_s else 0
            hb = f"{age}s" if item.last_heartbeat_s else "-"
            if item.status in {"running", "busy", "idle"}:
                status_style = "ok"
            elif item.status in {"starting", "degraded"}:
                status_style = "warn"
            else:
                status_style = "err"
            table.add_row(
                item.agent_id,
                item.kind,
                Text(item.status, style=status_style),
                str(item.queue_depth),
                item.current_task[:42],
                hb,
            )
    return Panel(table, title="[accent]active agents[/accent]", border_style="accent")


def _limits_panel(runtime_view: RuntimeSnapshotView) -> Panel:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="key", no_wrap=True)
    table.add_column(style="val")
    table.add_row("Telegram msg/sec", f"{runtime_view.limits.telegram_global_msg_per_sec}")
    table.add_row("Ollama inflight", str(runtime_view.limits.max_inflight_ollama_requests))
    table.add_row("Agent queue depth", str(runtime_view.limits.max_agent_queue_depth))
    table.add_row("Workers", runtime_view.workers.get("summary", "not yet available"))
    return Panel(table, title="[accent]guardrails[/accent]", border_style="accent")


def _steps_panel(step_states: List[tuple[str, str]], unicode_ok: bool) -> Panel:
    if unicode_ok:
        glyphs = {"ok": "✓", "fail": "✗", "doing": "➤", "todo": "•"}
    else:
        glyphs = {"ok": "[OK]", "fail": "[FAIL]", "doing": "[>]", "todo": "[ ]"}

    lines = Text()
    for label, state in step_states:
        marker = glyphs.get(state, glyphs["todo"])
        if state == "ok":
            lines.append(f"{marker} ", style="ok")
            lines.append(label + "\n", style="muted")
        elif state == "fail":
            lines.append(f"{marker} ", style="err")
            lines.append(label + "\n", style="err")
        elif state == "doing":
            lines.append(f"{marker} ", style="accent")
            lines.append(label + "\n", style="val")
        else:
            lines.append(f"{marker} ", style="muted")
            lines.append(label + "\n", style="muted")
    return Panel(lines, title="[accent]boot steps[/accent]", border_style="accent")


def _check_ollama_tags(config: StartupConfig) -> tuple[bool, str, List[str], int]:
    url = config.ollama_base_url.rstrip("/") + "/api/tags"
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(url)
            if response.status_code >= 400:
                latency = int((time.perf_counter() - started) * 1000)
                return False, f"Ollama responded {response.status_code}", [], latency
            data = response.json()
            models = [item.get("name", "") for item in data.get("models", []) if isinstance(item, dict)]
            latency = int((time.perf_counter() - started) * 1000)
            return True, "Ollama reachable", models, latency
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return False, f"Ollama unreachable ({exc.__class__.__name__})", [], latency


def _check_model_present(config: StartupConfig, models: List[str]) -> tuple[bool, str, int]:
    started = time.perf_counter()
    if not config.ollama_model:
        return False, "OLLAMA model not configured", int((time.perf_counter() - started) * 1000)

    if config.ollama_model in models:
        return True, f"Model present: {config.ollama_model}", int((time.perf_counter() - started) * 1000)

    base = config.ollama_model.split(":")[0]
    if any(item.split(":")[0] == base for item in models):
        return True, f"Model base present: {base}", int((time.perf_counter() - started) * 1000)

    return False, f"Model not found: {config.ollama_model}", int((time.perf_counter() - started) * 1000)


def _warmup_model(config: StartupConfig) -> tuple[bool, str, int]:
    started = time.perf_counter()
    if not config.ollama_warmup:
        return True, "Warmup disabled", int((time.perf_counter() - started) * 1000)

    url = config.ollama_base_url.rstrip("/") + "/api/generate"
    payload = {"model": config.ollama_model, "prompt": "ping", "stream": False}
    try:
        with httpx.Client(timeout=6.0) as client:
            response = client.post(url, json=payload)
            if response.status_code >= 400:
                return False, f"Warmup HTTP {response.status_code}", int((time.perf_counter() - started) * 1000)
        return True, "Model warmed", int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        return False, f"Warmup skipped ({exc.__class__.__name__})", int((time.perf_counter() - started) * 1000)


def execute_boot_checks(
    context: ControlPlaneContext,
    config: StartupConfig,
    progress_cb: Optional[Callable[[str, str], None]] = None,
) -> BootRunResult:
    checks: List[BootCheckResult] = []
    ollama_meta: Dict[str, Any] = {}

    def mark(step: str, state: str) -> None:
        if progress_cb:
            progress_cb(step, state)

    mark("config", "doing")
    started = time.perf_counter()
    try:
        context.config_service.load()
        checks.append(BootCheckResult("config_load", True, "Config loaded", int((time.perf_counter() - started) * 1000)))
        mark("config", "ok")
    except Exception as exc:
        checks.append(BootCheckResult("config_load", False, f"Config error: {exc}", int((time.perf_counter() - started) * 1000)))
        mark("config", "fail")
        return BootRunResult(ok=False, checks=checks, ollama_meta=ollama_meta)

    mark("paths", "doing")
    started = time.perf_counter()
    try:
        base_ok = context.paths.base_dir.exists()
        lock_ok = context.paths.lock_file.parent.exists()
        ok = bool(base_ok and lock_ok)
        msg = f"base={context.paths.base_dir} lock={context.paths.lock_file}"
        checks.append(BootCheckResult("path_lock_visibility", ok, msg, int((time.perf_counter() - started) * 1000)))
        mark("paths", "ok" if ok else "fail")
        if not ok:
            return BootRunResult(ok=False, checks=checks, ollama_meta=ollama_meta)
    except Exception as exc:
        checks.append(BootCheckResult("path_lock_visibility", False, str(exc), int((time.perf_counter() - started) * 1000)))
        mark("paths", "fail")
        return BootRunResult(ok=False, checks=checks, ollama_meta=ollama_meta)

    mark("ollama", "doing")
    ok_ollama, msg_ollama, models, latency_ollama = _check_ollama_tags(config)
    checks.append(BootCheckResult("ollama_reachable", ok_ollama, msg_ollama, latency_ollama))
    mark("ollama", "ok" if ok_ollama else "fail")
    if not ok_ollama:
        return BootRunResult(ok=False, checks=checks, ollama_meta=ollama_meta)

    ollama_meta["models"] = models

    mark("model", "doing")
    ok_model, msg_model, latency_model = _check_model_present(config, models)
    checks.append(BootCheckResult("ollama_model_present", ok_model, msg_model, latency_model))
    if ok_model:
        mark("model", "ok")
    elif config.strict_model_check:
        mark("model", "fail")
        return BootRunResult(ok=False, checks=checks, ollama_meta=ollama_meta)
    else:
        mark("model", "ok")

    mark("warmup", "doing")
    ok_warmup, msg_warmup, latency_warmup = _warmup_model(config)
    checks.append(BootCheckResult("ollama_warmup", ok_warmup, msg_warmup, latency_warmup))
    mark("warmup", "ok" if ok_warmup else "fail")

    mark("supervisor", "doing")
    started = time.perf_counter()
    try:
        context.runtime_supervisor.snapshot()
        checks.append(BootCheckResult("supervisor_ready", True, "Supervisor reachable", int((time.perf_counter() - started) * 1000)))
        mark("supervisor", "ok")
    except Exception as exc:
        checks.append(BootCheckResult("supervisor_ready", False, str(exc), int((time.perf_counter() - started) * 1000)))
        mark("supervisor", "fail")
        return BootRunResult(ok=False, checks=checks, ollama_meta=ollama_meta)

    return BootRunResult(ok=True, checks=checks, ollama_meta=ollama_meta)


def run_live_boot(
    console: Console,
    context: ControlPlaneContext,
    config: StartupConfig,
    runtime_view: RuntimeSnapshotView,
    registry: Optional[AgentRegistry] = None,
) -> BootRunResult:
    step_labels = {
        "config": "Loading config",
        "paths": "Resolving data + lock",
        "ollama": "Checking Ollama endpoint",
        "model": "Verifying model",
        "warmup": "Warming model",
        "supervisor": "Starting supervisor",
    }
    step_order = ["config", "paths", "ollama", "model", "warmup", "supervisor"]
    step_states = {key: "todo" for key in step_order}

    unicode_ok = supports_unicode(console)
    tick = 0

    def render(frame: int) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=7),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=10),
        )
        layout["body"].split_row(Layout(name="left", ratio=1), Layout(name="right", ratio=2))
        layout["right"].split_column(Layout(name="right_top", size=10), Layout(name="right_mid", ratio=1))

        steps = [(step_labels[key], step_states[key]) for key in step_order]
        layout["header"].update(Panel(Align.center(_logo_frame(frame)), border_style="brand"))
        layout["left"].update(_config_panel(config))
        layout["right_top"].update(_ports_panel(config))
        layout["right_mid"].update(_agents_panel(registry))
        layout["footer"].split_row(Layout(_steps_panel(steps, unicode_ok=unicode_ok), ratio=2), Layout(_limits_panel(runtime_view), ratio=1))
        return layout

    with Live(render(tick), console=console, refresh_per_second=12, transient=True) as live:
        def redraw(extra_ticks: int = 1, delay: float = 0.03) -> None:
            nonlocal tick
            for _ in range(extra_ticks):
                tick += 1
                live.update(render(tick))
                time.sleep(delay)

        def progress(step: str, state: str) -> None:
            step_states[step] = state
            redraw(2)

        redraw(4)
        result = execute_boot_checks(context, config, progress_cb=progress)
        redraw(2)

    return result


def run_plain_boot(console: Console, context: ControlPlaneContext, config: StartupConfig) -> BootRunResult:
    console.print("[bold]Teiken Claw boot[/bold]")
    result = execute_boot_checks(context, config)
    for check in result.checks:
        if check.ok:
            console.print(f"[OK] {check.name} ({check.latency_ms}ms) - {check.message}")
        else:
            console.print(f"[WARN] {check.name} ({check.latency_ms}ms) - {check.message}")
    return result


def now_utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_startup_config(context: ControlPlaneContext, version: str) -> StartupConfig:
    cfg = context.config_service.load().values
    strict = os.getenv("STRICT_MODEL_CHECK", "0") not in {"0", "false", "False"}
    warmup = os.getenv("OLLAMA_WARMUP", "1") not in {"0", "false", "False"}

    return StartupConfig(
        app_name="Teiken Claw",
        version=version,
        environment=os.getenv("TEIKEN_ENV", "local"),
        git_sha=os.getenv("GIT_SHA", ""),
        ollama_base_url=cfg.ollama_endpoint,
        ollama_model=cfg.default_model,
        ollama_warmup=warmup,
        api_host=cfg.dev_server_host,
        api_port=cfg.dev_server_port,
        dashboard_port=int(os.getenv("TEIKEN_DASHBOARD_PORT", "5173")),
        public_base_url=os.getenv("TEIKEN_PUBLIC_BASE_URL", ""),
        strict_model_check=strict,
    )


def redact_boot_config(config: StartupConfig) -> Dict[str, Any]:
    return {
        "ollama_base_url": config.ollama_base_url,
        "ollama_model": config.ollama_model,
        "api_host": config.api_host,
        "api_port": config.api_port,
        "dashboard_port": config.dashboard_port,
        "public_base_url": config.public_base_url,
        "strict_model_check": config.strict_model_check,
    }


def is_tty() -> bool:
    return bool(getattr(sys.stdout, "isatty", lambda: False)())
