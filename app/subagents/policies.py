"""
Sub-agent policy management for the Teiken Claw agent system.

This module provides the SubAgentPolicyManager class for managing
sub-agent policies, including defaults, validation, and inheritance.

Key Features:
    - SubAgentPolicyManager: Manages sub-agent policy creation and validation
    - Default policy configurations
    - Policy inheritance from parent to child
    - Policy validation
"""

import logging
from typing import Any, Dict, List, Optional

from app.subagents.models import SubAgentPolicy, SubAgentStatus, SubAgentTrigger

logger = logging.getLogger(__name__)


# Restricted tools that should not be available to sub-agents by default
DEFAULT_DENYLIST = [
    "exec",  # Command execution
    "run_code",  # Code execution
    "sudo",  # Sudo access
]


class SubAgentPolicyManager:
    """
    Manager for sub-agent policies.
    
    Handles policy creation, validation, and inheritance rules
    for sub-agent execution.
    
    Attributes:
        default_policy: Default policy for new sub-agents
    """
    
    def __init__(self, default_policy: Optional[SubAgentPolicy] = None):
        """
        Initialize the policy manager.
        
        Args:
            default_policy: Custom default policy (uses built-in defaults if None)
        """
        self.default_policy = default_policy or self._create_default_policy()
        logger.info(
            "SubAgentPolicyManager initialized",
            extra={
                "event": "policy_manager_init",
                "default_max_spawn_depth": self.default_policy.max_spawn_depth,
                "default_max_children": self.default_policy.max_children_per_parent,
            }
        )
    
    def _create_default_policy(self) -> SubAgentPolicy:
        """
        Create the default sub-agent policy.
        
        Returns:
            SubAgentPolicy with default constraints
        """
        return SubAgentPolicy(
            max_spawn_depth=1,
            max_children_per_parent=3,
            tool_allowlist=[],  # Empty = all tools allowed (subject to denylist)
            tool_denylist=DEFAULT_DENYLIST.copy(),
            timeout_sec=300,  # 5 minutes
            max_turns=20,
            no_scheduler_mutation=True,
            no_exec=True,
            max_output_chars=10000,
            allow_subagents=False,
        )
    
    def get_policy(
        self,
        requested_policy: Optional[SubAgentPolicy] = None,
        parent_policy: Optional[SubAgentPolicy] = None,
        trigger: SubAgentTrigger = SubAgentTrigger.MANUAL,
    ) -> SubAgentPolicy:
        """
        Get the effective policy for a new sub-agent.
        
        Applies inheritance rules based on parent policy and requested overrides.
        
        Args:
            requested_policy: Policy overrides requested by the spawner
            parent_policy: Policy of the parent agent (for inheritance)
            trigger: What triggered this sub-agent spawn
            
        Returns:
            The effective policy to use
        """
        # Start with default policy
        effective = self.default_policy.model_copy(deep=True)
        
        # Apply parent policy constraints (inheritance)
        if parent_policy:
            effective = self._apply_inheritance(effective, parent_policy)
        
        # Apply requested policy overrides
        if requested_policy:
            effective = self._apply_overrides(effective, requested_policy)
        
        # Validate the final policy
        self.validate_policy(effective, trigger)
        
        return effective
    
    def _apply_inheritance(
        self,
        policy: SubAgentPolicy,
        parent_policy: SubAgentPolicy,
    ) -> SubAgentPolicy:
        """
        Apply inheritance rules from parent policy.
        
        Child policies cannot exceed parent constraints.
        
        Args:
            policy: Policy to modify
            parent_policy: Parent's policy to inherit from
            
        Returns:
            Modified policy with inheritance applied
        """
        # Depth must not exceed parent's remaining depth
        if parent_policy.max_spawn_depth > 0:
            policy.max_spawn_depth = min(
                policy.max_spawn_depth,
                parent_policy.max_spawn_depth - 1
            )
        else:
            policy.max_spawn_depth = 0
        
        # Children limit from parent
        policy.max_children_per_parent = min(
            policy.max_children_per_parent,
            parent_policy.max_children_per_parent
        )
        
        # If parent doesn't allow subagents, child can't either
        if not parent_policy.allow_subagents:
            policy.allow_subagents = False
        
        # Inherit tool restrictions (intersection)
        if parent_policy.tool_allowlist:
            if policy.tool_allowlist:
                # Intersect both allowlists
                policy.tool_allowlist = list(
                    set(policy.tool_allowlist) & set(parent_policy.tool_allowlist)
                )
            else:
                # Inherit parent's allowlist
                policy.tool_allowlist = parent_policy.tool_allowlist.copy()
        
        # Union denylists
        if parent_policy.tool_denylist:
            combined_denylist = list(
                set(policy.tool_denylist) | set(parent_policy.tool_denylist)
            )
            policy.tool_denylist = combined_denylist
        
        # Apply stricter resource limits
        policy.timeout_sec = min(policy.timeout_sec, parent_policy.timeout_sec)
        policy.max_turns = min(policy.max_turns, parent_policy.max_turns)
        policy.max_output_chars = min(
            policy.max_output_chars,
            parent_policy.max_output_chars
        )
        
        # Inherit restriction flags (can't relax them)
        if parent_policy.no_scheduler_mutation:
            policy.no_scheduler_mutation = True
        if parent_policy.no_exec:
            policy.no_exec = True
        
        return policy
    
    def _apply_overrides(
        self,
        policy: SubAgentPolicy,
        overrides: SubAgentPolicy,
    ) -> SubAgentPolicy:
        """
        Apply requested policy overrides.
        
        Args:
            policy: Policy to modify
            overrides: Requested overrides
            
        Returns:
            Modified policy with overrides applied
        """
        # Only allow specific overrides (whitelist approach for safety)
        # These are the only fields that can be customized per-sub-agent
        allowed_overrides = [
            "max_turns",
            "timeout_sec",
            "max_output_chars",
            "task_description",  # This is not in SubAgentPolicy, handled elsewhere
        ]
        
        # Apply tool allowlist if specified
        if overrides.tool_allowlist:
            policy.tool_allowlist = overrides.tool_allowlist
        
        # Apply purpose if specified (for audit)
        # Note: Purpose is not part of SubAgentPolicy, handled in task
        
        return policy
    
    def validate_policy(
        self,
        policy: SubAgentPolicy,
        trigger: SubAgentTrigger = SubAgentTrigger.MANUAL,
    ) -> None:
        """
        Validate a sub-agent policy.
        
        Args:
            policy: Policy to validate
            trigger: What triggered this sub-agent spawn
            
        Raises:
            ValueError: If policy constraints are invalid
        """
        # Validate depth
        if policy.max_spawn_depth < 0:
            raise ValueError("max_spawn_depth cannot be negative")
        
        if policy.max_spawn_depth > 5:
            logger.warning(
                f"High max_spawn_depth: {policy.max_spawn_depth}",
                extra={"event": "high_spawn_depth"}
            )
        
        # Validate children limit
        if policy.max_children_per_parent < 1:
            raise ValueError("max_children_per_parent must be at least 1")
        
        if policy.max_children_per_parent > 10:
            logger.warning(
                f"High max_children_per_parent: {policy.max_children_per_parent}",
                extra={"event": "high_children_limit"}
            )
        
        # Validate timeout
        if policy.timeout_sec < 10:
            raise ValueError("timeout_sec must be at least 10 seconds")
        
        if policy.timeout_sec > 3600:  # 1 hour
            logger.warning(
                f"High timeout_sec: {policy.timeout_sec}",
                extra={"event": "high_timeout"}
            )
        
        # Validate max turns
        if policy.max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        
        if policy.max_turns > 100:
            logger.warning(
                f"High max_turns: {policy.max_turns}",
                extra={"event": "high_max_turns"}
            )
        
        # Validate max output
        if policy.max_output_chars < 100:
            raise ValueError("max_output_chars must be at least 100")
        
        # Validate tool lists don't conflict
        if policy.tool_allowlist and policy.tool_denylist:
            overlap = set(policy.tool_allowlist) & set(policy.tool_denylist)
            if overlap:
                raise ValueError(
                    f"Tool allowlist and denylist overlap: {overlap}"
                )
        
        # Check for dangerous tool patterns
        dangerous_tools = ["exec", "run_code", "sudo", "shell"]
        if policy.tool_allowlist:
            for tool in dangerous_tools:
                if tool in policy.tool_allowlist:
                    logger.warning(
                        f"Allowing dangerous tool: {tool}",
                        extra={
                            "event": "dangerous_tool_allowed",
                            "tool": tool,
                            "trigger": trigger,
                        }
                    )
        
        logger.debug(
            "Policy validation passed",
            extra={
                "event": "policy_validated",
                "max_spawn_depth": policy.max_spawn_depth,
                "max_turns": policy.max_turns,
            }
        )
    
    def create_restricted_policy(
        self,
        tool_allowlist: List[str],
        max_turns: int = 10,
        timeout_sec: int = 120,
    ) -> SubAgentPolicy:
        """
        Create a restricted policy with specific tool access.
        
        Args:
            tool_allowlist: List of allowed tool names
            max_turns: Maximum agent turns
            timeout_sec: Maximum execution time
            
        Returns:
            SubAgentPolicy with restricted access
        """
        policy = self.default_policy.model_copy(deep=True)
        policy.tool_allowlist = tool_allowlist
        policy.max_turns = max_turns
        policy.timeout_sec = timeout_sec
        
        self.validate_policy(policy)
        
        return policy
    
    def get_effective_tool_list(self, policy: SubAgentPolicy) -> List[str]:
        """
        Get the effective list of allowed tools from a policy.
        
        Args:
            policy: The policy to check
            
        Returns:
            List of tool names that would be allowed
        """
        # This is a placeholder - actual implementation would check
        # against the tool registry
        return policy.tool_allowlist if policy.tool_allowlist else []


# Global policy manager instance
_policy_manager: Optional[SubAgentPolicyManager] = None


def get_policy_manager() -> SubAgentPolicyManager:
    """
    Get the global policy manager instance.
    
    Returns:
        Global SubAgentPolicyManager instance
    """
    global _policy_manager
    if _policy_manager is None:
        _policy_manager = SubAgentPolicyManager()
    return _policy_manager


def set_policy_manager(manager: SubAgentPolicyManager) -> None:
    """
    Set the global policy manager instance.
    
    Args:
        manager: SubAgentPolicyManager to use globally
    """
    global _policy_manager
    _policy_manager = manager


__all__ = [
    "SubAgentPolicyManager",
    "get_policy_manager",
    "set_policy_manager",
    "DEFAULT_DENYLIST",
]
