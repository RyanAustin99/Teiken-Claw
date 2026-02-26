"""Runtime snapshot adapter for install-time boot dashboard."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

from app.config.settings import get_settings
from app.control_plane.bootstrap import ControlPlaneContext
from app.control_plane.install.agent_registry import AgentRegistry, AgentSnapshot


@dataclass(frozen=True)
class ConcurrencyLimits:
    telegram_global_msg_per_sec: float
    max_inflight_ollama_requests: int
    max_agent_queue_depth: int


@dataclass(frozen=True)
class RuntimeSnapshotView:
    limits: ConcurrencyLimits
    workers: Dict[str, Any]


def build_runtime_snapshot(context: ControlPlaneContext, registry: AgentRegistry) -> RuntimeSnapshotView:
    """Populate registry from supervisor snapshot and expose limits/worker summary."""

    supervisor = context.runtime_supervisor.snapshot()
    now = time.time()

    for runtime in supervisor.runtimes:
        heartbeat = runtime.last_heartbeat_at.timestamp() if runtime.last_heartbeat_at else now
        registry.upsert(
            AgentSnapshot(
                agent_id=runtime.agent_id,
                kind="agent",
                status=runtime.status.value,
                current_task=runtime.last_error or "idle",
                queue_depth=runtime.queued,
                last_heartbeat_s=heartbeat,
                notes=f"overflow={runtime.overflow_count}",
            )
        )

    app_settings = get_settings()
    cfg = context.config_service.load().values
    limits = ConcurrencyLimits(
        telegram_global_msg_per_sec=float(getattr(app_settings, "TELEGRAM_GLOBAL_MSG_PER_SEC", 30.0) or 30.0),
        max_inflight_ollama_requests=cfg.max_inflight_ollama_requests,
        max_agent_queue_depth=cfg.max_agent_queue_depth,
    )

    workers = {
        "summary": "not yet available",
        "count": 0,
        "source": "runtime_supervisor",
    }

    return RuntimeSnapshotView(limits=limits, workers=workers)
