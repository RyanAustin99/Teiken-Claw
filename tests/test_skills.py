"""
Tests for the Skills system.

This module tests:
- Skill schema validation
- Skill loading from YAML
- Skill execution
- Skill routing
- Built-in skills
"""

import pytest
import tempfile
import os
from pathlib import Path

from app.skills.schema import (
    SkillDefinition,
    SkillStep,
    SkillTrigger,
    SkillInput,
    SkillOutput,
    StepType,
    validate_skill_definition,
)
from app.skills.loader import SkillLoader
from app.skills.engine import SkillEngine, ExecutionContext, SkillResult
from app.skills.router import SkillRouter, SkillMatch


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_skills_dir():
    """Create a temporary directory for skill files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_skill_yaml():
    """Sample skill YAML content."""
    return """
version: "1.0"
name: test_skill
description: A test skill
category: test
tags:
  - test
  - sample

triggers:
  - keywords:
      - test
      - sample
    priority: 5

inputs:
  - name: input1
    type: string
    description: Test input
    required: true

outputs:
  - name: output1
    type: string
    description: Test output

steps:
  - id: step1
    type: tool_call
    description: First step
    tool_name: test_tool
    tool_params:
      param1: "value1"
    on_success: step2

  - id: step2
    type: return
    description: Return result
    return_value: "Success"
"""


# ============================================================================
# Schema Tests
# ============================================================================

class TestSkillSchema:
    """Tests for skill schema validation."""
    
    def test_skill_definition_valid(self):
        """Test valid skill definition."""
        data = {
            "version": "1.0",
            "name": "test_skill",
            "description": "Test skill description",
            "steps": [
                {
                    "id": "step1",
                    "type": "return",
                    "description": "Return step",
                    "return_value": "test"
                }
            ]
        }
        
        skill = validate_skill_definition(data)
        assert skill.name == "test_skill"
        assert skill.version == "1.0"
        assert len(skill.steps) == 1
    
    def test_skill_definition_missing_name(self):
        """Test skill definition without name fails."""
        data = {
            "version": "1.0",
            "description": "Test skill",
            "steps": [{"id": "step1", "type": "return"}]
        }
        
        with pytest.raises(Exception):
            validate_skill_definition(data)
    
    def test_skill_definition_no_steps(self):
        """Test skill definition without steps fails."""
        data = {
            "version": "1.0",
            "name": "test_skill",
            "description": "Test skill",
            "steps": []
        }
        
        with pytest.raises(Exception):
            validate_skill_definition(data)
    
    def test_step_type_enum(self):
        """Test StepType enum values."""
        assert StepType.TOOL_CALL.value == "tool_call"
        assert StepType.LLM_PROMPT.value == "llm_prompt"
        assert StepType.CONDITION.value == "condition"
        assert StepType.TRANSFORM.value == "transform"
        assert StepType.SUBAGENT.value == "subagent"
        assert StepType.SCHEDULE_CREATE.value == "schedule_create"
        assert StepType.RETURN.value == "return"


# ============================================================================
# Loader Tests
# ============================================================================

class TestSkillLoader:
    """Tests for skill loader."""
    
    def test_load_skill_from_yaml(self, temp_skills_dir, sample_skill_yaml):
        """Test loading a skill from YAML file."""
        # Write skill file
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        # Load skill
        loader = SkillLoader(skills_dir=temp_skills_dir)
        skill = loader.load_skill("test_skill")
        
        assert skill is not None
        assert skill.name == "test_skill"
        assert skill.description == "A test skill"
        assert len(skill.steps) == 2
    
    def test_load_nonexistent_skill(self, temp_skills_dir):
        """Test loading a skill that doesn't exist."""
        loader = SkillLoader(skills_dir=temp_skills_dir)
        skill = loader.load_skill("nonexistent")
        
        assert skill is None
    
    def test_load_all_skills(self, temp_skills_dir, sample_skill_yaml):
        """Test loading all skills from directory."""
        # Write multiple skill files
        (temp_skills_dir / "skill1.yaml").write_text(sample_skill_yaml)
        (temp_skills_dir / "skill2.yaml").write_text(sample_skill_yaml.replace("test_skill", "skill2"))
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        skills = loader.load_all_skills()
        
        assert len(skills) == 2
        assert "test_skill" in skills
        assert "skill2" in skills
    
    def test_validate_skill(self, temp_skills_dir, sample_skill_yaml):
        """Test skill validation."""
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        skill = loader.load_skill("test_skill")
        
        assert loader.validate_skill(skill) is True
    
    def test_get_skill_path(self, temp_skills_dir):
        """Test getting skill file path."""
        loader = SkillLoader(skills_dir=temp_skills_dir)
        path = loader.get_skill_path("my_skill")
        
        assert path == temp_skills_dir / "my_skill.yaml"


# ============================================================================
# Engine Tests
# ============================================================================

