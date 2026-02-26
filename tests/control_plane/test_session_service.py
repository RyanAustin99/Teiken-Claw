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

