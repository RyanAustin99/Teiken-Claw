from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.context_builder import ContextBuilder
from app.agent.context_router import ContextRouter
from app.db.base import Base
from app.memory.audit import MemoryAuditLogger
from app.memory.audit_store import MemoryAuditStore
from app.memory.extraction_rules import MemoryExtractionRules
from app.memory.extractor import MemoryExtractor
from app.memory.memory_store_v15 import MemoryStoreV15
from app.memory.message_store import MessageStore
from app.memory.models import MemoryAuditEvent
from app.memory.thread_state import ThreadState
from app.memory.thread_store import ThreadStore


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _build_extractor(session):
    return MemoryExtractor(
        rules=MemoryExtractionRules(),
        memory_store=MemoryStoreV15(session=session),
        audit_logger=MemoryAuditLogger(store=MemoryAuditStore(session=session)),
    )


def test_extraction_identity_preferred_name(db_session):
    thread_store = ThreadStore(session=db_session)
    message_store = MessageStore(session=db_session)
    memory_store = MemoryStoreV15(session=db_session)
    extractor = _build_extractor(db_session)

    thread = thread_store.create_thread("chat-1", "A")
    message = message_store.append_message(thread.id, "user", "remember that my name is Ryan")

    result = extractor.process_user_message(
        thread_id=thread.id,
        memory_enabled=True,
        message_text=message.content,
        source_message_id=message.id,
    )
    assert result["ok"] is True

    memories = memory_store.list_memories(thread.id, limit=10)
    assert len(memories) == 1
    assert memories[0].category == "identity"
    assert memories[0].key == "preferred_name"
    assert memories[0].value == "Ryan"


def test_extraction_blocks_secret_and_audits(db_session):
    thread_store = ThreadStore(session=db_session)
    message_store = MessageStore(session=db_session)
    extractor = _build_extractor(db_session)

    thread = thread_store.create_thread("chat-2", "Security")
    message = message_store.append_message(thread.id, "user", "remember that my password is hunter2")

    result = extractor.process_user_message(
        thread_id=thread.id,
        memory_enabled=True,
        message_text=message.content,
        source_message_id=message.id,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "ERR_MEM_SECRET_DETECTED"

    blocked_events = (
        db_session.query(MemoryAuditEvent)
        .filter(MemoryAuditEvent.thread_id == thread.id, MemoryAuditEvent.status == "blocked")
        .all()
    )
    assert len(blocked_events) == 1
    assert blocked_events[0].reason_code == "ERR_MEM_SECRET_DETECTED"


def test_dedupe_updates_single_memory_item(db_session):
    thread_store = ThreadStore(session=db_session)
    message_store = MessageStore(session=db_session)
    memory_store = MemoryStoreV15(session=db_session)
    extractor = _build_extractor(db_session)

    thread = thread_store.create_thread("chat-3", "Dedupe")
    message1 = message_store.append_message(thread.id, "user", "remember that call me Ryan")
    result1 = extractor.process_user_message(
        thread_id=thread.id,
        memory_enabled=True,
        message_text=message1.content,
        source_message_id=message1.id,
    )
    assert result1["ok"] is True
    assert result1["op"] == "add"

    message2 = message_store.append_message(thread.id, "user", "remember that call me Ry")
    result2 = extractor.process_user_message(
        thread_id=thread.id,
        memory_enabled=True,
        message_text=message2.content,
        source_message_id=message2.id,
    )
    assert result2["ok"] is True
    assert result2["op"] == "update"

    memories = memory_store.list_memories(thread.id, limit=10)
    assert len(memories) == 1
    assert memories[0].key == "preferred_name"
    assert memories[0].value == "Ry"


def test_thread_isolation_for_context_injection(db_session):
    thread_store = ThreadStore(session=db_session)
    message_store = MessageStore(session=db_session)
    memory_store = MemoryStoreV15(session=db_session)
    extractor = _build_extractor(db_session)

    thread_a = thread_store.create_thread("chat-A", "A")
    thread_b = thread_store.create_thread("chat-B", "B")

    msg_a = message_store.append_message(thread_a.id, "user", "my preference is concise responses")
    extractor.process_user_message(
        thread_id=thread_a.id,
        memory_enabled=True,
        message_text=msg_a.content,
        source_message_id=msg_a.id,
    )

    msg_b = message_store.append_message(thread_b.id, "user", "my preference is verbose responses")
    extractor.process_user_message(
        thread_id=thread_b.id,
        memory_enabled=True,
        message_text=msg_b.content,
        source_message_id=msg_b.id,
    )

    builder = ContextBuilder(
        thread_state=ThreadState(session=db_session),
        memory_store=memory_store,
    )
    messages = builder.build(
        session_id="chat-A",
        thread_id=thread_a.public_id,
        recent_messages=[{"role": "user", "content": "keep tone concise"}],
    )
    system_blob = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    assert "concise" in system_blob.lower()
    assert "verbose" not in system_blob.lower()


@pytest.mark.asyncio
async def test_context_router_proposes_new_thread_without_auto_create(db_session):
    thread_store = ThreadStore(session=db_session)
    thread_store.create_thread("chat-router", "Python work")
    router = ContextRouter(thread_state=ThreadState(session=db_session))

    outcome = await router.route_message("chat-router", "new topic: gardening notes")
    assert outcome.created_new_thread is True

    # Similarity-based switch should be proposal-only.
    current = thread_store.get_or_create_active_thread("chat-router")
    outcome2 = await router.route_message("chat-router", "I need cooking recipes for pasta")
    assert outcome2.created_new_thread is False
    assert outcome2.thread_id == current.public_id
    assert outcome2.proposal is not None
