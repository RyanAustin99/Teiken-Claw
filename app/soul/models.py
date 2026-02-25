"""
Soul data models for identity, behavior configuration, and mode-specific settings.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ModeType(str, Enum):
    """Available agent modes."""
    DEFAULT = "default"
    ARCHITECT = "architect"
    OPERATOR = "operator"
    CODER = "coder"
    RESEARCHER = "researcher"


class GuardrailsConfig(BaseModel):
    """Safety behavior configuration."""
    max_file_size_mb: int = Field(default=50, description="Maximum file size to process in MB")
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".py", ".js", ".ts", ".md", ".yaml", ".yml", ".json", ".txt"],
        description="Allowed file extensions"
    )
    blocked_paths: list[str] = Field(
        default_factory=list,
        description="Paths that are blocked from access"
    )
    max_concurrent_tools: int = Field(default=5, description="Maximum concurrent tool calls")
    require_confirmation_for: list[str] = Field(
        default_factory=lambda: ["delete", "exec", "drop"],
        description="Tool categories requiring confirmation"
    )
    rate_limit_per_minute: int = Field(default=60, description="Rate limit per minute")
    allowed_proactiveness: str = Field(
        default="balanced",
        description="Allowed proactiveness level: none, minimal, balanced, aggressive"
    )


class GoalsConfig(BaseModel):
    """Operational goals configuration."""
    primary_goals: list[str] = Field(
        default_factory=lambda: [
            "Provide accurate and helpful responses",
            "Maintain code quality and security",
            "Follow best practices and patterns"
        ],
        description="Primary operational goals"
    )
    success_criteria: list[str] = Field(
        default_factory=lambda: [
            "User requests fulfilled successfully",
            "Code compiles and runs without errors",
            "Tests pass where applicable"
        ],
        description="Success criteria for operations"
    )
    priority_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "accuracy": 0.4,
            "efficiency": 0.3,
            "safety": 0.2,
            "clarity": 0.1
        },
        description="Priority weights for decision making"
    )


class ModeConfig(BaseModel):
    """Mode-specific settings."""
    name: str = Field(description="Mode name")
    description: str = Field(default="", description="Mode description")
    verbosity: str = Field(default="normal", description="Verbosity level: terse, normal, verbose")
    output_format: str = Field(default="markdown", description="Output format: markdown, plain, json")
    tool_proactiveness: str = Field(
        default="balanced",
        description="Tool proactiveness: none, minimal, balanced, aggressive"
    )
    response_style: str = Field(
        default="professional",
        description="Response style: terse, normal, detailed, exhaustive"
    )
    include_reasoning: bool = Field(default=True, description="Include reasoning in responses")
    include_alternatives: bool = Field(default=False, description="Include alternative approaches")
    max_iterations: int = Field(default=10, description="Maximum iterations for complex tasks")
    timeout_seconds: int = Field(default=300, description="Timeout for operations")
    prompt_template: Optional[str] = Field(default=None, description="Custom prompt template for mode")


class SoulConfig(BaseModel):
    """Complete soul configuration."""
    name: str = Field(default="Teiken Claw", description="Agent identity name")
    version: str = Field(default="1.0.0", description="Soul version")
    core_file: str = Field(default="soul/core.md", description="Path to core.md")
    style_file: str = Field(default="soul/style.md", description="Path to style.md")
    goals_file: str = Field(default="soul/goals.yaml", description="Path to goals.yaml")
    guardrails_file: str = Field(default="soul/guardrails.yaml", description="Path to guardrails.yaml")
    default_mode: ModeType = Field(default=ModeType.DEFAULT, description="Default mode")
    modes_directory: str = Field(default="soul/modes", description="Path to modes directory")
    
    # Loaded configurations (populated at runtime)
    core: Optional[str] = Field(default=None, description="Loaded core identity")
    style: Optional[str] = Field(default=None, description="Loaded style guide")
    guardrails: Optional[GuardrailsConfig] = Field(default=None, description="Loaded guardrails")
    goals: Optional[GoalsConfig] = Field(default=None, description="Loaded goals")
    modes: dict[str, ModeConfig] = Field(default_factory=dict, description="Loaded mode configurations")


class ModeState(BaseModel):
    """Runtime state for mode."""
    current_mode: ModeType = Field(default=ModeType.DEFAULT, description="Current active mode")
    mode_config: Optional[ModeConfig] = Field(default=None, description="Current mode configuration")
    previous_mode: Optional[ModeType] = Field(default=None, description="Previous mode for switching back")
    mode_changed_at: Optional[str] = Field(default=None, description="Timestamp of last mode change")
