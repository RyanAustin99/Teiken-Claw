# Soul package
"""
Soul module for Teiken Claw.
Contains agent personality, behavior patterns, and mode configurations.
"""

from app.soul.models import (
    SoulConfig,
    ModeConfig,
    GuardrailsConfig,
    GoalsConfig,
    ModeType,
    ModeState,
)

from app.soul.loader import (
    SoulLoader,
    get_soul_loader,
    load_soul,
)

from app.soul.policies import (
    SoulPolicyManager,
    get_policy_manager,
    init_policy_manager,
)

__all__ = [
    "SoulConfig",
    "ModeConfig", 
    "GuardrailsConfig",
    "GoalsConfig",
    "ModeType",
    "ModeState",
    "SoulLoader",
    "get_soul_loader",
    "load_soul",
    "SoulPolicyManager",
    "get_policy_manager",
    "init_policy_manager",
]
