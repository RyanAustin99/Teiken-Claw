"""Shared tool executor with policy, pause, and audit enforcement."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from app.scheduler.control_state import get_control_state_manager
from app.observability.file_audit import FileAuditContext, runtime_file_audit_context
from app.tools.base import ToolResult
from app.tools.files_tool import runtime_workspace_root
from app.tools.files_service import runtime_file_policy_override
from app.tools.policies import check_tool_permission
from app.tools.protocol import ToolCall, ToolResultEnvelope
from app.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)

DEFAULT_PROFILE_ALLOWLIST: Dict[str, set[str]] = {
    "safe": {"echo", "time", "status", "files.read", "files.list", "files.exists", "web.search"},
    "balanced": {
        "echo",
        "time",
        "status",
        "files.read",
        "files.list",
        "files.exists",
        "files.write",
        "web.search",
        "exec",
    },
}


@dataclass
class ToolExecutionContext:
    """Execution context for policy and audit controls."""

    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    scheduler_job_id: Optional[str] = None
    scheduler_run_id: Optional[str] = None
    chat_id: Optional[str] = None
    is_admin: bool = False
    tool_profile: str = "safe"
    workspace_root: Optional[Path] = None
    actor: str = "runtime"
    correlation_id: Optional[str] = None
    max_calls_per_message: int = 3
    timeout_sec: float = 30.0
    max_result_chars: int = 12000
    allowed_tools: Optional[set[str]] = None
    file_policy_override: Optional[Dict[str, Any]] = None
    audit_log: Optional[Callable[[str, Optional[str], Optional[Dict[str, Any]], str], None]] = None
    control_state_manager: Any = None


class ToolExecutor:
    """Execute canonical tool calls with deterministic receipts."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute_calls(
        self,
        calls: List[ToolCall],
        ctx: ToolExecutionContext,
    ) -> List[ToolResultEnvelope]:
        correlation_id = ctx.correlation_id or str(uuid4())
        results: List[ToolResultEnvelope] = []

        capped_calls = calls[: max(1, ctx.max_calls_per_message)]
        overflow = calls[len(capped_calls) :]
        for skipped in overflow:
            envelope = ToolResultEnvelope(
                id=skipped.id,
                tool=skipped.tool,
                ok=False,
                error={
                    "type": "limit_exceeded",
                    "message": f"max tool calls per message exceeded ({ctx.max_calls_per_message})",
                },
                correlation_id=correlation_id,
            )
            self._emit_audit(
                "tool_call_failed",
                skipped.tool,
                {
                    "call_id": skipped.id,
                    "reason": "max_calls_per_message_exceeded",
                    "max_calls_per_message": ctx.max_calls_per_message,
                    "correlation_id": correlation_id,
                },
                ctx,
            )
            results.append(envelope)

        for call in capped_calls:
            self._emit_audit(
                "tool_call_detected",
                call.tool,
                {
                    "call_id": call.id,
                    "agent_id": ctx.agent_id,
                    "session_id": ctx.session_id,
                    "thread_id": ctx.thread_id,
                    "scheduler_job_id": ctx.scheduler_job_id,
                    "scheduler_run_id": ctx.scheduler_run_id,
                    "correlation_id": correlation_id,
                },
                ctx,
            )

            denied_reason = self._deny_reason(call, ctx)
            if denied_reason:
                envelope = ToolResultEnvelope(
                    id=call.id,
                    tool=call.tool,
                    ok=False,
                    error={"type": "not_allowed", "message": denied_reason},
                    correlation_id=correlation_id,
                )
                self._emit_audit(
                    "tool_call_denied",
                    call.tool,
                    {
                        "call_id": call.id,
                        "reason": denied_reason,
                        "tool_profile": ctx.tool_profile,
                        "correlation_id": correlation_id,
                    },
                    ctx,
                )
                results.append(envelope)
                continue

            self._emit_audit(
                "tool_call_started",
                call.tool,
                {"call_id": call.id, "correlation_id": correlation_id},
                ctx,
            )

            started = asyncio.get_running_loop().time()
            envelope = await self._execute_single(call, ctx=ctx, correlation_id=correlation_id)
            elapsed_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            envelope.elapsed_ms = elapsed_ms
            results.append(envelope)

            if envelope.ok:
                self._emit_audit(
                    "tool_call_succeeded",
                    call.tool,
                    {
                        "call_id": call.id,
                        "elapsed_ms": elapsed_ms,
                        "result": envelope.result,
                        "correlation_id": correlation_id,
                    },
                    ctx,
                )
            else:
                self._emit_audit(
                    "tool_call_failed",
                    call.tool,
                    {
                        "call_id": call.id,
                        "elapsed_ms": elapsed_ms,
                        "error": envelope.error,
                        "correlation_id": correlation_id,
                    },
                    ctx,
                )

        return results

    async def _execute_single(
        self,
        call: ToolCall,
        *,
        ctx: ToolExecutionContext,
        correlation_id: str,
    ) -> ToolResultEnvelope:
        tool_call_payload = {
            "function": {
                "name": call.tool,
                "arguments": call.args,
            }
        }
        execution_ctx = {
            "agent_id": ctx.agent_id,
            "session_id": ctx.session_id,
            "thread_id": ctx.thread_id,
            "scheduler_job_id": ctx.scheduler_job_id,
            "scheduler_run_id": ctx.scheduler_run_id,
            "chat_id": ctx.chat_id,
            "is_admin": ctx.is_admin,
            "correlation_id": correlation_id,
        }

        workspace_cm = runtime_workspace_root(ctx.workspace_root) if ctx.workspace_root else nullcontext()
        file_policy_cm = runtime_file_policy_override(ctx.file_policy_override) if ctx.file_policy_override else nullcontext()
        file_audit_cm = runtime_file_audit_context(
            FileAuditContext(
                agent_id=str(ctx.agent_id) if ctx.agent_id is not None else None,
                thread_id=str(ctx.thread_id) if ctx.thread_id is not None else None,
                session_id=str(ctx.session_id) if ctx.session_id is not None else None,
                correlation_id=correlation_id,
            )
        )
        try:
            with workspace_cm, file_policy_cm, file_audit_cm:
                raw_result: ToolResult = await asyncio.wait_for(
                    self.registry.execute_tool_call(tool_call=tool_call_payload, context=execution_ctx),
                    timeout=max(0.1, ctx.timeout_sec),
                )
        except asyncio.TimeoutError:
            return ToolResultEnvelope(
                id=call.id,
                tool=call.tool,
                ok=False,
                error={"type": "timeout", "message": f"tool call timed out after {ctx.timeout_sec}s"},
                correlation_id=correlation_id,
            )
        except Exception as exc:
            return ToolResultEnvelope(
                id=call.id,
                tool=call.tool,
                ok=False,
                error={"type": "execution_error", "message": str(exc)},
                correlation_id=correlation_id,
            )

        if raw_result.ok:
            payload = self._sanitize_result_payload(raw_result, max_chars=ctx.max_result_chars)
            return ToolResultEnvelope(
                id=call.id,
                tool=call.tool,
                ok=True,
                result=payload,
                correlation_id=correlation_id,
            )

        error_message = raw_result.error_message or raw_result.content or "tool execution failed"
        error_type = (raw_result.error_code or "execution_error").lower()
        error_payload: Dict[str, Any] = {"type": error_type, "message": error_message}
        metadata_error = raw_result.metadata.get("error") if isinstance(raw_result.metadata, dict) else None
        if isinstance(metadata_error, dict):
            if metadata_error.get("code"):
                error_payload["code"] = metadata_error.get("code")
            if metadata_error.get("hint"):
                error_payload["hint"] = metadata_error.get("hint")
            if metadata_error.get("legacy_code"):
                error_payload["legacy_code"] = metadata_error.get("legacy_code")
        return ToolResultEnvelope(
            id=call.id,
            tool=call.tool,
            ok=False,
            error=error_payload,
            correlation_id=correlation_id,
        )

    def _deny_reason(self, call: ToolCall, ctx: ToolExecutionContext) -> Optional[str]:
        manager = ctx.control_state_manager or get_control_state_manager()
        if manager and hasattr(manager, "is_tools_paused"):
            try:
                if manager.is_tools_paused():
                    return "tools are paused by control state"
            except Exception:
                pass

        tool = self.registry.get(call.tool)
        if tool is None:
            return f"unknown tool: {call.tool}"

        if not self._is_profile_allowed(call.tool, ctx.tool_profile):
            return f"tool '{call.tool}' is not permitted for profile '{ctx.tool_profile}'"

        if not check_tool_permission(tool, chat_id=ctx.chat_id, is_admin=ctx.is_admin):
            return f"permission denied for tool '{call.tool}'"

        if not tool.policy.enabled:
            return f"tool '{call.tool}' is disabled"

        if ctx.allowed_tools is not None and call.tool not in ctx.allowed_tools:
            return f"tool '{call.tool}' is not allowed by active soul/mode policy"

        return None

    @staticmethod
    def _is_profile_allowed(tool_name: str, profile: str) -> bool:
        normalized = (profile or "safe").strip().lower()
        if normalized == "dangerous":
            return True
        allowed = DEFAULT_PROFILE_ALLOWLIST.get(normalized, DEFAULT_PROFILE_ALLOWLIST["safe"])
        return tool_name in allowed

    @staticmethod
    def _sanitize_result_payload(result: ToolResult, *, max_chars: int) -> Dict[str, Any]:
        if isinstance(result.metadata, dict) and isinstance(result.metadata.get("receipt"), dict):
            receipt = dict(result.metadata["receipt"])
            receipt.pop("abs_path", None)
            return receipt

        payload: Dict[str, Any] = {
            "content": result.content,
            "metadata": result.metadata or {},
        }
        content = payload.get("content", "")
        if isinstance(content, str) and len(content) > max_chars:
            payload["content"] = content[: max(0, max_chars - 3)] + "..."
            payload["truncated"] = True
            payload["original_content_length"] = len(content)

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata = json.loads(json.dumps(metadata, default=str))
            if isinstance(metadata.get("receipt"), dict):
                metadata["receipt"].pop("abs_path", None)
            payload["metadata"] = metadata

        return payload

    @staticmethod
    def _emit_audit(
        action: str,
        target: Optional[str],
        details: Optional[Dict[str, Any]],
        ctx: ToolExecutionContext,
    ) -> None:
        if not ctx.audit_log:
            return
        try:
            ctx.audit_log(action, target, details or {}, ctx.actor)
        except Exception:  # pragma: no cover - audit must never fail tool execution
            logger.debug("tool audit emission failed", exc_info=True)

