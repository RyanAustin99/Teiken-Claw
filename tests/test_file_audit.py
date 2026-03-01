from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import FileOpAudit
from app.observability.file_audit import FileAuditContext, FileAuditLogger, runtime_file_audit_context


def test_file_audit_logger_persists_events(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[FileOpAudit.__table__])
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr("app.observability.file_audit.get_db_session", lambda: Session())

    logger = FileAuditLogger(enabled=True)
    with runtime_file_audit_context(
        FileAuditContext(agent_id="agent-1", thread_id="thread-1", session_id="session-1", correlation_id="corr-1")
    ):
        logger.log_event(
            op="write",
            path_rel="notes/today.md",
            status="success",
            bytes_in=12,
            bytes_out=12,
            latency_ms=5,
            error_code=None,
        )

    with Session() as session:
        row = session.execute(select(FileOpAudit)).scalar_one()
        assert row.agent_id == "agent-1"
        assert row.thread_id == "thread-1"
        assert row.session_id == "session-1"
        assert row.op == "write"
        assert row.path_rel == "notes/today.md"
        assert row.bytes_in == 12
        assert row.bytes_out == 12
        assert row.status == "success"
        assert row.error_code is None
        assert row.latency_ms == 5
        assert row.correlation_id == "corr-1"

