"""
Tests for the Soul layer - identity, behavior configuration, and mode-specific settings.
"""
import pytest
from pathlib import Path
import tempfile
import os

from app.soul.models import (
    SoulConfig,
    ModeConfig,
    GuardrailsConfig,
    GoalsConfig,
    ModeType,
    ModeState,
)
from app.soul.loader import SoulLoader, load_soul, get_soul_loader
from app.soul.policies import SoulPolicyManager, get_policy_manager, init_policy_manager


class TestSoulModels:
    """Test soul data models."""
    
    def test_mode_type_enum(self):
        """Test ModeType enum values."""
        assert ModeType.DEFAULT == "default"
        assert ModeType.ARCHITECT == "architect"
        assert ModeType.OPERATOR == "operator"
        assert ModeType.CODER == "coder"
        assert ModeType.RESEARCHER == "researcher"
    
    def test_guardrails_config_defaults(self):
        """Test GuardrailsConfig default values."""
        config = GuardrailsConfig()
        
        assert config.max_file_size_mb == 50
        assert config.max_concurrent_tools == 5
        assert config.rate_limit_per_minute == 60
        assert config.allowed_proactiveness == "balanced"
        assert ".py" in config.allowed_extensions
    
    def test_goals_config_defaults(self):
        """Test GoalsConfig default values."""
        config = GoalsConfig()
        
        assert len(config.primary_goals) > 0
        assert len(config.success_criteria) > 0
        assert "accuracy" in config.priority_weights
    
    def test_mode_config_defaults(self):
        """Test ModeConfig default values."""
        config = ModeConfig(name="test")
        
        assert config.name == "test"
        assert config.verbosity == "normal"
        assert config.output_format == "markdown"
        assert config.tool_proactiveness == "balanced"
        assert config.include_reasoning is True
        assert config.max_iterations == 10
        assert config.timeout_seconds == 300
    
    def test_soul_config_defaults(self):
        """Test SoulConfig default values."""
        config = SoulConfig()
        
        assert config.name == "Teiken Claw"
        assert config.version == "1.0.0"
        assert config.default_mode == ModeType.DEFAULT
        assert config.core_file == "soul/core.md"
        assert config.modes_directory == "soul/modes"
    
    def test_mode_state(self):
        """Test ModeState model."""
        state = ModeState(
            current_mode=ModeType.CODER,
            previous_mode=ModeType.DEFAULT
        )
        
        assert state.current_mode == ModeType.CODER
        assert state.previous_mode == ModeType.DEFAULT


class TestSoulLoader:
    """Test SoulLoader functionality."""
    
    @pytest.fixture
    def temp_soul_dir(self):
        """Create a temporary soul directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir) / "soul"
            soul_dir.mkdir()
            modes_dir = soul_dir / "modes"
            modes_dir.mkdir()
            
            # Create core.md
            (soul_dir / "core.md").write_text("# Test Core\n\nTest identity.")
            
            # Create style.md
            (soul_dir / "style.md").write_text("# Test Style\n\nTest style guide.")
            
            # Create goals.yaml
            (soul_dir / "goals.yaml").write_text("""
primary_goals:
  - "Test goal 1"
  - "Test goal 2"
success_criteria:
  - "Test criteria 1"
priority_weights:
  accuracy: 0.5
  efficiency: 0.5
""")
            
            # Create guardrails.yaml
            (soul_dir / "guardrails.yaml").write_text("""
max_file_size_mb: 100
allowed_proactiveness: aggressive
""")
            
            # Create default mode
            (modes_dir / "default.yaml").write_text("""
name: default
description: "Test default mode"
verbosity: terse
tool_proactiveness: minimal
""")
            
            # Create another mode
            (modes_dir / "coder.yaml").write_text("""
