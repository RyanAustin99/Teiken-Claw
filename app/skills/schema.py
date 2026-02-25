"""YAML skill schema validation for Teiken Claw.

This module provides Pydantic models for validating skill definitions
loaded from YAML files, ensuring type safety and schema compliance.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class StepType(str, Enum):
    """Enumeration of available step types in a skill workflow."""
    TOOL_CALL = "tool_call"
    LLM_PROMPT = "llm_prompt"
    CONDITION = "condition"
    TRANSFORM = "transform"
    SUBAGENT = "subagent"
    SCHEDULE_CREATE = "schedule_create"
    RETURN = "return"


class SkillInput(BaseModel):
    """Definition of an input parameter for a skill."""
    name: str = Field(..., description="Name of the input parameter")
    type: str = Field(default="string", description="Type of the input parameter")
    description: str = Field(default="", description="Description of the input")
    required: bool = Field(default=True, description="Whether this input is required")
    default: Optional[Any] = Field(default=None, description="Default value if not provided")
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate that the type is a supported type."""
        allowed_types = {"string", "integer", "float", "boolean", "array", "object", "path"}
        if v not in allowed_types:
            raise ValueError(f"Type must be one of: {allowed_types}")
        return v


class SkillOutput(BaseModel):
    """Definition of an output from a skill."""
    name: str = Field(..., description="Name of the output")
    type: str = Field(default="string", description="Type of the output")
    description: str = Field(default="", description="Description of the output")
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate that the type is a supported type."""
        allowed_types = {"string", "integer", "float", "boolean", "array", "object", "path"}
        if v not in allowed_types:
            raise ValueError(f"Type must be one of: {allowed_types}")
        return v


class SkillTrigger(BaseModel):
    """Trigger configuration for a skill."""
    keywords: list[str] = Field(..., description="Keywords that trigger this skill")
    pattern: Optional[str] = Field(default=None, description="Regex pattern for advanced matching")
    priority: int = Field(default=0, description="Priority when multiple skills match (higher wins)")
    
    @field_validator('keywords')
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        """Ensure at least one keyword is provided."""
        if not v:
            raise ValueError("At least one keyword must be provided")
        return v


class SkillStep(BaseModel):
    """Individual step in a skill workflow."""
    id: str = Field(..., description="Unique identifier for this step")
    type: StepType = Field(..., description="Type of step to execute")
    description: str = Field(default="", description="Human-readable description")
    
    # Tool call specific
    tool_name: Optional[str] = Field(default=None, description="Name of tool to call")
    tool_params: Optional[dict[str, Any]] = Field(default=None, description="Parameters for tool call")
    
    # LLM prompt specific
    prompt: Optional[str] = Field(default=None, description="Prompt template for LLM")
    prompt_inputs: Optional[dict[str, str]] = Field(default=None, description="Input mappings for prompt")
    
    # Condition specific
    condition_expression: Optional[str] = Field(default=None, description="Boolean expression to evaluate")
    
    # Transform specific
    transform_expression: Optional[str] = Field(default=None, description="Transformation expression")
    transform_input: Optional[str] = Field(default=None, description="Input value path for transform")
    
    # Subagent specific
    subagent_name: Optional[str] = Field(default=None, description="Name of subagent to invoke")
    subagent_prompt: Optional[str] = Field(default=None, description="Prompt for subagent")
    
    # Schedule create specific
    schedule_cron: Optional[str] = Field(default=None, description="Cron expression for schedule")
    schedule_action: Optional[str] = Field(default=None, description="Action to schedule")
    
    # Return specific
    return_value: Optional[str] = Field(default=None, description="Value or path to return")
    
    # Branching
    on_success: Optional[str] = Field(default=None, description="Next step ID on success")
    on_failure: Optional[str] = Field(default=None, description="Next step ID on failure")
    
    @field_validator('type')
    @classmethod
    def validate_step_type(cls, v: StepType) -> StepType:
        """Validate step type has required fields."""
        return v


class SkillDefinition(BaseModel):
    """Complete skill definition loaded from YAML."""
    version: str = Field(default="1.0", description="Skill definition version")
    name: str = Field(..., description="Unique name of the skill")
    description: str = Field(..., description="Human-readable description")
    
    # Trigger configuration
    triggers: list[SkillTrigger] = Field(default_factory=list, description="Triggers that activate this skill")
    
    # I/O specifications
    inputs: list[SkillInput] = Field(default_factory=list, description="Input parameters")
    outputs: list[SkillOutput] = Field(default_factory=list, description="Output specifications")
    
    # Workflow steps
    steps: list[SkillStep] = Field(..., description="Ordered list of steps to execute")
    
    # Metadata
    category: Optional[str] = Field(default=None, description="Category for organization")
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")
    author: Optional[str] = Field(default=None, description="Author of the skill")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate skill name format."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Skill name must contain only alphanumeric characters, hyphens, and underscores")
        return v
    
    @field_validator('steps')
    @classmethod
    def validate_steps(cls, v: list[SkillStep]) -> list[SkillStep]:
        """Ensure at least one step exists and step IDs are unique."""
        if not v:
            raise ValueError("At least one step must be defined")
        
        step_ids = [step.id for step in v]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique")
        
        return v
    
    def get_input(self, name: str) -> Optional[SkillInput]:
        """Get input definition by name."""
        for inp in self.inputs:
            if inp.name == name:
                return inp
        return None
    
    def get_step(self, step_id: str) -> Optional[SkillStep]:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None
    
    def get_first_step(self) -> Optional[SkillStep]:
        """Get the first step in the workflow."""
        return self.steps[0] if self.steps else None


class SkillVersion(BaseModel):
    """Version information for skill definitions."""
    major: int = Field(..., description="Major version number")
    minor: int = Field(..., description="Minor version number")
    patch: int = Field(default=0, description="Patch version number")
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    @classmethod
    def from_string(cls, version: str) -> "SkillVersion":
        """Parse version string like '1.0' or '1.2.3'."""
        parts = version.split('.')
        return cls(
            major=int(parts[0]),
            minor=int(parts[1]) if len(parts) > 1 else 0,
            patch=int(parts[2]) if len(parts) > 2 else 0
        )
    
    def is_compatible(self, other: "SkillVersion") -> bool:
        """Check if versions are compatible (same major version)."""
        return self.major == other.major


# Schema validation functions
def validate_skill_definition(data: dict[str, Any]) -> SkillDefinition:
    """Validate and parse a skill definition from raw data.
    
    Args:
        data: Raw dictionary from YAML parsing
        
    Returns:
        Validated SkillDefinition instance
        
    Raises:
        ValidationError: If the data doesn't match the schema
    """
    return SkillDefinition(**data)


def validate_step_type(step: SkillStep) -> bool:
    """Validate that a step has all required fields for its type.
    
    Args:
        step: The step to validate
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If required fields are missing
    """
    required_fields = {
        StepType.TOOL_CALL: ['tool_name'],
        StepType.LLM_PROMPT: ['prompt'],
        StepType.CONDITION: ['condition_expression'],
        StepType.TRANSFORM: ['transform_expression'],
        StepType.SUBAGENT: ['subagent_name'],
        StepType.SCHEDULE_CREATE: ['schedule_cron', 'schedule_action'],
        StepType.RETURN: [],
    }
    
    missing = [f for f in required_fields.get(step.type, []) if not getattr(step, f, None)]
    if missing:
        raise ValueError(f"Step {step.id} of type {step.type.value} missing required fields: {missing}")
    
    return True


# Export all models
__all__ = [
    'StepType',
    'SkillInput',
    'SkillOutput',
    'SkillTrigger',
    'SkillStep',
    'SkillDefinition',
    'SkillVersion',
    'validate_skill_definition',
    'validate_step_type',
]
