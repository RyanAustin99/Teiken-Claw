"""Canonical tool-call envelope protocol utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError


TOOL_CALL_OPEN = "<TEIKEN_TOOL_CALL>"
TOOL_CALL_CLOSE = "</TEIKEN_TOOL_CALL>"
TOOL_RESULT_OPEN = "<TEIKEN_TOOL_RESULT>"
TOOL_RESULT_CLOSE = "</TEIKEN_TOOL_RESULT>"

_TOOL_CALL_PATTERN = re.compile(
    r"<TEIKEN_TOOL_CALL>\s*(.*?)\s*</TEIKEN_TOOL_CALL>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TOOL_RESULT_PATTERN = re.compile(
    r"<TEIKEN_TOOL_RESULT>\s*(.*?)\s*</TEIKEN_TOOL_RESULT>",
    flags=re.IGNORECASE | re.DOTALL,
)


class ToolCall(BaseModel):
    """Normalized tool call parsed from assistant output."""

    id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolResultEnvelope(BaseModel):
    """Runtime-generated tool execution receipt."""

    id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    ok: bool
    result: Dict[str, Any] | None = None
    error: Dict[str, Any] | None = None
    elapsed_ms: int = 0
    correlation_id: str | None = None


@dataclass
class ParsedToolCalls:
    """Parsed tool-call blocks and non-tool output."""

    clean_text: str
    calls: List[ToolCall] = field(default_factory=list)
    parse_failures: List[ToolResultEnvelope] = field(default_factory=list)


def extract_tool_calls(text: str) -> ParsedToolCalls:
    """Extract canonical tool calls from assistant output."""
    if not text:
        return ParsedToolCalls(clean_text="")

    calls: List[ToolCall] = []
    failures: List[ToolResultEnvelope] = []
    matches = list(_TOOL_CALL_PATTERN.finditer(text))
    clean_text = _TOOL_CALL_PATTERN.sub("", text).strip()

    for index, match in enumerate(matches, start=1):
        raw = (match.group(1) or "").strip()
        fallback_id = f"tc_parse_{index}"
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("tool call payload must be a JSON object")
            call = ToolCall(
                id=str(payload.get("id") or fallback_id),
                tool=str(payload.get("tool") or "").strip(),
                args=payload.get("args") or {},
            )
            calls.append(call)
        except (ValueError, TypeError, PydanticValidationError, json.JSONDecodeError) as exc:
            failures.append(
                ToolResultEnvelope(
                    id=fallback_id,
                    tool="invalid",
                    ok=False,
                    error={
                        "type": "parse_error",
                        "message": f"invalid tool envelope: {exc}",
                    },
                )
            )

    return ParsedToolCalls(clean_text=clean_text, calls=calls, parse_failures=failures)


def render_tool_result(envelope: ToolResultEnvelope) -> str:
    """Serialize a tool receipt into the canonical result envelope."""
    payload = envelope.model_dump(exclude_none=True)
    return f"{TOOL_RESULT_OPEN}{json.dumps(payload, ensure_ascii=False)}{TOOL_RESULT_CLOSE}"


def extract_tool_results(text: str) -> List[ToolResultEnvelope]:
    """Parse tool-result envelopes from transcript text."""
    if not text:
        return []
    results: List[ToolResultEnvelope] = []
    for match in _TOOL_RESULT_PATTERN.finditer(text):
        raw = (match.group(1) or "").strip()
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                continue
            results.append(ToolResultEnvelope(**payload))
        except Exception:
            continue
    return results


def normalize_native_tool_calls(tool_calls: List[Dict[str, Any]]) -> tuple[List[ToolCall], List[ToolResultEnvelope]]:
    """Convert native Ollama tool_calls payloads into canonical ToolCall objects."""
    calls: List[ToolCall] = []
    failures: List[ToolResultEnvelope] = []
    for index, call in enumerate(tool_calls, start=1):
        fallback_id = f"tc_native_{index}"
        try:
            function = call.get("function", {})
            if not isinstance(function, dict):
                raise ValueError("tool call function payload must be an object")
            name = str(function.get("name") or "").strip()
            if not name:
                raise ValueError("missing tool function name")
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments) if arguments.strip() else {}
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                raise ValueError("tool function arguments must be an object")
            calls.append(ToolCall(id=fallback_id, tool=name, args=arguments))
        except Exception as exc:
            failures.append(
                ToolResultEnvelope(
                    id=fallback_id,
                    tool="invalid",
                    ok=False,
                    error={
                        "type": "parse_error",
                        "message": f"invalid native tool call: {exc}",
                    },
                )
            )
    return calls, failures