name: coder
description: "Test coder mode"
verbosity: verbose
tool_proactiveness: aggressive
""")
            
            yield tmpdir
    
    def test_load_soul(self, temp_soul_dir):
        """Test loading complete soul configuration."""
        loader = SoulLoader(base_path=temp_soul_dir)
        config = loader.load_soul()
        
        assert config is not None
        assert config.name == "Teiken Claw"
        assert config.core is not None
        assert config.style is not None
        assert config.guardrails is not None
        assert config.goals is not None
        assert "default" in config.modes
        assert "coder" in config.modes
    
    def test_load_core(self, temp_soul_dir):
        """Test loading core identity."""
        loader = SoulLoader(base_path=temp_soul_dir)
        core = loader.load_core()
        
        assert "Test Core" in core
        assert "Test identity" in core
    
    def test_load_style(self, temp_soul_dir):
        """Test loading style guide."""
        loader = SoulLoader(base_path=temp_soul_dir)
        style = loader.load_style()
        
        assert "Test Style" in style
    
    def test_load_guardrails(self, temp_soul_dir):
        """Test loading guardrails."""
        loader = SoulLoader(base_path=temp_soul_dir)
        guardrails = loader.load_guardrails()
        
        assert guardrails.max_file_size_mb == 100
        assert guardrails.allowed_proactiveness == "aggressive"
    
    def test_load_goals(self, temp_soul_dir):
        """Test loading goals."""
        loader = SoulLoader(base_path=temp_soul_dir)
        goals = loader.load_goals()
        
        assert "Test goal 1" in goals.primary_goals
        assert "Test criteria 1" in goals.success_criteria
        assert goals.priority_weights["accuracy"] == 0.5
    
    def test_load_mode(self, temp_soul_dir):
        """Test loading specific mode."""
        loader = SoulLoader(base_path=temp_soul_dir)
        mode = loader.load_mode("coder")
        
        assert mode.name == "coder"
        assert mode.description == "Test coder mode"
        assert mode.verbosity == "verbose"
        assert mode.tool_proactiveness == "aggressive"
    
    def test_load_all_modes(self, temp_soul_dir):
        """Test loading all modes."""
        loader = SoulLoader(base_path=temp_soul_dir)
        modes = loader.load_all_modes()
        
        assert "default" in modes
        assert "coder" in modes
    
    def test_default_core_fallback(self):
        """Test default core when file not found."""
        loader = SoulLoader(base_path="/nonexistent")
        core = loader.load_core()
        
        assert "Teiken Claw" in core
        assert "Identity" in core
    
    def test_default_style_fallback(self):
        """Test default style when file not found."""
        loader = SoulLoader(base_path="/nonexistent")
        style = loader.load_style()
        
        assert "Style Guide" in style
    
    def test_default_mode_config(self):
        """Test default mode config."""
        loader = SoulLoader()
        mode = loader._get_default_mode_config("test")
        
        assert mode.name == "test"
        assert mode.verbosity == "normal"


class TestSoulPolicies:
    """Test SoulPolicyManager functionality."""
    
    def test_default_policies(self):
        """Test default policy values."""
        manager = SoulPolicyManager()
        
        assert manager.allowed_tool_proactiveness == "balanced"
        assert manager.default_verbosity == "normal"
        assert manager.risk_posture == "moderate"
        assert manager.memory_aggressiveness == "balanced"
    
    def test_get_mode_policy(self):
        """Test getting mode-specific policy."""
        manager = SoulPolicyManager()
        
        # Test architect mode
        architect_policy = manager.get_mode_policy("architect")
        assert architect_policy["default_verbosity"] == "verbose"
        assert architect_policy["allowed_tool_proactiveness"] == "minimal"
        assert architect_policy["include_alternatives"] is True
        
        # Test operator mode
        operator_policy = manager.get_mode_policy("operator")
        assert operator_policy["default_verbosity"] == "terse"
        assert operator_policy["allowed_tool_proactiveness"] == "aggressive"
        
        # Test coder mode
        coder_policy = manager.get_mode_policy("coder")
        assert coder_policy["include_alternatives"] is True
        
        # Test researcher mode
        researcher_policy = manager.get_mode_policy("researcher")
        assert researcher_policy["default_verbosity"] == "verbose"
        assert researcher_policy["max_iterations"] == 20
    
    def test_apply_mode(self):
        """Test applying mode policies."""
        manager = SoulPolicyManager()
        
        policy = manager.apply_mode("operator")
        
        assert policy["default_verbosity"] == "terse"
        assert policy["allowed_tool_proactiveness"] == "aggressive"
    
    def test_get_policy_value(self):
        """Test getting specific policy value."""
        manager = SoulPolicyManager()
        
        # Without mode
        assert manager.get_policy_value("default_verbosity") == "normal"
        
        # With mode
        assert manager.get_policy_value("default_verbosity", "architect") == "verbose"
        assert manager.get_policy_value("default_verbosity", "operator") == "terse"
    
    def test_update_default_policy(self):
        """Test updating default policy."""
        manager = SoulPolicyManager()
        
        manager.update_default_policy("risk_posture", "conservative")
        
        assert manager.risk_posture == "conservative"
        assert manager.get_policy_value("risk_posture") == "conservative"
    
    def test_update_mode_policy(self):
        """Test updating mode-specific policy."""
        manager = SoulPolicyManager()
        
        manager.update_mode_policy("coder", "verbosity", "terse")
        
        policy = manager.get_mode_policy("coder")
        assert policy["verbosity"] == "terse"
    
    def test_should_include_reasoning(self):
        """Test reasoning inclusion check."""
        manager = SoulPolicyManager()
        
        assert manager.should_include_reasoning() is True
        assert manager.should_include_reasoning("default") is True
        assert manager.should_include_reasoning("operator") is False
    
    def test_should_include_alternatives(self):
        """Test alternatives inclusion check."""
        manager = SoulPolicyManager()
        
        assert manager.should_include_alternatives() is False
        assert manager.should_include_alternatives("architect") is True
        assert manager.should_include_alternatives("operator") is False
    
    def test_get_max_iterations(self):
        """Test max iterations for modes."""
        manager = SoulPolicyManager()
        
        assert manager.get_max_iterations() == 10
        assert manager.get_max_iterations("default") == 10
        assert manager.get_max_iterations("architect") == 20
        assert manager.get_max_iterations("operator") == 5
    
    def test_get_timeout(self):
        """Test timeout for modes."""
        manager = SoulPolicyManager()
        
        assert manager.get_timeout() == 300
        assert manager.get_timeout("architect") == 600
        assert manager.get_timeout("operator") == 60
    
    def test_output_format_rules(self):
        """Test output format rules."""
        manager = SoulPolicyManager()
        
        rules = manager.output_format_rules
        assert rules["use_markdown"] is True
        assert rules["include_line_numbers"] is True
        
        # Architect mode has additional rules
        architect_rules = manager.get_mode_policy("architect")
        assert architect_rules.get("phased_output") is True


class TestSoulIntegration:
    """Integration tests for soul components."""
    
    def test_load_and_policy_integration(self):
        """Test integration between loader and policies."""
        # Create a temporary soul config
        config = SoulConfig(
            name="Test Agent",
            version="1.0.0",
            default_mode=ModeType.DEFAULT
        )
        
        # Initialize policy manager with config
        manager = init_policy_manager(config)
        
        assert manager is not None
        assert manager.allowed_tool_proactiveness == "balanced"
    
    def test_get_soul_loader_singleton(self):
        """Test getting singleton soul loader."""
        loader1 = get_soul_loader()
        loader2 = get_soul_loader()
        
        assert loader1 is loader2
    
    def test_get_policy_manager_singleton(self):
        """Test getting singleton policy manager."""
        manager1 = get_policy_manager()
        manager2 = get_policy_manager()
        
        assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
