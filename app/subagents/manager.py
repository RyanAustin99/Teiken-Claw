"""
Sub-agent lifecycle management for the Teiken Claw agent system.

This module provides the SubAgentManager class for managing sub-agent
spawning, tracking, and lifecycle operations.

Key Features:
    - SubAgentManager: Manages sub-agent spawning and tracking
    - Spawn constrained child agents
    - Parent/child relationship tracking
    - Quota enforcement
    - Run record management
"""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.subagents.models import (
    SubAgentPolicy,
    SubAgentResult,
    SubAgentRunRecord,
    SubAgentStatus,
    SubAgentTask,
    SubAgentTrigger,
)
from app.subagents.policies import SubAgentPolicyManager, get_policy_manager

logger = logging.getLogger(__name__)


class SubAgentQuotaExceeded(Exception):
    """Raised when sub-agent quota is exceeded."""
    
    def __init__(self, parent_id: str, current_count: int, max_allowed: int):
        self.parent_id = parent_id
        self.current_count = current_count
        self.max_allowed = max_allowed
        super().__init__(
            f"Sub-agent quota exceeded for parent {parent_id}: "
            f"{current_count}/{max_allowed} children"
        )


class SubAgentDepthExceeded(Exception):
    """Raised when sub-agent depth limit is exceeded."""
    
    def __init__(self, parent_id: str, current_depth: int, max_depth: int):
        self.parent_id = parent_id
        self.current_depth = current_depth
        self.max_depth = max_depth
        super().__init__(
            f"Sub-agent depth exceeded for parent {parent_id}: "
            f"depth {current_depth} exceeds max {max_depth}"
        )


class SubAgentNotFound(Exception):
    """Raised when a sub-agent run is not found."""
    
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Sub-agent run not found: {run_id}")


