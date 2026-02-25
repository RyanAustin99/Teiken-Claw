# Skills package
"""
Skills module for Teiken Claw.

This module provides a declarative skill system where skills are defined
in YAML files and executed by the skill engine. Skills can be triggered
by keywords or direct invocation.

Core components:
- schema: Pydantic models for skill validation
- loader: Loads skill definitions from YAML files
- engine: Executes skill workflows
- router: Routes user messages to skills
"""

from app.skills.schema import (
    StepType,
    SkillInput,
    SkillOutput,
    SkillTrigger,
    SkillStep,
    SkillDefinition,
    SkillVersion,
    validate_skill_definition,
    validate_step_type,
)

from app.skills.loader import (
    SkillLoader,
    get_skill_loader,
    load_skill,
    load_all_skills,
)

from app.skills.engine import (
    SkillEngine,
    SkillResult,
    ExecutionContext,
    get_skill_engine,
    execute_skill,
)

from app.skills.router import (
    SkillRouter,
    SkillMatch,
    get_skill_router,
    route_intent,
)

# Global instances for dependency injection
_skill_loader: SkillLoader = None
_skill_engine: SkillEngine = None
_skill_router: SkillRouter = None


def set_skill_loader(loader: SkillLoader) -> None:
    """Set the global skill loader instance."""
    global _skill_loader
    _skill_loader = loader


def set_skill_engine(engine: SkillEngine) -> None:
    """Set the global skill engine instance."""
    global _skill_engine
    _skill_engine = engine


def set_skill_router(router: SkillRouter) -> None:
    """Set the global skill router instance."""
    global _skill_router
    _skill_router = router


def get_skill_loader() -> SkillLoader:
    """Get the global skill loader instance."""
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader


def get_skill_engine() -> SkillEngine:
    """Get the global skill engine instance."""
    global _skill_engine
    if _skill_engine is None:
        _skill_engine = SkillEngine()
    return _skill_engine


def get_skill_router() -> SkillRouter:
    """Get the global skill router instance."""
    global _skill_router
    if _skill_router is None:
        _skill_router = SkillRouter()
    return _skill_router


__all__ = [
    # Schema
    'StepType',
    'SkillInput',
    'SkillOutput',
    'SkillTrigger',
    'SkillStep',
    'SkillDefinition',
    'SkillVersion',
    'validate_skill_definition',
    'validate_step_type',
    # Loader
    'SkillLoader',
    'get_skill_loader',
    'set_skill_loader',
    'load_skill',
    'load_all_skills',
    # Engine
    'SkillEngine',
    'SkillResult',
    'ExecutionContext',
    'get_skill_engine',
    'set_skill_engine',
    'execute_skill',
    # Router
    'SkillRouter',
    'SkillMatch',
    'get_skill_router',
    'set_skill_router',
    'route_intent',
]
