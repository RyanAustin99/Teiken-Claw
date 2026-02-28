import pytest

pytest.importorskip("textual")

from app.control_plane.bootstrap import build_context
from app.control_plane.domain.models import RuntimeStatus
from app.control_plane.tui.screens.hatch import HatchScreen
from app.control_plane.tui.uikit import ErrorPayload


def test_hatch_recovery_message_includes_correlation_and_logs() -> None:
    payload = ErrorPayload(
        message="Boom",
        code="START_FAIL",
        details="x",
        correlation_id="cid-123",
        logs_path="C:/logs",
    )
    rendered = HatchScreen._build_recovery_message("Hatch failed while starting runtime.", payload)
    assert "Hatch failed while starting runtime." in rendered
    assert "Reason: Boom" in rendered
    assert "Recovery actions:" in rendered
    assert "code=START_FAIL" in rendered
    assert "correlation_id=cid-123" in rendered
    assert "logs=C:/logs" in rendered


def test_safe_set_status_ignores_missing_agent(tmp_path) -> None:
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    screen = HatchScreen.__new__(HatchScreen)
    screen.context = context
    # Should not raise when agent does not exist.
    screen._safe_set_status("missing-agent", RuntimeStatus.CRASHED, "boom")


def test_hatch_recovery_message_uses_details_when_unexpected() -> None:
    payload = ErrorPayload(
        message="Unexpected error",
        code="UNEXPECTED",
        details="WinError 123 invalid path",
        correlation_id="cid-456",
        logs_path="C:/logs",
    )
    rendered = HatchScreen._build_recovery_message("Hatch failed before runtime start.", payload)
    assert "Reason: WinError 123 invalid path" in rendered


def test_hatch_auto_name_generation_is_non_empty(tmp_path) -> None:
    context = build_context(cli_data_dir=str(tmp_path / "cp_data"))
    screen = HatchScreen(context)
    generated = screen._next_agent_name()
    assert generated.startswith("hatch-")
    assert len(generated) > len("hatch-")
