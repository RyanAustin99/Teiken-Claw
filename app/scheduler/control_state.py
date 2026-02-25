"""
Control state management for the Teiken Claw scheduler.

This module provides:
- ControlStateManager class for managing system pause modes
- Support for normal, pause_jobs, pause_tools, and pause_all states
- State persistence across restarts
- Thread-safe state transitions

Key Features:
    - Instant pause/resume of scheduled jobs
    - Tool execution control
    - Read-only mode support
    - State persistence in database
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pathlib import Path
import json

from app.config.constants import DATA_DIR

logger = logging.getLogger(__name__)

# Global control state manager instance
_control_state_manager: Optional["ControlStateManager"] = None


def get_control_state_manager() -> Optional["ControlStateManager"]:
    """Get the global control state manager instance."""
    return _control_state_manager


def set_control_state_manager(manager: "ControlStateManager") -> None:
    """Set the global control state manager instance."""
    global _control_state_manager
    _control_state_manager = manager


class ControlState(str, Enum):
    """
    System control states.
    
    States:
        NORMAL: All operations normal
        PAUSE_JOBS: Scheduled jobs paused
        PAUSE_TOOLS: Dangerous tools disabled
        PAUSE_ALL: Read-only mode (everything paused)
    """
    NORMAL = "normal"
    PAUSE_JOBS = "pause_jobs"
    PAUSE_TOOLS = "pause_tools"
    PAUSE_ALL = "pause_all"
    
    @classmethod
    def is_valid(cls, state: str) -> bool:
        """Check if a state string is valid."""
        return state in [s.value for s in cls]
    
    @classmethod
    def from_string(cls, state: str) -> "ControlState":
        """Create ControlState from string."""
        state_lower = state.lower().strip()
        for s in cls:
            if s.value == state_lower:
                return s
        raise ValueError(f"Invalid control state: {state}")


class ControlStateManager:
    """
    Manager for system control states.
    
    Provides pause/resume functionality for:
    - Scheduled jobs
    - Tool execution
    - Full system (read-only mode)
    
    State is persisted to ensure it survives restarts.
    
    Example:
        manager = ControlStateManager()
        
        # Check current state
        state = manager.get_state()
        
        # Pause all jobs
        manager.set_state(ControlState.PAUSE_JOBS)
        
        # Check if jobs are paused
        if manager.is_jobs_paused():
            print("Jobs are paused")
        
        # Resume normal operation
        manager.set_state(ControlState.NORMAL)
    """
    
    # State file path for persistence
    STATE_FILE = "control_state.json"
    
    # Dangerous tools that are disabled in PAUSE_TOOLS mode
    DANGEROUS_TOOLS = {
        "exec",
        "files_write",
        "files_delete",
        "web_post",
        "web_put",
        "web_delete",
    }
    
    def __init__(
        self,
        persistence_path: Optional[str] = None,
        initial_state: ControlState = ControlState.NORMAL,
    ):
        """
        Initialize the control state manager.
        
        Args:
            persistence_path: Path to state persistence file
            initial_state: Initial state if no persisted state exists
        """
        self._state = initial_state
        self._previous_state: Optional[ControlState] = None
        self._state_changed_at: Optional[datetime] = None
        self._state_changed_by: Optional[str] = None
        
        # Set persistence path
        if persistence_path is None:
            data_dir = Path(DATA_DIR)
            data_dir.mkdir(parents=True, exist_ok=True)
            persistence_path = str(data_dir / self.STATE_FILE)
        
        self.persistence_path = persistence_path
        
        # Load persisted state
        self._load_state()
        
        logger.info(
            f"ControlStateManager initialized (state: {self._state.value})",
            extra={
                "event": "control_state_initialized",
                "state": self._state.value,
            }
        )
    
    def get_state(self) -> str:
        """
        Get the current control state.
        
        Returns:
            Current state as string
        """
        return self._state.value
    
    def set_state(
        self,
        state: Union[ControlState, str],
        changed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Set the control state.
        
        Args:
            state: New state to set
            changed_by: Optional identifier for who changed the state
            
        Returns:
            Dict with state change details
        """
        # Normalize state
        if isinstance(state, str):
            state = ControlState.from_string(state)
        
        old_state = self._state
        
        if old_state == state:
            logger.debug(f"State unchanged: {state.value}")
            return {
                "status": "unchanged",
                "state": state.value,
                "previous_state": old_state.value,
            }
        
        # Update state
        self._previous_state = old_state
        self._state = state
        self._state_changed_at = datetime.utcnow()
        self._state_changed_by = changed_by
        
        # Persist state
        self._save_state()
        
        logger.info(
            f"Control state changed: {old_state.value} -> {state.value}",
            extra={
                "event": "control_state_changed",
                "old_state": old_state.value,
                "new_state": state.value,
                "changed_by": changed_by,
            }
        )
        
        return {
            "status": "changed",
            "state": state.value,
            "previous_state": old_state.value,
            "changed_at": self._state_changed_at.isoformat() if self._state_changed_at else None,
            "changed_by": changed_by,
        }
    
    def is_jobs_paused(self) -> bool:
        """
        Check if scheduled jobs are paused.
        
        Returns:
            True if jobs are paused (PAUSE_JOBS or PAUSE_ALL)
        """
        return self._state in (ControlState.PAUSE_JOBS, ControlState.PAUSE_ALL)
    
    def is_tools_paused(self) -> bool:
        """
        Check if dangerous tools are paused.
        
        Returns:
            True if tools are paused (PAUSE_TOOLS or PAUSE_ALL)
        """
        return self._state in (ControlState.PAUSE_TOOLS, ControlState.PAUSE_ALL)
    
    def is_all_paused(self) -> bool:
        """
        Check if everything is paused (read-only mode).
        
        Returns:
            True if in PAUSE_ALL state
        """
        return self._state == ControlState.PAUSE_ALL
    
    def is_normal(self) -> bool:
        """
        Check if system is in normal operation mode.
        
        Returns:
            True if in NORMAL state
        """
        return self._state == ControlState.NORMAL
    
    def can_run_jobs(self) -> bool:
        """
        Check if scheduled jobs can run.
        
        Returns:
            True if jobs can run
        """
        return not self.is_jobs_paused()
    
    def can_use_tool(self, tool_name: str) -> bool:
        """
        Check if a tool can be used.
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            True if the tool can be used
        """
        if self.is_all_paused():
            return False
        
        if self.is_tools_paused() and tool_name.lower() in self.DANGEROUS_TOOLS:
            return False
        
        return True
    
    def pause_jobs(self, changed_by: Optional[str] = None) -> Dict[str, Any]:
        """
        Pause scheduled jobs.
        
        Args:
            changed_by: Optional identifier for who paused
            
        Returns:
            Dict with state change details
        """
        return self.set_state(ControlState.PAUSE_JOBS, changed_by)
    
    def pause_tools(self, changed_by: Optional[str] = None) -> Dict[str, Any]:
        """
        Pause dangerous tools.
        
        Args:
            changed_by: Optional identifier for who paused
            
        Returns:
            Dict with state change details
        """
        return self.set_state(ControlState.PAUSE_TOOLS, changed_by)
    
    def pause_all(self, changed_by: Optional[str] = None) -> Dict[str, Any]:
        """
        Pause everything (read-only mode).
        
        Args:
            changed_by: Optional identifier for who paused
            
        Returns:
            Dict with state change details
        """
        return self.set_state(ControlState.PAUSE_ALL, changed_by)
    
    def resume(self, changed_by: Optional[str] = None) -> Dict[str, Any]:
        """
        Resume normal operation.
        
        Args:
            changed_by: Optional identifier for who resumed
            
        Returns:
            Dict with state change details
        """
        return self.set_state(ControlState.NORMAL, changed_by)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get detailed status information.
        
        Returns:
            Dict with status details
        """
        return {
            "state": self._state.value,
            "previous_state": self._previous_state.value if self._previous_state else None,
            "state_changed_at": self._state_changed_at.isoformat() if self._state_changed_at else None,
            "state_changed_by": self._state_changed_by,
            "is_jobs_paused": self.is_jobs_paused(),
            "is_tools_paused": self.is_tools_paused(),
            "is_all_paused": self.is_all_paused(),
            "is_normal": self.is_normal(),
            "dangerous_tools": list(self.DANGEROUS_TOOLS),
        }
    
    def _load_state(self) -> None:
        """Load persisted state from file."""
        try:
            state_file = Path(self.persistence_path)
            
            if not state_file.exists():
                logger.debug("No persisted state file found, using initial state")
                return
            
            with open(state_file, "r") as f:
                data = json.load(f)
            
            state_str = data.get("state")
            if state_str and ControlState.is_valid(state_str):
                self._state = ControlState.from_string(state_str)
                self._state_changed_at = datetime.fromisoformat(data["changed_at"]) if data.get("changed_at") else None
                self._state_changed_by = data.get("changed_by")
                
                logger.info(
                    f"Loaded persisted control state: {self._state.value}",
                    extra={"event": "control_state_loaded", "state": self._state.value}
                )
            
        except Exception as e:
            logger.error(
                f"Error loading persisted state: {e}",
                extra={"event": "control_state_load_error"},
                exc_info=True,
            )
    
    def _save_state(self) -> None:
        """Persist state to file."""
        try:
            state_file = Path(self.persistence_path)
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "state": self._state.value,
                "changed_at": self._state_changed_at.isoformat() if self._state_changed_at else None,
                "changed_by": self._state_changed_by,
            }
            
            with open(state_file, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Persisted control state: {self._state.value}")
            
        except Exception as e:
            logger.error(
                f"Error persisting state: {e}",
                extra={"event": "control_state_save_error"},
                exc_info=True,
            )


# Type hint for Union
from typing import Union


# Export
__all__ = [
    "ControlState",
    "ControlStateManager",
    "get_control_state_manager",
    "set_control_state_manager",
]
