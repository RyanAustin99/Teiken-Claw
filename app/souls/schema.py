"""Versioned soul schema definitions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


Verbosity = Literal["low", "med", "high"]


class SoulStyle(BaseModel):
    verbosity: Verbosity = "med"
    formatting_bias: Optional[str] = None
    tone: Optional[str] = None


class SoulConstraints(BaseModel):
    disallowed_behaviors: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=lambda: ["*"])
    file_policy_override: Optional[Dict[str, Any]] = None
    memory_policy_override: Optional[Dict[str, Any]] = None

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, value: List[str]) -> List[str]:
        normalized = [item.strip() for item in value if item and item.strip()]
        if not normalized:
            return ["*"]
        if "*" in normalized:
            return ["*"]
        return sorted(set(normalized))


class SoulDefinition(BaseModel):
    name: str
    version: str
    description: str
    system_prompt: str
    principles: List[str] = Field(default_factory=list)
    style: SoulStyle = Field(default_factory=SoulStyle)
    constraints: SoulConstraints = Field(default_factory=SoulConstraints)
    tags: List[str] = Field(default_factory=list)
