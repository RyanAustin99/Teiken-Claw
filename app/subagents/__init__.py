"""
Subagents package for Teiken Claw.

This module provides the sub-agent system for spawning constrained
child agents from parent agents.

Key Components:
    - SubAgentManager: Manages sub-agent lifecycle
    - SubAgentExecutor: Executes sub-agents with constraints
    - SubAgentSummarizer: Summarizes sub-agent results
"""

from app.subagents.models import (
    SubAgentStatus,
    SubAgentTrigger,
    SubAgentTask,
    SubAgentResult,
    SubAgentPolicy,
    SubAgentRunRecord,
)

from app.subagents.policies import (
    SubAgentPolicyManager,
    get_policy_manager,
    set_policy_manager,
    DEFAULT_DENYLIST,
)

from app.subagents.manager import (
    SubAgentQuotaExceeded,
    SubAgentDepthExceeded,
    SubAgentNotFound,
)

# These will be imported lazily to avoid circular imports
def get_subagent_manager():
    from app.subagents.manager import SubAgentManager, _manager
    if _manager is None:
        from app.subagents.manager import SubAgentManager
        return SubAgentManager()
    return _manager

def set_subagent_manager(manager):
    import app.subagents.manager as m
    m._manager = manager

def get_subagent_executor():
    from app.subagents.executor import SubAgentExecutor, _executor
    if _executor is None:
        from app.subagents.executor import SubAgentExecutor
        return SubAgentExecutor()
    return _executor

def set_subagent_executor(executor):
    import app.subagents.executor as e
    e._executor = executor

def get_subagent_summarizer():
    from app.subagents.summarizer import SubAgentSummarizer, _summarizer
    if _summarizer is None:
        from app.subagents.summarizer import SubAgentSummarizer
        return SubAgentSummarizer()
    return _summarizer

def set_subagent_summarizer(summarizer):
    import app.subagents.summarizer as s
    s._summarizer = summarizer


__all__ = [
    # Models
    "SubAgentStatus",
    "SubAgentTrigger",
    "SubAgentTask",
    "SubAgentResult",
    "SubAgentPolicy",
    "SubAgentRunRecord",
    # Policies
    "SubAgentPolicyManager",
    "get_policy_manager",
    "set_policy_manager",
    "DEFAULT_DENYLIST",
    # Exceptions
    "SubAgentQuotaExceeded",
    "SubAgentDepthExceeded",
    "SubAgentNotFound",
    # Lazy getters
    "get_subagent_manager",
    "set_subagent_manager",
    "get_subagent_executor",
    "set_subagent_executor",
    "get_subagent_summarizer",
    "set_subagent_summarizer",
]
