"""Layered config service for control-plane settings."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Tuple

from pydantic import ValidationError as PydanticValidationError

from app.control_plane.domain.errors import ValidationError
from app.control_plane.domain.models import AppConfig, EffectiveConfig
from app.control_plane.infra.config_store import ConfigStore


class ConfigService:
    """Read/write validated config with env > local > defaults precedence."""

    RESTART_KEYS = {
        "ollama_endpoint",
        "default_model",
        "dev_server_host",
        "dev_server_port",
        "max_inflight_ollama_requests",
        "max_agent_queue_depth",
    }

    ENV_MAP = {
        "OLLAMA_BASE_URL": "ollama_endpoint",
        "OLLAMA_CHAT_MODEL": "default_model",
        "LOG_LEVEL": "log_level",
    }

    def __init__(self, store: ConfigStore) -> None:
        self.store = store

    def load(self) -> EffectiveConfig:
        local_payload = self.store.load()
        merged: Dict[str, Any] = {}
        source_map: Dict[str, str] = {}

        defaults = AppConfig().model_dump()
        merged.update(defaults)
        source_map.update({key: "default" for key in defaults.keys()})

        merged.update(local_payload)
        for key in local_payload.keys():
            source_map[key] = "local"

        for env_key, config_key in self.ENV_MAP.items():
            raw = os.getenv(env_key)
            if raw in (None, ""):
                continue
            merged[config_key] = raw
            source_map[config_key] = "env"

        try:
            parsed = AppConfig(**merged)
        except PydanticValidationError as exc:
            raise ValidationError("Config validation failed", details={"errors": str(exc)}) from exc

        return EffectiveConfig(values=parsed, sources=source_map)

    def validate_patch(self, patch: Dict[str, Any]) -> EffectiveConfig:
        current = self.load().values.model_dump()
        current.update(patch)
        try:
            parsed = AppConfig(**current)
        except PydanticValidationError as exc:
            raise ValidationError("Invalid configuration input", details={"errors": str(exc)}) from exc
        return EffectiveConfig(values=parsed, sources={})

    def save_patch(self, patch: Dict[str, Any], actor: str = "user") -> EffectiveConfig:
        validated = self.validate_patch(patch)
        self.store.patch(validated.values.model_dump())
        return self.load()

    def requires_restart(self, changed_keys: Iterable[str]) -> bool:
        return any(key in self.RESTART_KEYS for key in changed_keys)

    def mark_configured(self) -> None:
        self.store.patch({"configured": True})

