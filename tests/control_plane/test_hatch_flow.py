import asyncio

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.models import RuntimeStatus
from app.control_plane.tui.command_router import TuiCommandRouter


def _run(coro):
    return asyncio.run(coro)


def test_hatch_failure_keeps_agent_crashed_and_retry_is_idempotent(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    async def _fail_start(_agent_id: str):
        raise RuntimeError("start failed")

    context.runtime_supervisor.start_agent = _fail_start

    first = _run(router.execute("hatch --name crashy"))
    assert "Runtime start failed" in first.output

    created = context.agent_service.get_agent("crashy")
    assert created is not None
    assert created.status == RuntimeStatus.CRASHED

    second = _run(router.execute("hatch --name crashy --no-start"))
    assert "Using existing agent" in second.output
    assert len(context.agent_service.list_agents()) == 1


def test_hatch_success_creates_session_and_active_chat(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    result = _run(router.execute("hatch --name alpha"))
    assert "Started runtime and opened chat session" in result.output
    assert router.active_agent_id is not None
    assert router.active_session_id is not None


def test_delete_running_agent_cleans_runtime_without_crash(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    hatch = _run(router.execute("hatch --name to-delete"))
    assert "Started runtime and opened chat session" in hatch.output

    deleted = _run(router.execute("agents delete to-delete --yes"))
    assert "Deleted: to-delete" in deleted.output
    assert context.agent_service.get_agent("to-delete") is None
    snapshot = context.runtime_supervisor.snapshot()
    assert len(snapshot.runtimes) == 0


def test_delete_agent_survives_session_cleanup_failure(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    hatch = _run(router.execute("hatch --name delete-resilient"))
    assert "Started runtime and opened chat session" in hatch.output

    def _raise_cleanup(_agent_id: str) -> int:
        raise RuntimeError("db locked")

    context.session_service.delete_sessions_for_agent = _raise_cleanup

    deleted = _run(router.execute("agents delete delete-resilient --yes"))
    assert "Deleted: delete-resilient" in deleted.output
    assert context.agent_service.get_agent("delete-resilient") is None


def test_delete_agent_survives_runtime_audit_failure(tmp_path):
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    router = TuiCommandRouter(context)

    hatch = _run(router.execute("hatch --name delete-audit-failure"))
    assert "Started runtime and opened chat session" in hatch.output

    class _FailingAudit:
        def log(self, *_args, **_kwargs) -> None:
            raise RuntimeError("audit unavailable")

    context.runtime_supervisor.audit_service = _FailingAudit()

    deleted = _run(router.execute("agents delete delete-audit-failure --yes"))
    assert "Deleted: delete-audit-failure" in deleted.output
    assert context.agent_service.get_agent("delete-audit-failure") is None
