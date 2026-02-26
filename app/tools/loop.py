"""Shared model-tool loop orchestration for chat and runtime paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Sequence

from app.tools.executor import ToolExecutionContext, ToolExecutor
from app.tools.protocol import (
    ToolCall,
    ToolResultEnvelope,
    extract_tool_calls,
    normalize_native_tool_calls,
    render_tool_result,
)


ToolModelCall = Callable[[List[Dict[str, Any]]], Awaitable[tuple[str, List[Dict[str, Any]]]]]


@dataclass
class ToolLoopResult:
    """Final output and receipts from a tool-enabled model turn loop."""

    final_response: str
    tool_events: List[ToolResultEnvelope] = field(default_factory=list)
    turns: int = 0


def extract_calls_from_output(
    assistant_output: str,
    native_tool_calls: Sequence[Dict[str, Any]] | None = None,
) -> tuple[str, List[ToolCall], List[ToolResultEnvelope]]:
    """Extract canonical + native calls from model output safely."""
    parsed = extract_tool_calls(assistant_output)
    calls = list(parsed.calls)
    failures = list(parsed.parse_failures)
    if native_tool_calls:
        native_calls, native_failures = normalize_native_tool_calls(list(native_tool_calls))
        calls.extend(native_calls)
        failures.extend(native_failures)
    clean_text = parsed.clean_text or assistant_output
    return clean_text, calls, failures


def build_receipt_feedback(receipts: Sequence[ToolResultEnvelope]) -> str:
    if not receipts:
        return (
            "No tool receipts were generated. If tool actions are needed, emit only "
            "<TEIKEN_TOOL_CALL>...</TEIKEN_TOOL_CALL> envelopes."
        )
    lines = [render_tool_result(item) for item in receipts]
    return (
        "Tool execution receipts:\n"
        + "\n".join(lines)
        + "\nUse these runtime receipts. If more actions are needed, emit only TEIKEN_TOOL_CALL "
        "envelopes. Otherwise provide the final response."
    )


async def run_tool_loop(
    *,
    initial_messages: List[Dict[str, Any]],
    model_call: ToolModelCall,
    executor: ToolExecutor,
    execution_context: ToolExecutionContext,
    max_tool_turns_per_request: int = 8,
) -> ToolLoopResult:
    """Run a bounded tool loop with runtime-generated receipts."""
    messages = list(initial_messages)
    all_events: List[ToolResultEnvelope] = []

    for turn in range(1, max(1, max_tool_turns_per_request) + 1):
        assistant_output, native_tool_calls = await model_call(messages)
        clean_output, calls, parse_failures = extract_calls_from_output(
            assistant_output,
            native_tool_calls=native_tool_calls,
        )
        all_events.extend(parse_failures)

        if not calls:
            return ToolLoopResult(
                final_response=clean_output,
                tool_events=all_events,
                turns=turn,
            )

        messages.append({"role": "assistant", "content": clean_output})
        turn_events = await executor.execute_calls(calls, ctx=execution_context)
        all_events.extend(turn_events)
        messages.append(
            {
                "role": "user",
                "content": build_receipt_feedback([*parse_failures, *turn_events]),
            }
        )

    return ToolLoopResult(
        final_response=(
            "I reached the maximum tool execution turns for this request. "
            "Please narrow the scope and try again."
        ),
        tool_events=all_events,
        turns=max(1, max_tool_turns_per_request),
    )