class SubAgentManager:
    """
    Manager for sub-agent lifecycle operations.
    
    Handles spawning, tracking, and managing sub-agent runs,
    including quota enforcement and policy application.
    
    Attributes:
        policy_manager: Policy manager for sub-agent policies
    """
    
    def __init__(
        self,
        policy_manager: Optional[SubAgentPolicyManager] = None,
    ):
        """
        Initialize the sub-agent manager.
        
        Args:
            policy_manager: Policy manager (uses global if None)
        """
        self.policy_manager = policy_manager or get_policy_manager()
        self._runs: Dict[str, SubAgentRunRecord] = {}
        self._parent_children: Dict[str, List[str]] = {}  # parent_id -> [child_run_ids]
        
        logger.info(
            "SubAgentManager initialized",
            extra={"event": "subagent_manager_init"}
        )
    
    def spawn_subagent(
        self,
        parent_id: str,
        task: SubAgentTask,
        policy: Optional[SubAgentPolicy] = None,
        trigger: SubAgentTrigger = SubAgentTrigger.MANUAL,
        parent_policy: Optional[SubAgentPolicy] = None,
        trace_id: Optional[str] = None,
    ) -> SubAgentRunRecord:
        """
        Spawn a new sub-agent with the given task and policy.
        
        Validates policy constraints, creates run record, and tracks
        parent/child relationships.
        
        Args:
            parent_id: ID of the parent agent/job
            task: Task specification for the sub-agent
            policy: Policy constraints (uses default if None)
            trigger: What triggered this spawn
            parent_policy: Policy of the parent (for inheritance)
            trace_id: Optional trace ID for distributed tracing
            
        Returns:
            SubAgentRunRecord for the new sub-agent
            
        Raises:
            SubAgentQuotaExceeded: If parent has too many children
            SubAgentDepthExceeded: If depth limit would be exceeded
        """
        # Generate run ID
        run_id = f"subagent_{uuid.uuid4().hex[:12]}"
        
        # Determine depth
        depth = 1
        if parent_id in self._parent_children:
            # This parent has children, get parent's depth info
            # For simplicity, we track depth via run records
            try:
                parent_run = self.get_subagent_run(parent_id)
                if parent_run:
                    depth = parent_run.depth + 1
            except SubAgentNotFound:
                # Parent is not a sub-agent (e.g., "main")
                pass
        
        # Get effective policy
        effective_policy = self.policy_manager.get_policy(
            requested_policy=policy,
            parent_policy=parent_policy,
            trigger=trigger,
        )
        
        # Check depth limit
        if depth > effective_policy.max_spawn_depth:
            logger.warning(
                f"Sub-agent depth exceeded: parent={parent_id}, depth={depth}, "
                f"max={effective_policy.max_spawn_depth}",
                extra={
                    "event": "depth_exceeded",
                    "parent_id": parent_id,
                    "depth": depth,
                    "max_depth": effective_policy.max_spawn_depth,
                }
            )
            raise SubAgentDepthExceeded(parent_id, depth, effective_policy.max_spawn_depth)
        
        # Check children quota
        current_children = self._parent_children.get(parent_id, [])
        if len(current_children) >= effective_policy.max_children_per_parent:
            logger.warning(
                f"Sub-agent quota exceeded: parent={parent_id}, "
                f"children={len(current_children)}, "
                f"max={effective_policy.max_children_per_parent}",
                extra={
                    "event": "quota_exceeded",
                    "parent_id": parent_id,
                    "current": len(current_children),
                    "max": effective_policy.max_children_per_parent,
                }
            )
            raise SubAgentQuotaExceeded(
                parent_id,
                len(current_children),
                effective_policy.max_children_per_parent
            )
        
        # Check if sub-agents are allowed
        if not effective_policy.allow_subagents and depth > 1:
            effective_policy.allow_subagents = False
        
        # Create run record
        run_record = SubAgentRunRecord(
            run_id=run_id,
            parent_id=parent_id,
            task=task,
            policy=effective_policy,
            status=SubAgentStatus.PENDING,
            trigger=trigger,
            depth=depth,
            created_at=datetime.utcnow(),
            trace_id=trace_id or f"trace_{uuid.uuid4().hex[:16]}",
        )
        
        # Store run record
        self._runs[run_id] = run_record
        
        # Update parent children tracking
        if parent_id not in self._parent_children:
            self._parent_children[parent_id] = []
        self._parent_children[parent_id].append(run_id)
        
        # Update parent's child_run_ids
        parent_run = self._runs.get(parent_id)
        if parent_run:
            parent_run.child_run_ids.append(run_id)
        
        logger.info(
            f"Sub-agent spawned: run_id={run_id}, parent_id={parent_id}, "
            f"depth={depth}, trigger={trigger}",
            extra={
                "event": "subagent_spawned",
                "run_id": run_id,
                "parent_id": parent_id,
                "depth": depth,
                "trigger": trigger,
                "max_turns": effective_policy.max_turns,
                "timeout_sec": effective_policy.timeout_sec,
            }
        )
        
        return run_record
    
    def get_subagent_run(self, run_id: str) -> SubAgentRunRecord:
        """
        Get a sub-agent run record by ID.
        
        Args:
            run_id: ID of the run to retrieve
            
        Returns:
            SubAgentRunRecord for the requested run
            
        Raises:
            SubAgentNotFound: If run doesn't exist
        """
        run = self._runs.get(run_id)
        if not run:
            raise SubAgentNotFound(run_id)
        return run
    
    def list_subagent_runs(
        self,
        parent_id: Optional[str] = None,
        status: Optional[SubAgentStatus] = None,
    ) -> List[SubAgentRunRecord]:
        """
        List sub-agent runs, optionally filtered.
        
        Args:
            parent_id: Filter by parent ID
            status: Filter by status
            
        Returns:
            List of matching SubAgentRunRecord objects
        """
        results = []
        
        for run in self._runs.values():
            # Filter by parent
            if parent_id and run.parent_id != parent_id:
                continue
            
            # Filter by status
            if status and run.status != status:
                continue
            
            results.append(run)
        
        # Sort by created_at descending (newest first)
        results.sort(key=lambda r: r.created_at, reverse=True)
        
        return results
    
    def get_active_subagents(
        self,
        parent_id: Optional[str] = None,
    ) -> List[SubAgentRunRecord]:
        """
        Get currently running sub-agents.
        
        Args:
            parent_id: Filter by parent ID (None = all active)
            
        Returns:
            List of active SubAgentRunRecord objects
        """
        return self.list_subagent_runs(
            parent_id=parent_id,
            status=SubAgentStatus.RUNNING,
        )
    
    def cancel_subagent(self, run_id: str) -> bool:
        """
        Cancel a sub-agent run.
        
        Only pending or running sub-agents can be cancelled.
        
        Args:
            run_id: ID of the run to cancel
            
        Returns:
            True if cancelled, False if not found or already completed
        """
        run = self._runs.get(run_id)
        if not run:
            logger.warning(f"Cancel failed: run not found: {run_id}")
            return False
        
        if run.status == SubAgentStatus.PENDING:
            run.status = SubAgentStatus.CANCELLED
            run.completed_at = datetime.utcnow()
            logger.info(f"Sub-agent cancelled: run_id={run_id}")
            return True
        
        if run.status == SubAgentStatus.RUNNING:
            run.status = SubAgentStatus.CANCELLED
            run.completed_at = datetime.utcnow()
            logger.info(f"Sub-agent cancelled: run_id={run_id}")
            return True
        
        logger.info(
            f"Sub-agent cannot be cancelled (status={run.status}): run_id={run_id}"
        )
        return False
    
    def update_run_status(
        self,
        run_id: str,
        status: SubAgentStatus,
        result: Optional[SubAgentResult] = None,
        error_message: Optional[str] = None,
    ) -> SubAgentRunRecord:
        """
        Update a sub-agent run's status.
        
        Args:
            run_id: ID of the run to update
            status: New status
            result: Result if completed
            error_message: Error message if failed
            
        Returns:
            Updated SubAgentRunRecord
            
        Raises:
            SubAgentNotFound: If run doesn't exist
        """
        run = self.get_subagent_run(run_id)
        
        run.status = status
        
        if status == SubAgentStatus.RUNNING and not run.started_at:
            run.started_at = datetime.utcnow()
        
        if status in (SubAgentStatus.COMPLETED, SubAgentStatus.FAILED, SubAgentStatus.CANCELLED):
            run.completed_at = datetime.utcnow()
        
        if result:
            run.result = result
        
        if error_message:
            run.error_message = error_message
        
        logger.info(
            f"Sub-agent status updated: run_id={run_id}, status={status}",
            extra={
                "event": "subagent_status_updated",
                "run_id": run_id,
                "status": status,
                "has_result": result is not None,
            }
        )
        
        return run
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about sub-agent runs.
        
        Returns:
            Dictionary with statistics
        """
        total_runs = len(self._runs)
        
        status_counts = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        
        for run in self._runs.values():
            status_counts[run.status.value] += 1
        
        total_parents = len(self._parent_children)
        
        return {
            "total_runs": total_runs,
            "status_counts": status_counts,
            "total_parents": total_parents,
        }
    
    def clear_completed(self, older_than_hours: int = 24) -> int:
        """
        Clear completed run records older than specified hours.
        
        Args:
            older_than_hours: Clear records older than this many hours
            
        Returns:
            Number of records cleared
        """
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        to_remove = []
        
        for run_id, run in self._runs.items():
            if run.status in (
                SubAgentStatus.COMPLETED,
                SubAgentStatus.FAILED,
                SubAgentStatus.CANCELLED,
            ):
                if run.completed_at and run.completed_at < cutoff:
                    to_remove.append(run_id)
        
        for run_id in to_remove:
            del self._runs[run_id]
        
        if to_remove:
            logger.info(
                f"Cleared {len(to_remove)} old sub-agent run records"
            )
        
        return len(to_remove)


# Global manager instance
_manager: Optional[SubAgentManager] = None


def get_subagent_manager() -> SubAgentManager:
    """
    Get the global sub-agent manager instance.
    
    Returns:
        Global SubAgentManager instance
    """
    global _manager
    if _manager is None:
        _manager = SubAgentManager()
    return _manager


def set_subagent_manager(manager: SubAgentManager) -> None:
    """
    Set the global sub-agent manager instance.
    
    Args:
        manager: SubAgentManager to use globally
    """
    global _manager
    _manager = manager


__all__ = [
    "SubAgentManager",
    "SubAgentQuotaExceeded",
    "SubAgentDepthExceeded",
    "SubAgentNotFound",
    "get_subagent_manager",
    "set_subagent_manager",
]
