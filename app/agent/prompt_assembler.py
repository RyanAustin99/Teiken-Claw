"""Deterministic prompt assembly with soul/mode overlays."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


PLATFORM_BASELINE_POLICY = (
    "You are Teiken Claw. Follow platform safety policy, produce accurate responses, "
    "and execute tools only when needed."
)


@dataclass(frozen=True)
class PromptBundle:
    system_prompt: str
    prompt_fingerprint: str
    resolved_soul_ref: str
    resolved_mode_ref: str
    effective_tool_policy: Dict[str, Any]
    effective_file_policy: Dict[str, Any]
    memory_ids: List[str]
    message_ids: List[str]


class PromptAssembler:
    def assemble(
        self,
        *,
        resolved_soul_ref: str,
        resolved_mode_ref: str,
        soul_hash: str,
        mode_hash: str,
        soul_prompt: str,
        soul_principles: Iterable[str],
        mode_overlay_prompt: str,
        mode_output_requirements: Dict[str, Any],
        memory_items: List[Dict[str, Any]],
        transcript_messages: List[Dict[str, Any]],
        effective_tool_policy: Dict[str, Any],
        effective_file_policy: Dict[str, Any],
        platform_policy_version: str,
    ) -> PromptBundle:
        memory_lines = [
            f'MEMORY: {item.get("category", "memory")}.{item.get("key", "item")} = "{item.get("value", "")}"'
            for item in memory_items
        ]
        transcript_lines = [
            f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
            for msg in transcript_messages
        ]

        principles_lines = [f"- {line}" for line in soul_principles if line]
        output_shape_lines: List[str] = []
        must_sections = mode_output_requirements.get("must_include_sections") or []
        forbid_sections = mode_output_requirements.get("forbid_sections") or []
        if must_sections:
            output_shape_lines.append("Must include sections: " + ", ".join(str(section) for section in must_sections))
        if forbid_sections:
            output_shape_lines.append("Forbidden sections: " + ", ".join(str(section) for section in forbid_sections))

        blocks = [
            "# Platform Baseline",
            PLATFORM_BASELINE_POLICY,
            "# Soul",
            soul_prompt.strip(),
            "# Soul Principles",
            "\n".join(principles_lines) if principles_lines else "- None",
            "# Mode Overlay",
            mode_overlay_prompt.strip(),
            "# Mode Output Shape",
            "\n".join(output_shape_lines) if output_shape_lines else "None",
            "# Thread Memory",
            "\n".join(memory_lines) if memory_lines else "None",
            "# Recent Transcript",
            "\n".join(transcript_lines) if transcript_lines else "None",
            "# Effective Tool Policy",
            json.dumps(effective_tool_policy, sort_keys=True),
            "# Effective File Policy",
            json.dumps(effective_file_policy, sort_keys=True),
        ]
        system_prompt = "\n\n".join(blocks).strip()

        memory_ids = sorted(
            str(item.get("id") or item.get("public_id") or "")
            for item in memory_items
            if item.get("id") or item.get("public_id")
        )
        message_ids = [
            str(item.get("id") or item.get("message_id") or "")
            for item in transcript_messages
            if item.get("id") or item.get("message_id")
        ]
        memory_markers = sorted(
            f"{item.get('id') or item.get('public_id')}@{item.get('updated_at') or item.get('ts') or ''}"
            for item in memory_items
            if item.get("id") or item.get("public_id")
        )

        fingerprint_payload = {
            "platform_policy_version": platform_policy_version,
            "soul_ref": resolved_soul_ref,
            "soul_hash": soul_hash,
            "mode_ref": resolved_mode_ref,
            "mode_hash": mode_hash,
            "memory_markers": memory_markers,
            "message_ids": message_ids,
            "effective_tool_policy": effective_tool_policy,
            "effective_file_policy": effective_file_policy,
        }
        canonical = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        prompt_fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return PromptBundle(
            system_prompt=system_prompt,
            prompt_fingerprint=prompt_fingerprint,
            resolved_soul_ref=resolved_soul_ref,
            resolved_mode_ref=resolved_mode_ref,
            effective_tool_policy=effective_tool_policy,
            effective_file_policy=effective_file_policy,
            memory_ids=memory_ids,
            message_ids=message_ids,
        )
