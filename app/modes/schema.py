"""Versioned runtime mode schema definitions."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


RiskPosture = Literal["cautious", "balanced", "aggressive"]


class ModeToolBias(BaseModel):
    prefer: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    max_tool_turns: Optional[int] = None


class ModeOutputShape(BaseModel):
    must_include_sections: List[str] = Field(default_factory=list)
    forbid_sections: List[str] = Field(default_factory=list)


class ModeDefinition(BaseModel):
    name: str
    version: str
    description: str
    overlay_prompt: str
    tool_bias: ModeToolBias = Field(default_factory=ModeToolBias)
    output_shape: ModeOutputShape = Field(default_factory=ModeOutputShape)
    risk_posture: RiskPosture = "balanced"
    formatting_bias: Optional[str] = None
