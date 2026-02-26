from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from app.control_plane import entrypoint
from app.control_plane.domain.models import RuntimeEntry, RuntimeStatus, RunnerType, SupervisorSnapshot
from app.control_plane.install.agent_registry import InMemoryAgentRegistry
from app.control_plane.install.boot_report import BootCheckResult, BootReport, write_boot_report
from app.control_plane.install.live_boot import BootRunResult, StartupConfig, ports_and_urls
from app.control_plane.install.runtime_snapshot import build_runtime_snapshot


def test_write_boot_report_writes_timestamp_and_latest(tmp_path: Path) -> None:
    report = BootReport(
        ts_utc="2026-02-26T08:00:00Z",
        duration_ms=1234,
        app_name="Teiken Claw",
        version="1.20.3",
        environment="test",
        git_sha="deadbeef",
        python="3.11.0",
        platform="Windows 11",
        config_redacted={"ollama_model": "qwen2.5:7b"},
        ports_and_urls={"API": "http://127.0.0.1:8000"},
        ollama={"model": "qwen2.5:7b"},
        limits={"telegram_global_msg_per_sec": 30},
        checks=[BootCheckResult(name="config", ok=True, message="ok", latency_ms=4)],
        agents=[],
        workers={"summary": "not yet available"},
        exit_code=0,
    )
    report_dir = tmp_path / "logs" / "boot"
    latest = tmp_path / "logs" / "boot_report.json"

    written = write_boot_report(report, report_dir=str(report_dir), latest_path=str(latest))

    assert Path(written).exists()
    assert latest.exists()
    data = json.loads(latest.read_text(encoding="utf-8"))
    assert data["exit_code"] == 0
    assert data["checks"][0]["name"] == "config"


def test_ports_and_urls_uses_public_override() -> None:
    cfg = StartupConfig(
        app_name="Teiken Claw",
        version="1.20.3",
        environment="local",
        git_sha="",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:7b",
        ollama_warmup=True,
        api_host="0.0.0.0",
        api_port=8080,
        dashboard_port=5173,
        public_base_url="https://app.example.com",
        strict_model_check=False,
    )
    urls = ports_and_urls(cfg)
    assert urls["API"] == "http://127.0.0.1:8080"
    assert urls["Public Base"] == "https://app.example.com"
    assert urls["Webhook"].startswith("https://app.example.com")


def test_runtime_snapshot_populates_registry(tmp_path: Path, monkeypatch) -> None:
    context = entrypoint.build_context(cli_data_dir=str(tmp_path))
    runtime = RuntimeEntry(
        agent_id="agent-1",
        status=RuntimeStatus.RUNNING,
        runner_type=RunnerType.INPROCESS,
        queued=3,
        overflow_count=0,
        last_error=None,
        last_heartbeat_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        context.runtime_supervisor,
        "snapshot",
        lambda: SupervisorSnapshot(
            dev_server_running=False,
            dev_server_url=None,
            global_inflight_ollama=0,
            max_inflight_ollama=2,
            runtimes=[runtime],
        ),
    )

    registry = InMemoryAgentRegistry()
    view = build_runtime_snapshot(context, registry)
    snapshots = registry.snapshot()

    assert snapshots
    assert snapshots[0].agent_id == "agent-1"
    assert view.limits.max_agent_queue_depth >= 1


def test_run_no_ui_writes_boot_report(tmp_path: Path, monkeypatch) -> None:
    context = entrypoint.build_context(cli_data_dir=str(tmp_path / "cp"))

    class _Status:
        running = True
        url = "http://127.0.0.1:8000"

    monkeypatch.setattr(context.runtime_supervisor.server_process_manager, "status", lambda: _Status())
    monkeypatch.setattr(context.runtime_supervisor, "start_dev_server", lambda: context.runtime_supervisor.snapshot())
    monkeypatch.setattr(entrypoint, "build_context", lambda cli_data_dir=None: context)

    import app.control_plane.install.live_boot as live_boot

    monkeypatch.setattr(
        live_boot,
        "run_plain_boot",
        lambda console, context, config: BootRunResult(
            ok=True,
            checks=[BootCheckResult(name="mock", ok=True, message="ok", latency_ms=1)],
            ollama_meta={"models": ["qwen2.5:7b"]},
        ),
    )

    runner = CliRunner()
    env = {
        "BOOT_REPORT": "1",
        "BOOT_REPORT_DIR": str(tmp_path / "logs" / "boot"),
        "BOOT_REPORT_LATEST": str(tmp_path / "logs" / "boot_report.json"),
    }
    result = runner.invoke(entrypoint.app, ["--data-dir", str(tmp_path / "cp"), "run", "--no-ui"], env=env)

    assert result.exit_code == 0
    assert (tmp_path / "logs" / "boot_report.json").exists()
