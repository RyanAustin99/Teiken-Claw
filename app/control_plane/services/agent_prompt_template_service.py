"""Prompt template rendering for hatched control-plane agents."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.control_plane.domain.models import AgentRecord


DEFAULT_TEMPLATE = """You are {agent_name}.
Description: {agent_description}
Model: {model_name}
Workspace: {workspace_path}

Capabilities:
{capabilities_block}

Tool Profile: {tool_profile}
Allowed tools:
{tools_block}

Style Profile:
{style_block}

Skills:
{skills_block}
"""


class AgentPromptTemplateService:
    """Renders the standard system prompt for hatched agents."""

    def __init__(self, template_path: Path) -> None:
        self.template_path = template_path

    def render(
        self,
        agent: AgentRecord,
        *,
        default_model: str,
        capability_lines: Iterable[str],
        tool_lines: Iterable[str],
        style_lines: Iterable[str],
        skill_lines: Iterable[str],
    ) -> str:
        template = self._load_template()
        model_name = agent.model or default_model
        capabilities_block = self._render_lines(capability_lines, fallback="No capability summary available.")
        tools_block = self._render_lines(tool_lines, fallback="No tools declared for this profile.")
        style_block = self._render_lines(style_lines, fallback="No style overrides.")
        skills_block = self._render_lines(skill_lines, fallback="No skills loaded.")
        return template.format(
            agent_name=agent.name,
            agent_description=agent.description or "No description provided.",
            model_name=model_name,
            workspace_path=agent.workspace_path,
            capabilities_block=capabilities_block,
            tool_profile=agent.tool_profile,
            tools_block=tools_block,
            style_block=style_block,
            skills_block=skills_block,
        )

    def _load_template(self) -> str:
        try:
            return self.template_path.read_text(encoding="utf-8")
        except Exception:
            return DEFAULT_TEMPLATE

    @staticmethod
    def _render_lines(lines: Iterable[str], fallback: str) -> str:
        normalized = [line.strip() for line in lines if line and line.strip()]
        if not normalized:
            return f"- {fallback}"
        return "\n".join(f"- {line}" for line in normalized)
