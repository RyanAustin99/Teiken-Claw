from __future__ import annotations

import textwrap

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.agent.prompt_assembler import PromptAssembler
from app.db.models import Thread
from app.modes.registry import ModeRegistry, get_mode_registry, set_mode_registry
from app.modes.schema import ModeDefinition
from app.persona.audit import PersonaAuditLogger
from app.persona.resolve import resolve_persona
from app.souls.registry import SoulRegistry, get_soul_registry, set_soul_registry
from app.souls.schema import SoulDefinition


def _write_seed_soul(path):
    path.write_text(
        textwrap.dedent(
            """
            name: teiken_claw_agent
            version: 1.5.0
            description: Teiken Claw default soul
            system_prompt: You are Teiken Claw.
            principles:
              - Be direct
              - Be safe
            constraints:
              allowed_tools:
                - files.read
                - files.write
                - status
                - web.search
            """
        ).strip(),
        encoding="utf-8",
    )


def _write_seed_mode(path, *, name, avoid=None):
    avoid = avoid or []
    avoid_lines = "\n".join(f"    - {item}" for item in avoid) if avoid else ""
    path.write_text(
        textwrap.dedent(
            f"""
            name: {name}
            version: 1.5.0
            description: {name} mode
            overlay_prompt: Use {name} behavior.
            tool_bias:
              avoid:
            {avoid_lines if avoid_lines else '    []'}
            output_shape:
              must_include_sections: []
              forbid_sections: []
            """
        ).strip(),
        encoding="utf-8",
    )


@pytest.fixture
def isolated_persona_registries(tmp_path):
    souls_dir = tmp_path / "souls"
    modes_dir = tmp_path / "modes"
    souls_dir.mkdir()
    modes_dir.mkdir()

    _write_seed_soul(souls_dir / "teiken_claw_agent.yaml")
    _write_seed_mode(modes_dir / "builder.yaml", name="builder")
    _write_seed_mode(modes_dir / "research.yaml", name="research", avoid=["exec"])

    previous_soul = get_soul_registry()
    previous_mode = get_mode_registry()

    soul_registry = SoulRegistry(str(souls_dir))
    mode_registry = ModeRegistry(str(modes_dir))
    set_soul_registry(soul_registry)
    set_mode_registry(mode_registry)
    try:
        yield soul_registry, mode_registry
    finally:
        set_soul_registry(previous_soul)
        set_mode_registry(previous_mode)


def test_soul_schema_defaults():
    soul = SoulDefinition.model_validate(
        {
            "name": "test_soul",
            "version": "1.0.0",
            "description": "desc",
            "system_prompt": "prompt",
        }
    )
    assert soul.style.verbosity == "med"
    assert soul.constraints.allowed_tools == ["*"]


def test_mode_schema_rejects_invalid_risk_posture():
    with pytest.raises(ValidationError):
        ModeDefinition.model_validate(
            {
                "name": "builder",
                "version": "1.5.0",
                "description": "desc",
                "overlay_prompt": "overlay",
                "risk_posture": "risky",
            }
        )


def test_registry_duplicate_ref_rejected(tmp_path):
    souls_dir = tmp_path / "souls"
    souls_dir.mkdir()
    _write_seed_soul(souls_dir / "one.yaml")
    _write_seed_soul(souls_dir / "two.yaml")
    registry = SoulRegistry(str(souls_dir))
    with pytest.raises(ValueError):
        registry.load(force=True)


def test_registry_hash_stability(isolated_persona_registries):
    soul_registry, mode_registry = isolated_persona_registries
    soul_registry.load(force=True)
    first = [s.sha256 for s in soul_registry.list_souls()]
    soul_registry.load(force=True)
    second = [s.sha256 for s in soul_registry.list_souls()]
    assert first == second

    mode_registry.load(force=True)
    m1 = [m.sha256 for m in mode_registry.list_modes()]
    mode_registry.load(force=True)
    m2 = [m.sha256 for m in mode_registry.list_modes()]
    assert m1 == m2


def test_alias_resolution_to_canonical_mode_ref(isolated_persona_registries):
    persona = resolve_persona(
        mode_ref="coder",
        soul_ref="teiken_claw_agent",
        tool_profile="balanced",
        base_file_policy={
            "max_read_bytes": 1048576,
            "max_write_bytes": 262144,
            "allowed_extensions": [".md", ".txt", ".json"],
        },
    )
    assert persona.resolved_mode_ref == "builder@1.5.0"
    assert persona.resolved_soul_ref == "teiken_claw_agent@1.5.0"


def test_persona_canonicalizes_legacy_web_search_tool_name(isolated_persona_registries):
    persona = resolve_persona(
        mode_ref="builder",
        soul_ref="teiken_claw_agent",
        tool_profile="safe",
        base_file_policy={
            "max_read_bytes": 1048576,
            "max_write_bytes": 262144,
            "allowed_extensions": [".md", ".txt", ".json"],
        },
    )
    assert persona.effective_allowed_tools is not None
    assert "web" in persona.effective_allowed_tools
    assert "web.search" not in persona.effective_allowed_tools


def test_prompt_assembler_is_deterministic():
    assembler = PromptAssembler()
    kwargs = {
        "resolved_soul_ref": "teiken_claw_agent@1.5.0",
        "resolved_mode_ref": "builder@1.5.0",
        "soul_hash": "soulhash",
        "mode_hash": "modehash",
        "soul_prompt": "You are Teiken Claw.",
        "soul_principles": ["Direct", "Safe"],
        "mode_overlay_prompt": "Execute with precision.",
        "mode_output_requirements": {"must_include_sections": [], "forbid_sections": []},
        "memory_items": [{"id": "m_1", "category": "preference", "key": "tone", "value": "concise", "updated_at": "2026-01-01T00:00:00"}],
        "transcript_messages": [{"id": "10", "role": "user", "content": "hello"}],
        "effective_tool_policy": {"allowed_tools": ["status"], "max_tool_turns": 4},
        "effective_file_policy": {"max_read_bytes": 10, "max_write_bytes": 5, "allowed_extensions": [".md"]},
        "platform_policy_version": "1.22.0",
    }
    bundle1 = assembler.assemble(**kwargs)
    bundle2 = assembler.assemble(**kwargs)
    assert bundle1.system_prompt == bundle2.system_prompt
    assert bundle1.prompt_fingerprint == bundle2.prompt_fingerprint
    assert "# Effective File Policy" in bundle1.system_prompt

    bundle3 = assembler.assemble(**{**kwargs, "resolved_mode_ref": "architect@1.5.0", "mode_hash": "architecthash"})
    assert bundle3.prompt_fingerprint != bundle1.prompt_fingerprint


def test_persona_audit_logger_bootstraps_table():
    engine = create_engine("sqlite:///:memory:", future=True)
    Thread.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        logger = PersonaAuditLogger(session=session)
        logger.log_event(
            scope_type="thread",
            thread_id=None,
            op="mode_set",
            previous_value="builder@1.5.0",
            new_value="architect@1.5.0",
            status="ok",
        )
        count = session.execute(text("SELECT COUNT(*) FROM persona_audit_events")).scalar_one()
        assert count == 1
    finally:
        session.close()
