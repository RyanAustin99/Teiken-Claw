from app.control_plane.infra.audit_repo import ControlPlaneAuditRepository
from app.control_plane.services.audit_service import AuditService


def test_audit_service_records_events(tmp_path):
    repo = ControlPlaneAuditRepository(tmp_path / "state.db")
    service = AuditService(repo)

    service.log("config.change", target="config", details={"key": "default_model"}, actor="test")
    service.log("agent.start", target="agent-1", details={"status": "running"}, actor="test")

    rows = service.list_recent(limit=10)
    assert len(rows) >= 2
    assert rows[0]["action"] in {"agent.start", "config.change"}

