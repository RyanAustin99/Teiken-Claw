"""Ollama model discovery, pull, selection, and validation."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.agent.ollama_client import OllamaClient
from app.control_plane.services.config_service import ConfigService


class ModelService:
    """Service facade for model operations."""

    def __init__(self, config_service: ConfigService) -> None:
        self.config_service = config_service

    def _client(self) -> OllamaClient:
        config = self.config_service.load().values
        return OllamaClient(
            base_url=config.ollama_endpoint,
            chat_model=config.default_model,
            embed_model=config.default_model,
        )

    async def detect_endpoint(self) -> Dict[str, Any]:
        config = self.config_service.load().values
        start = time.perf_counter()
        client = self._client()
        result = await client.check_health()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "ok": result.get("status") == "healthy",
            "endpoint": config.ollama_endpoint,
            "latency_ms": latency_ms,
            "details": result,
        }

    async def list_models(self) -> List[str]:
        client = self._client()
        models = await client.list_models()
        return [item.name for item in models]

    async def list_models_detailed(self) -> List[Dict[str, Any]]:
        """Return model metadata for richer TUI tables."""
        client = self._client()
        default_model = self.config_service.load().values.default_model
        models = await client.list_models()
        result: List[Dict[str, Any]] = []
        for item in models:
            result.append(
                {
                    "name": item.name,
                    "size": item.size,
                    "modified_at": item.modified_at,
                    "digest": item.digest,
                    "is_default": item.name == default_model,
                    "installed": True,
                }
            )
        return result

    async def pull_model(
        self,
        model_name: str,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        endpoint = self.config_service.load().values.ollama_endpoint.rstrip("/") + "/api/pull"
        progress = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(300)) as client:
            async with client.stream("POST", endpoint, json={"model": model_name, "stream": True}) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except Exception:
                        payload = {"status": line}
                    status = payload.get("status", "working")
                    progress.append(status)
                    if progress_cb:
                        progress_cb(status)
        return {"ok": True, "model": model_name, "progress": progress}

    def select_default_model(self, model_name: str) -> None:
        self.config_service.save_patch({"default_model": model_name}, actor="models")

    async def validate_model(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        config = self.config_service.load().values
        model = model_name or config.default_model
        start = time.perf_counter()
        client = self._client()
        response = await client.chat(
            messages=[{"role": "user", "content": "Reply with one word: pong"}],
            model=model,
            tools=None,
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "ok": bool(response.message.content),
            "model": model,
            "latency_ms": latency_ms,
            "response_preview": response.message.content[:120],
        }

    async def chat(self, message: str, model: Optional[str] = None) -> str:
        client = self._client()
        response = await client.chat(
            messages=[{"role": "user", "content": message}],
            model=model,
            tools=None,
        )
        return response.message.content
