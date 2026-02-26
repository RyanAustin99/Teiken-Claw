"""Deterministic doctor checks and fix guidance."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, List

from app.control_plane.domain.models import CheckStatus, DoctorCheck, DoctorReport
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.model_service import ModelService


class DoctorService:
    """Runs health checks without requiring FastAPI service availability."""

    def __init__(
        self,
        config_service: ConfigService,
        model_service: ModelService,
        state_db_path: Path,
        runtime_supervisor: Any,
    ) -> None:
        self.config_service = config_service
        self.model_service = model_service
        self.state_db_path = state_db_path
        self.runtime_supervisor = runtime_supervisor

    async def run_checks(self) -> DoctorReport:
        checks: List[DoctorCheck] = []
        config = self.config_service.load().values

        # Storage writable
        try:
            self.state_db_path.parent.mkdir(parents=True, exist_ok=True)
            probe = self.state_db_path.parent / ".doctor_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            checks.append(DoctorCheck(name="storage", status=CheckStatus.PASS, summary="Storage path writable"))
        except Exception as exc:
            checks.append(
                DoctorCheck(
                    name="storage",
                    status=CheckStatus.FAIL,
                    summary="Storage path is not writable",
                    suggestion="Check folder permissions or choose a different --data-dir",
                    fix_action="open_config",
                    details={"error": str(exc)},
                )
            )

        # Ollama endpoint reachable
        try:
            endpoint = await self.model_service.detect_endpoint()
            if endpoint["ok"]:
                checks.append(
                    DoctorCheck(
                        name="ollama_endpoint",
                        status=CheckStatus.PASS,
                        summary=f"Ollama reachable ({endpoint['latency_ms']} ms)",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="ollama_endpoint",
                        status=CheckStatus.FAIL,
                        summary="Ollama endpoint unreachable",
                        suggestion="Run `ollama serve` or update endpoint via `teiken config`",
                        fix_action="open_config",
                    )
                )
        except Exception as exc:
            checks.append(
                DoctorCheck(
                    name="ollama_endpoint",
                    status=CheckStatus.FAIL,
                    summary="Ollama endpoint check failed",
                    suggestion="Verify Ollama is running and endpoint is correct",
                    fix_action="open_config",
                    details={"error": str(exc)},
                )
            )

        # Default model availability
        try:
            models = await self.model_service.list_models()
            if config.default_model in models:
                checks.append(
                    DoctorCheck(
                        name="default_model",
                        status=CheckStatus.PASS,
                        summary=f"Default model present: {config.default_model}",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="default_model",
                        status=CheckStatus.WARN,
                        summary=f"Default model missing: {config.default_model}",
                        suggestion=f"Run `teiken models pull {config.default_model}` or select another default",
                        fix_action="open_models",
                    )
                )
        except Exception as exc:
            checks.append(
                DoctorCheck(
                    name="default_model",
                    status=CheckStatus.WARN,
                    summary="Could not verify default model",
                    suggestion="Run `teiken models` to inspect installed models",
                    fix_action="open_models",
                    details={"error": str(exc)},
                )
            )

        # Dev server status
        snapshot = self.runtime_supervisor.snapshot()
        if snapshot.dev_server_running:
            checks.append(DoctorCheck(name="dev_server", status=CheckStatus.PASS, summary=f"Dev server running at {snapshot.dev_server_url}"))
        else:
            checks.append(
                DoctorCheck(
                    name="dev_server",
                    status=CheckStatus.WARN,
                    summary="Dev server not running",
                    suggestion="Run `teiken status` then `teiken` dashboard action to start server",
                    fix_action="restart_server",
                )
            )

        # Model validation
        try:
            validation = await self.model_service.validate_model(config.default_model)
            if validation["ok"]:
                checks.append(
                    DoctorCheck(
                        name="model_validation",
                        status=CheckStatus.PASS,
                        summary=f"Model responded ({validation['latency_ms']} ms)",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="model_validation",
                        status=CheckStatus.FAIL,
                        summary="Model validation failed",
                        suggestion="Try another model in `teiken models`",
                        fix_action="open_models",
                    )
                )
        except Exception as exc:
            checks.append(
                DoctorCheck(
                    name="model_validation",
                    status=CheckStatus.FAIL,
                    summary="Model did not respond",
                    suggestion="Check Ollama and pull/select a valid model",
                    fix_action="open_models",
                    details={"error": str(exc)},
                )
            )

        return DoctorReport(created_at=datetime.utcnow(), checks=checks)

