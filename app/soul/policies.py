"""
Soul behavior policies - manages policy decisions and mode-specific overrides.
"""
from typing import Optional, Dict, Any
import logging

from app.soul.models import SoulConfig, ModeConfig, ModeType
from app.persona.resolve import MODE_ALIASES

logger = logging.getLogger(__name__)


class SoulPolicyManager:
    """Manages behavior policies for the soul."""
    
    def __init__(self, soul_config: Optional[SoulConfig] = None):
        """
        Initialize the policy manager.
        
        Args:
            soul_config: Soul configuration to base policies on
        """
        self._soul_config = soul_config
        self._mode_policies: Dict[str, Dict[str, Any]] = {}
        self._init_default_policies()
        logger.info("SoulPolicyManager initialized")
    
    def _init_default_policies(self):
        """Initialize default policy settings."""
        self._default_policies = {
            "allowed_tool_proactiveness": "balanced",
            "default_verbosity": "normal",
            "output_format_rules": {
                "use_markdown": True,
                "include_line_numbers": True,
                "code_highlighting": True,
                "include_file_links": True
            },
            "risk_posture": "moderate",
            "memory_aggressiveness": "balanced",
            "include_reasoning": True,
            "include_alternatives": False,
            "max_iterations": 10,
            "timeout_seconds": 300,
            "response_style": "professional"
        }
        
        # Initialize mode-specific overrides
        self._init_mode_policies()
    
    def _init_mode_policies(self):
        """Initialize mode-specific policy overrides."""
        self._mode_policies = {
            "default": {
                "allowed_tool_proactiveness": "balanced",
                "default_verbosity": "normal",
                "response_style": "professional",
                "include_reasoning": True,
                "include_alternatives": False
            },
            "architect": {
                "allowed_tool_proactiveness": "minimal",
                "default_verbosity": "verbose",
                "response_style": "detailed",
                "include_reasoning": True,
                "include_alternatives": True,
                "max_iterations": 20,
                "timeout_seconds": 600,
                "phased_output": True,
                "output_format_rules": {
                    "use_markdown": True,
                    "include_line_numbers": True,
                    "code_highlighting": True,
                    "include_file_links": True,
                    "include_diagrams": True,
                    "phased_output": True
                }
            },
            "operator": {
                "allowed_tool_proactiveness": "aggressive",
                "default_verbosity": "terse",
                "response_style": "terse",
                "include_reasoning": False,
                "include_alternatives": False,
                "max_iterations": 5,
                "timeout_seconds": 60
            },
            "coder": {
                "allowed_tool_proactiveness": "balanced",
                "default_verbosity": "normal",
                "response_style": "professional",
                "include_reasoning": True,
                "include_alternatives": True,
                "output_format_rules": {
                    "use_markdown": True,
                    "include_line_numbers": True,
                    "code_highlighting": True,
                    "include_file_links": True,
                    "show_diff": True
                }
            },
            "researcher": {
                "allowed_tool_proactiveness": "minimal",
                "default_verbosity": "verbose",
                "response_style": "exhaustive",
                "include_reasoning": True,
                "include_alternatives": True,
                "max_iterations": 20,
                "timeout_seconds": 600
            }
        }
    
    @property
    def allowed_tool_proactiveness(self) -> str:
        """Get allowed tool proactiveness level."""
        return self._default_policies.get("allowed_tool_proactiveness", "balanced")
    
    @property
    def default_verbosity(self) -> str:
        """Get default verbosity level."""
        return self._default_policies.get("default_verbosity", "normal")
    
    @property
    def output_format_rules(self) -> Dict[str, Any]:
        """Get output format rules."""
        return self._default_policies.get("output_format_rules", {})
    
    @property
    def risk_posture(self) -> str:
        """Get risk posture setting."""
        return self._default_policies.get("risk_posture", "moderate")
    
    @property
    def memory_aggressiveness(self) -> str:
        """Get memory aggressiveness setting."""
        return self._default_policies.get("memory_aggressiveness", "balanced")
    
    def get_mode_policy(self, mode: str) -> Dict[str, Any]:
        """
        Get policy settings for a specific mode.
        
        Args:
            mode: Mode name
            
        Returns:
            Dictionary of policy settings for the mode
        """
        normalized = (mode or "").strip().lower()
        # Preserve legacy mode behavior when an explicit legacy policy exists.
        if normalized in self._mode_policies:
            lookup = normalized
        else:
            lookup = MODE_ALIASES.get(normalized, normalized)
        mode_policies = self._mode_policies.get(lookup, {})
        # Merge with defaults
        return {**self._default_policies, **mode_policies}
    
    def apply_mode(self, mode: str) -> Dict[str, Any]:
        """
        Apply mode-specific policies.
        
        Args:
            mode: Mode name to apply
            
        Returns:
            Applied policy settings
        """
        policy = self.get_mode_policy(mode)
        logger.info(f"Applied policy for mode '{mode}': proactiveness={policy.get('allowed_tool_proactiveness')}, verbosity={policy.get('default_verbosity')}")
        return policy
    
    def get_policy_value(self, key: str, mode: Optional[str] = None) -> Any:
        """
        Get a specific policy value, optionally for a mode.
        
        Args:
            key: Policy key
            mode: Optional mode to get value for
            
        Returns:
            Policy value
        """
        if mode:
            mode_policy = self.get_mode_policy(mode)
            return mode_policy.get(key, self._default_policies.get(key))
        return self._default_policies.get(key)
    
    def update_default_policy(self, key: str, value: Any):
        """
        Update a default policy value.
        
        Args:
            key: Policy key
            value: New value
        """
        self._default_policies[key] = value
        logger.info(f"Updated default policy: {key} = {value}")
    
    def update_mode_policy(self, mode: str, key: str, value: Any):
        """
        Update a mode-specific policy.
        
        Args:
            mode: Mode name
            key: Policy key
            value: New value
        """
        if mode not in self._mode_policies:
            self._mode_policies[mode] = {}
        self._mode_policies[mode][key] = value
        logger.info(f"Updated mode '{mode}' policy: {key} = {value}")
    
    def set_soul_config(self, soul_config: SoulConfig):
        """Set the soul configuration."""
        self._soul_config = soul_config
        logger.info("Soul config updated in policy manager")
    
    def get_verbosity_for_mode(self, mode: Optional[str] = None) -> str:
        """Get verbosity setting for a mode."""
        return self.get_policy_value("default_verbosity", mode)
    
    def get_proactiveness_for_mode(self, mode: Optional[str] = None) -> str:
        """Get proactiveness setting for a mode."""
        return self.get_policy_value("allowed_tool_proactiveness", mode)
    
    def get_risk_posture_for_mode(self, mode: Optional[str] = None) -> str:
        """Get risk posture for a mode."""
        return self.get_policy_value("risk_posture", mode)
    
    def should_include_reasoning(self, mode: Optional[str] = None) -> bool:
        """Check if reasoning should be included."""
        return self.get_policy_value("include_reasoning", mode)
    
    def should_include_alternatives(self, mode: Optional[str] = None) -> bool:
        """Check if alternatives should be included."""
        return self.get_policy_value("include_alternatives", mode)
    
    def get_max_iterations(self, mode: Optional[str] = None) -> int:
        """Get max iterations for a mode."""
        return self.get_policy_value("max_iterations", mode)
    
    def get_timeout(self, mode: Optional[str] = None) -> int:
        """Get timeout for a mode."""
        return self.get_policy_value("timeout_seconds", mode)


# Global singleton instance
_policy_manager: Optional[SoulPolicyManager] = None


def get_policy_manager() -> SoulPolicyManager:
    """Get the global policy manager instance."""
    global _policy_manager
    if _policy_manager is None:
        _policy_manager = SoulPolicyManager()
    return _policy_manager


def init_policy_manager(soul_config: SoulConfig) -> SoulPolicyManager:
    """Initialize the policy manager with soul config."""
    global _policy_manager
    _policy_manager = SoulPolicyManager(soul_config)
    return _policy_manager