class TestSkillEngine:
    """Tests for skill engine execution."""
    
    def test_execute_skill_not_found(self):
        """Test executing a skill that doesn't exist."""
        engine = SkillEngine()
        result = engine.execute_skill("nonexistent", {})
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    def test_execute_skill_with_inputs(self, temp_skills_dir, sample_skill_yaml):
        """Test executing a skill with inputs."""
        # Write skill file
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        # Create engine with loader
        loader = SkillLoader(skills_dir=temp_skills_dir)
        engine = SkillEngine(loader=loader)
        
        # Execute with inputs
        result = engine.execute_skill("test_skill", {"input1": "test value"})
        
        # Should succeed (return step returns)
        assert result.success is True
        assert result.steps_executed >= 1
    
    def test_execution_context(self):
        """Test execution context."""
        ctx = ExecutionContext()
        
        # Test inputs
        ctx.inputs["key1"] = "value1"
        assert ctx.get("key1") == "value1"
        
        # Test variables
        ctx.set_variable("var1", "value2")
        assert ctx.get("var1") == "value2"
        
        # Test outputs
        ctx.set_output("out1", "value3")
        assert ctx.get("out1") == "value3"
        
        # Test errors
        ctx.add_error("Error 1")
        assert ctx.has_errors() is True
    
    def test_skill_result(self):
        """Test skill result."""
        result = SkillResult(
            success=True,
            outputs={"key": "value"},
            steps_executed=3,
            execution_time_ms=100.0,
            logs=["log1"]
        )
        
        assert result.success is True
        assert result.outputs["key"] == "value"
        assert result.steps_executed == 3
        assert result.execution_time_ms == 100.0
        
        # Test to_dict
        d = result.to_dict()
        assert d["success"] is True
        assert d["outputs"]["key"] == "value"


# ============================================================================
# Router Tests
# ============================================================================

class TestSkillRouter:
    """Tests for skill router."""
    
    def test_route_intent_no_match(self, temp_skills_dir):
        """Test routing with no matching skill."""
        loader = SkillLoader(skills_dir=temp_skills_dir)
        router = SkillRouter(loader=loader)
        
        result = router.route_intent("hello world")
        
        assert result is None
    
    def test_route_intent_direct_invocation(self, temp_skills_dir, sample_skill_yaml):
        """Test direct skill invocation."""
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        router = SkillRouter(loader=loader)
        router._loaded = False  # Force reload
        
        result = router.route_intent("/skill test_skill param1=value1")
        
        assert result is not None
        assert result[0] == "test_skill"
        assert result[1]["param1"] == "value1"
    
    def test_match_trigger_keyword(self, temp_skills_dir, sample_skill_yaml):
        """Test keyword matching."""
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        router = SkillRouter(loader=loader)
        
        # Force reload
        loader._loaded = False
        
        result = router.route_intent("test this please")
        
        assert result is not None
        assert result[0] == "test_skill"
    
    def test_list_available_skills(self, temp_skills_dir, sample_skill_yaml):
        """Test listing available skills."""
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        router = SkillRouter(loader=loader)
        
        # Force reload
        loader._loaded = False
        
        skills = router.list_available_skills()
        
        assert len(skills) >= 1
        assert any(s["name"] == "test_skill" for s in skills)
    
    def test_suggest_skills(self, temp_skills_dir, sample_skill_yaml):
        """Test skill suggestions."""
        skill_file = temp_skills_dir / "test_skill.yaml"
        skill_file.write_text(sample_skill_yaml)
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        router = SkillRouter(loader=loader)
        
        # Force reload
        loader._loaded = False
        
        suggestions = router.suggest_skills("test")
        
        assert len(suggestions) >= 1
        assert suggestions[0]["name"] == "test_skill"


# ============================================================================
# Integration Tests
# ============================================================================

class TestSkillsIntegration:
    """Integration tests for skills system."""
    
    def test_end_to_end_skill_flow(self, temp_skills_dir):
        """Test complete skill flow: load -> route -> execute."""
        # Create a simple skill
        skill_yaml = """
version: "1.0"
name: hello_skill
description: Says hello
triggers:
  - keywords:
      - hello
      - hi

inputs:
  - name: name
    type: string
    required: false
    default: "World"

steps:
  - id: greet
    type: return
    return_value: "Hello, ${name}!"
"""
        (temp_skills_dir / "hello_skill.yaml").write_text(skill_yaml)
        
        # Load
        loader = SkillLoader(skills_dir=temp_skills_dir)
        skills = loader.load_all_skills()
        assert "hello_skill" in skills
        
        # Route
        router = SkillRouter(loader=loader)
        route_result = router.route_intent("say hello")
        assert route_result is not None
        assert route_result[0] == "hello_skill"
        
        # Execute
        engine = SkillEngine(loader=loader)
        result = engine.execute_skill("hello_skill", {"name": "Test"})
        assert result.success is True
    
    def test_direct_invocation_format(self, temp_skills_dir):
        """Test various direct invocation formats."""
        skill_yaml = """
version: "1.0"
name: format_test
description: Test format
triggers:
  - keywords:
      - format

steps:
  - id: done
    type: return
    return_value: "Done"
"""
        (temp_skills_dir / "format_test.yaml").write_text(skill_yaml)
        
        loader = SkillLoader(skills_dir=temp_skills_dir)
        router = SkillRouter(loader=loader)
        
        # Force reload
        loader._loaded = False
        
        # Test /skill format
        result = router.route_intent("/skill format_test key=value")
        assert result == ("format_test", {"key": "value"})
        
        # Test /run format
        result = router.route_intent("/run format_test foo=bar")
        assert result == ("format_test", {"foo": "bar"})
        
        # Test skill: format
        result = router.route_intent("skill: format_test x=1")
        assert result == ("format_test", {"x": "1"})


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
