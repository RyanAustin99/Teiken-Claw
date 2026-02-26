import asyncio

from app.control_plane.bootstrap import build_context


async def _run_agent_lifecycle(ctx, agent_id: str):
    started = await ctx.runtime_supervisor.start_agent(agent_id)
    stopped = await ctx.runtime_supervisor.stop_agent(agent_id)
    return started, stopped


def test_programmatic_e2e_flow(tmp_path):
    ctx = build_context(cli_data_dir=str(tmp_path / "cp_data"))

    # Single-instance lock lifecycle.
    ctx.lock.acquire()
    ctx.lock.release()

    # Config save/load.
    ctx.config_service.save_patch({"default_model": "llama3.2", "configured": True})
    assert ctx.config_service.load().values.configured is True

    # Agent create/start/stop without chat call to avoid Ollama dependency.
    agent = ctx.agent_service.create_agent(name="e2e-agent")
    started, stopped = asyncio.run(_run_agent_lifecycle(ctx, agent.id))
    assert started.status.value in {"running", "degraded"}
    assert stopped.status.value in {"stopped", "stopping", "running", "degraded"}

    # Doctor should be robust even when dependencies are unavailable.
    report = asyncio.run(ctx.doctor_service.run_checks())
    assert len(report.checks) > 0
