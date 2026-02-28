import app.control_plane.infra.session_repo as session_repo_module

from app.control_plane.infra.session_repo import SessionRepository
from app.control_plane.services.session_service import SessionService


def test_session_rename_and_delete(tmp_path):
    repo = SessionRepository(tmp_path / "state.db")
    service = SessionService(repo=repo)

    session = service.new_session(agent_id="agent-1", title="original")
    renamed = service.rename_session(session.id, "renamed")
    assert renamed is not None
    assert renamed.title == "renamed"

    service.append_user_message(session.id, "hello")
    deleted = service.delete_session(session.id)
    assert deleted is True
    assert service.get_transcript(session.id) == []


def test_transcript_order_uses_insert_order_when_timestamps_match(tmp_path, monkeypatch):
    repo = SessionRepository(tmp_path / "state.db")
    service = SessionService(repo=repo)
    session = service.new_session(agent_id="agent-1", title="ordered")

    monkeypatch.setattr(session_repo_module, "_utcnow", lambda: "2026-02-28T12:00:00.000000")

    first = service.append_user_message(session.id, "first")
    second = service.append_assistant_message(session.id, "second")
    third = service.append_assistant_message(session.id, "third")

    transcript = service.get_transcript(session.id)
    assert [item.id for item in transcript] == [first.id, second.id, third.id]
    assert [item.content for item in transcript] == ["first", "second", "third"]

