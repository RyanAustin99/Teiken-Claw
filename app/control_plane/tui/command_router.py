"""Command router for the terminal UI control plane."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from app.control_plane.bootstrap import ControlPlaneContext
from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AgentRecord, RunnerType, RuntimeStatus


@dataclass
class CommandResult:
    output: str = ""
    clear_output: bool = False
    exit_app: bool = False


class TuiCommandRouter:
    """Parse and execute TUI commands via service-layer contracts."""

    def __init__(self, context: ControlPlaneContext) -> None:
        self.context = context
        self.active_agent_id: Optional[str] = None
        self.active_session_id: Optional[str] = None

    def current_prompt(self) -> str:
        if self.active_agent_id:
            agent = self.context.agent_service.get_agent(self.active_agent_id)
            label = agent.name if agent else self.active_agent_id[:8]
            return f"chat({label})>"
        return "teiken>"

    async def execute(self, raw_command: str) -> CommandResult:
        raw = raw_command.strip()
        if not raw:
            return CommandResult()

        prefixed = False
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            raise ValidationError("Invalid command syntax.", details={"error": str(exc)})

        if not parts:
            return CommandResult()
        if parts[0].lower() == "teiken":
            prefixed = True
            parts = parts[1:]
            if not parts:
                return CommandResult(output=self.help_text())

        command = parts[0].lower()
        args = parts[1:]

        if command in {"help", "?", "/help"}:
            return CommandResult(output=self.help_text())
        if command in {"clear", "/clear"}:
            return CommandResult(clear_output=True)
        if command in {"quit", "exit", "/exit"}:
            return CommandResult(exit_app=True)

        handlers = {
            "status": self._status,
            "doctor": self._doctor,
            "models": self._models,
            "agents": self._agents,
            "config": self._config,
            "hatch": self._hatch,
            "chat": self._chat,
            "logs": self._logs,
            "server": self._server,
        }
        handler = handlers.get(command)
        if handler:
            return await handler(args)

        if self.active_session_id and not prefixed:
            return await self._chat_send(raw)
        raise ValidationError(
            "Unknown command.",
            details={"hint": "Type `help` for supported commands.", "command": raw},
        )

    def help_text(self) -> str:
        return "\n".join(
            [
                "Commands:",
                "  status",
                "  doctor [--export]",
                "  models [list|select <model>|validate [model]|pull <model>]",
                "  agents [list|start|stop|restart|default|delete --yes] <agent>",
                "  hatch --name <name> [--description <text>] [--model <model>] [--tool-profile <safe|balanced|dangerous>] [--allow-dangerous] [--no-start]",
                "  chat [start <agent>|continue <agent>|send <message>|history [--limit N]|stop]",
                "  config [show|set <key> <value> ...]",
                "  logs [--limit N] [--audit] [--export]",
                "  server [status|start|stop|restart]",
                "  clear",
                "  quit",
                "",
                "Tip: If chat is active, plain text is sent as a chat message.",
            ]
        )

    async def _status(self, _args: Sequence[str]) -> CommandResult:
        snapshot = self.context.runtime_supervisor.snapshot()
        lines = [
            f"Dev server: {'running' if snapshot.dev_server_running else 'stopped'}",
            f"URL: {snapshot.dev_server_url or 'n/a'}",
            f"Ollama inflight: {snapshot.global_inflight_ollama}/{snapshot.max_inflight_ollama}",
            f"Running agents: {len(snapshot.runtimes)}",
        ]
        for runtime in snapshot.runtimes:
            lines.append(
                f"- {runtime.agent_id[:8]} {runtime.status.value} queued={runtime.queued} overflow={runtime.overflow_count}"
            )
        return CommandResult(output="\n".join(lines))

    async def _doctor(self, args: Sequence[str]) -> CommandResult:
        export = "--export" in args
        report = await self.context.doctor_service.run_checks()
        lines = [f"Doctor overall: {report.overall_status.value}"]
        for check in report.checks:
            lines.append(f"[{check.status.value}] {check.name}: {check.summary}")
            if check.suggestion:
                lines.append(f"  fix: {check.suggestion}")

        if export:
            export_file = self.context.paths.exports_dir / "doctor_report.txt"
            self.context.log_service.export(export_file, lines)
            lines.append(f"Exported: {export_file}")

        return CommandResult(output="\n".join(lines))

    async def _models(self, args: Sequence[str]) -> CommandResult:
        if not args or args[0].lower() in {"list", "ls"}:
            models = await self.context.model_service.list_models()
            default_model = self.context.config_service.load().values.default_model
            lines = [f"Default model: {default_model}", f"Installed models ({len(models)}):"]
            lines.extend([f"- {name}" for name in models] or ["- <none>"])
            return CommandResult(output="\n".join(lines))

        action = args[0].lower()
        if action == "select":
            model_name = self._require_arg(args, 1, "Model name required for `models select`.")
            self.context.model_service.select_default_model(model_name)
            self.context.audit_service.log("model.select_default", target=model_name, details={}, actor="tui")
            return CommandResult(output=f"Default model set: {model_name}")

        if action == "validate":
            model_name = args[1] if len(args) > 1 else None
            result = await self.context.model_service.validate_model(model_name)
            return CommandResult(
                output="\n".join(
                    [
                        f"Validation ok={result['ok']} latency={result['latency_ms']}ms",
                        result["response_preview"] or "<empty response>",
                    ]
                )
            )

        if action == "pull":
            model_name = self._require_arg(args, 1, "Model name required for `models pull`.")
            result = await self.context.model_service.pull_model(model_name=model_name)
            self.context.audit_service.log(
                "model.pull",
                target=model_name,
                details={"progress_events": len(result.get("progress", []))},
                actor="tui",
            )
            return CommandResult(output=f"Pulled model: {model_name}")

        raise ValidationError("Unsupported models command.", details={"args": list(args)})

    async def _agents(self, args: Sequence[str]) -> CommandResult:
        if not args or args[0].lower() in {"list", "ls"}:
            return CommandResult(output=self._render_agents())

        action = args[0].lower()
        if action in {"start", "stop", "restart", "default", "delete"}:
            agent_ref = self._require_arg(args, 1, f"Agent reference required for `agents {action}`.")
            agent = self._resolve_agent(agent_ref)

            if action == "start":
                entry = await self.context.runtime_supervisor.start_agent(agent.id)
                self.context.audit_service.log(
                    "agent.start", target=agent.id, details={"status": entry.status.value}, actor="tui"
                )
                return CommandResult(output=f"Started {agent.name}: {entry.status.value}")

            if action == "stop":
                entry = await self.context.runtime_supervisor.stop_agent(agent.id)
                self.context.audit_service.log(
                    "agent.stop", target=agent.id, details={"status": entry.status.value}, actor="tui"
                )
                if self.active_agent_id == agent.id:
                    self.active_agent_id = None
                    self.active_session_id = None
                return CommandResult(output=f"Stopped {agent.name}: {entry.status.value}")

            if action == "restart":
                entry = await self.context.runtime_supervisor.restart_agent(agent.id)
                self.context.audit_service.log(
                    "agent.restart", target=agent.id, details={"status": entry.status.value}, actor="tui"
                )
                return CommandResult(output=f"Restarted {agent.name}: {entry.status.value}")

            if action == "default":
                self.context.agent_service.set_default_agent(agent.id)
                self.context.audit_service.log("agent.set_default", target=agent.id, details={}, actor="tui")
                return CommandResult(output=f"Default agent set: {agent.name}")

            if "--yes" not in args[2:]:
                raise ValidationError("`agents delete` requires explicit confirmation.", details={"hint": "Use --yes"})
            deleted = self.context.agent_service.delete_agent(agent.id)
            if deleted:
                self.context.audit_service.log("agent.delete", target=agent.id, details={}, actor="tui")
            if self.active_agent_id == agent.id:
                self.active_agent_id = None
                self.active_session_id = None
            return CommandResult(output=f"Deleted: {agent.name}" if deleted else "Agent not found.")

        raise ValidationError("Unsupported agents command.", details={"args": list(args)})

    async def _config(self, args: Sequence[str]) -> CommandResult:
        if not args or args[0].lower() in {"show", "list"}:
            effective = self.context.config_service.load()
            lines = ["Config:"]
            for key, value in effective.values.model_dump().items():
                lines.append(f"- {key}={value} ({effective.sources.get(key, 'local')})")
            return CommandResult(output="\n".join(lines))

        action = args[0].lower()
        if action != "set":
            raise ValidationError("Unsupported config command.", details={"hint": "Use `config` or `config set ...`"})

        if len(args) < 3 or len(args[1:]) % 2 != 0:
            raise ValidationError(
                "Invalid config set syntax.",
                details={"hint": "Use `config set <key> <value> [<key> <value> ...]`"},
            )

        patch: Dict[str, object] = {}
        cursor = 1
        while cursor < len(args):
            key = args[cursor].strip().lower().replace("-", "_")
            raw_value = args[cursor + 1]
            cursor += 2
            mapped_key = {
                "host": "dev_server_host",
                "port": "dev_server_port",
                "dangerous_tools": "dangerous_tools_enabled",
                "dangerous_tools_enabled": "dangerous_tools_enabled",
            }.get(key, key)

            if mapped_key in {"dangerous_tools_enabled", "subprocess_runner_enabled", "configured"}:
                patch[mapped_key] = self._parse_bool(raw_value, key_name=mapped_key)
            elif mapped_key in {"dev_server_port", "max_inflight_ollama_requests", "max_agent_queue_depth"}:
                patch[mapped_key] = self._parse_int(raw_value, key_name=mapped_key)
            else:
                patch[mapped_key] = raw_value

        self.context.config_service.save_patch(patch)
        self.context.audit_service.log(
            "config.change",
            target="config",
            details={"patch_keys": sorted(patch.keys())},
            actor="tui",
        )
        effective = self.context.config_service.load()
        lines = ["Config updated.", f"Restart recommended: {self.context.config_service.requires_restart(patch.keys())}"]
        lines.extend(f"- {key}={effective.values.model_dump().get(key)}" for key in sorted(patch.keys()))
        return CommandResult(output="\n".join(lines))

    async def _hatch(self, args: Sequence[str]) -> CommandResult:
        parsed = self._parse_hatch_args(args)
        config = self.context.config_service.load().values
        if parsed["tool_profile"] == "dangerous" and not config.dangerous_tools_enabled:
            raise ValidationError(
                "dangerous tool profile is disabled by config.",
                details={"hint": "Set `dangerous_tools_enabled=true` first."},
            )

        runner = RunnerType(parsed["runner"])
        existing = self.context.agent_service.get_agent(str(parsed["name"]))
        if existing:
            agent = existing
            lines = [f"Using existing agent: {agent.name} ({agent.id})"]
        else:
            agent = self.context.agent_service.create_agent(
                name=parsed["name"],
                description=parsed["description"],
                model=parsed["model"],
                runner_type=runner,
                tool_profile=parsed["tool_profile"],
                allow_dangerous_override=parsed["allow_dangerous"],
                prompt_template_version=config.agent_prompt_template_version,
            )
            lines = [f"Hatched agent: {agent.name} ({agent.id})"]
        if not parsed["no_start"]:
            try:
                await self.context.runtime_supervisor.start_agent(agent.id)
                session = self.context.session_service.new_session(agent.id, title=f"{agent.name} session")
                self.active_agent_id = agent.id
                self.active_session_id = session.id
                lines.append(f"Started runtime and opened chat session: {session.id}")
            except Exception as exc:
                self.context.agent_service.set_status(agent.id, status=RuntimeStatus.CRASHED, last_error=str(exc))
                lines.append("Runtime start failed. Agent kept as crashed.")
                lines.append("Recovery: run `doctor`, then `agents restart <agent>` or edit model/config.")
        else:
            lines.append("Runtime not started (--no-start).")
        self.context.audit_service.log(
            "agent.hatch",
            target=agent.id,
            details={
                "name": agent.name,
                "runner_type": runner.value,
                "tool_profile": parsed["tool_profile"],
            },
            actor="tui",
        )
        return CommandResult(output="\n".join(lines))

    async def _chat(self, args: Sequence[str]) -> CommandResult:
        if not args:
            if not self.active_session_id:
                return CommandResult(output="No active chat. Use `chat start <agent>`.")
            return CommandResult(
                output=f"Active chat: agent={self.active_agent_id} session={self.active_session_id}. "
                "Send plain text or use `chat send <message>`."
            )

        action = args[0].lower()
        if action in {"start", "continue"}:
            agent_ref = self._require_arg(args, 1, f"`chat {action}` requires an agent reference.")
            agent = self._resolve_agent(agent_ref)
            if action == "continue":
                sessions = self.context.session_service.list_sessions(agent.id, limit=1)
                session = sessions[0] if sessions else self.context.session_service.new_session(agent.id, title=f"{agent.name} chat")
            else:
                force_new = "--new" in args[2:]
                if force_new:
                    session = self.context.session_service.new_session(agent.id, title=f"{agent.name} chat")
                else:
                    sessions = self.context.session_service.list_sessions(agent.id, limit=1)
                    session = sessions[0] if sessions else self.context.session_service.new_session(
                        agent.id, title=f"{agent.name} chat"
                    )
            self.active_agent_id = agent.id
            self.active_session_id = session.id
            await self.context.runtime_supervisor.start_agent(agent.id)
            return CommandResult(output=f"Chat ready: {agent.name} ({session.id})")

        if action == "send":
            message = " ".join(args[1:]).strip()
            if not message:
                raise ValidationError("`chat send` requires a message.")
            return await self._chat_send(message)

        if action == "history":
            if not self.active_session_id:
                raise ValidationError("No active chat session.")
            limit = self._option_int(args[1:], "--limit", default=20)
            transcript = self.context.session_service.get_transcript(self.active_session_id)
            if not transcript:
                return CommandResult(output="No messages in active session.")
            recent = transcript[-limit:]
            lines = [f"History ({len(recent)} messages):"]
            for item in recent:
                lines.append(f"- {item.role}: {item.content}")
            return CommandResult(output="\n".join(lines))

        if action in {"stop", "close"}:
            self.active_agent_id = None
            self.active_session_id = None
            return CommandResult(output="Chat session cleared.")

        if action == "sessions":
            agent_ref = self._require_arg(args, 1, "`chat sessions` requires an agent reference.")
            agent = self._resolve_agent(agent_ref)
            limit = self._option_int(args[2:], "--limit", default=10)
            sessions = self.context.session_service.list_sessions(agent.id, limit=limit)
            if not sessions:
                return CommandResult(output=f"No sessions for {agent.name}.")
            lines = [f"Sessions for {agent.name}:"]
            lines.extend(f"- {session.id} ({session.updated_at.isoformat()})" for session in sessions)
            return CommandResult(output="\n".join(lines))

        raise ValidationError("Unsupported chat command.", details={"args": list(args)})

    async def _chat_send(self, message: str) -> CommandResult:
        if not self.active_agent_id or not self.active_session_id:
            raise ValidationError("No active chat session. Use `chat start <agent>`.")
        response = await self.context.runtime_supervisor.chat(
            agent_id=self.active_agent_id,
            session_id=self.active_session_id,
            message=message,
        )
        return CommandResult(output=f"assistant> {response}")

    async def _logs(self, args: Sequence[str]) -> CommandResult:
        limit = self._option_int(args, "--limit", default=50)
        export = "--export" in args
        audit = "--audit" in args

        if audit:
            events = self.context.audit_service.list_recent(limit=limit)
            if not events:
                return CommandResult(output="No audit events.")
            lines = [
                f"{item['created_at']} {item['action']} target={item['target']} details={item['details']}"
                for item in events
            ]
        else:
            lines = self.context.log_service.query(limit=limit)
            if not lines:
                lines = ["No log lines found."]

        if export:
            export_file = self.context.paths.exports_dir / "logs_export.txt"
            self.context.log_service.export(export_file, lines)
            lines.append(f"Exported: {export_file}")

        return CommandResult(output="\n".join(lines))

    async def _server(self, args: Sequence[str]) -> CommandResult:
        action = args[0].lower() if args else "status"
        if action == "status":
            snapshot = self.context.runtime_supervisor.snapshot()
            return CommandResult(
                output=f"Dev server: {'running' if snapshot.dev_server_running else 'stopped'} "
                f"({snapshot.dev_server_url or 'n/a'})"
            )
        if action == "start":
            snapshot = self.context.runtime_supervisor.start_dev_server()
            return CommandResult(output=f"Dev server started: {snapshot.dev_server_url or 'n/a'}")
        if action == "stop":
            self.context.runtime_supervisor.stop_dev_server()
            return CommandResult(output="Dev server stopped.")
        if action == "restart":
            snapshot = self.context.runtime_supervisor.restart_dev_server()
            return CommandResult(output=f"Dev server restarted: {snapshot.dev_server_url or 'n/a'}")
        raise ValidationError("Unsupported server command.", details={"args": list(args)})

    def _resolve_agent(self, agent_ref: str) -> AgentRecord:
        direct = self.context.agent_service.get_agent(agent_ref)
        if direct:
            return direct

        candidates = []
        lowered = agent_ref.lower()
        for agent in self.context.agent_service.list_agents():
            if agent.id.startswith(agent_ref) or agent.name.lower() == lowered:
                candidates.append(agent)

        if not candidates:
            raise ValidationError("Unknown agent.", details={"agent": agent_ref})
        if len(candidates) > 1:
            raise ValidationError(
                "Ambiguous agent reference.",
                details={"agent": agent_ref, "matches": [item.id for item in candidates]},
            )
        return candidates[0]

    def _render_agents(self) -> str:
        agents = self.context.agent_service.list_agents()
        if not agents:
            return "No agents yet. Use `hatch --name <name>`."
        lines = ["Agents:"]
        for agent in agents:
            lines.append(
                f"- {agent.id[:8]} name={agent.name} status={agent.status.value} "
                f"model={agent.model or '(global)'} default={'yes' if agent.is_default else 'no'}"
            )
        return "\n".join(lines)

    @staticmethod
    def _require_arg(args: Sequence[str], index: int, message: str) -> str:
        if len(args) <= index or not args[index].strip():
            raise ValidationError(message)
        return args[index].strip()

    @staticmethod
    def _parse_bool(value: str, key_name: str) -> bool:
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValidationError("Invalid boolean value.", details={"key": key_name, "value": value})

    @staticmethod
    def _parse_int(value: str, key_name: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ValidationError("Invalid integer value.", details={"key": key_name, "value": value}) from exc

    @staticmethod
    def _option_int(args: Sequence[str], flag: str, default: int) -> int:
        if flag not in args:
            return default
        idx = list(args).index(flag)
        if idx + 1 >= len(args):
            raise ValidationError("Option missing value.", details={"flag": flag})
        return TuiCommandRouter._parse_int(args[idx + 1], key_name=flag)

    def _parse_hatch_args(self, args: Sequence[str]) -> Dict[str, object]:
        parsed: Dict[str, object] = {
            "name": None,
            "description": None,
            "model": None,
            "runner": RunnerType.INPROCESS.value,
            "tool_profile": "safe",
            "allow_dangerous": False,
            "no_start": False,
        }
        index = 0
        while index < len(args):
            token = args[index]
            if token == "--name":
                parsed["name"] = self._require_arg(args, index + 1, "`hatch --name` requires value.")
                index += 2
                continue
            if token == "--description":
                parsed["description"] = self._require_arg(args, index + 1, "`hatch --description` requires value.")
                index += 2
                continue
            if token == "--model":
                parsed["model"] = self._require_arg(args, index + 1, "`hatch --model` requires value.")
                index += 2
                continue
            if token == "--runner":
                runner = self._require_arg(args, index + 1, "`hatch --runner` requires value.")
                if runner not in {item.value for item in RunnerType}:
                    raise ValidationError("Invalid runner type.", details={"runner": runner})
                parsed["runner"] = runner
                index += 2
                continue
            if token == "--tool-profile":
                parsed["tool_profile"] = self._require_arg(args, index + 1, "`hatch --tool-profile` requires value.")
                index += 2
                continue
            if token == "--allow-dangerous":
                parsed["allow_dangerous"] = True
                index += 1
                continue
            if token == "--no-start":
                parsed["no_start"] = True
                index += 1
                continue
            if token.startswith("--"):
                raise ValidationError("Unsupported hatch option.", details={"option": token})
            if not parsed["name"]:
                parsed["name"] = token
            else:
                parsed["description"] = (parsed["description"] or token)  # first free token becomes description
            index += 1

        if not parsed["name"]:
            raise ValidationError("`hatch` requires an agent name.", details={"hint": "Use `hatch --name <name>`"})
        return parsed
