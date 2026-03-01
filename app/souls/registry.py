"""Versioned soul registry loader."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.config.settings import settings
from app.souls.schema import SoulDefinition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedSoul:
    ref: str
    definition: SoulDefinition
    sha256: str
    source_path: Path


class SoulRegistry:
    def __init__(self, souls_dir: Optional[str] = None) -> None:
        self._souls_dir = Path(souls_dir or getattr(settings, "SOULS_DIR", "./souls")).resolve()
        self._items: Dict[str, LoadedSoul] = {}
        self._by_name: Dict[str, List[str]] = {}
        self._loaded = False
        self._logged_deprecated = False

    def load(self, force: bool = False) -> None:
        if self._loaded and not force:
            return

        if not self._souls_dir.exists():
            self._items = {}
            self._by_name = {}
            self._loaded = True
            return

        items: Dict[str, LoadedSoul] = {}
        by_name: Dict[str, List[str]] = {}

        for path in sorted(self._souls_dir.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            soul = SoulDefinition.model_validate(payload)
            ref = f"{soul.name}@{soul.version}"
            canonical = json.dumps(soul.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if ref in items:
                raise ValueError(f"Duplicate soul definition: {ref}")
            loaded = LoadedSoul(ref=ref, definition=soul, sha256=digest, source_path=path)
            items[ref] = loaded
            by_name.setdefault(soul.name, []).append(ref)

        for name, refs in by_name.items():
            by_name[name] = sorted(refs)

        self._items = items
        self._by_name = by_name
        self._loaded = True

    def list_souls(self) -> List[LoadedSoul]:
        self.load()
        return [self._items[ref] for ref in sorted(self._items.keys())]

    def get_soul(self, name_or_ref: str) -> LoadedSoul:
        self.load()
        key = (name_or_ref or "").strip()
        if not key:
            raise KeyError("Soul reference is required")
        if "@" in key:
            loaded = self._items.get(key)
            if not loaded:
                raise KeyError(key)
            return loaded

        refs = self._by_name.get(key)
        if not refs:
            raise KeyError(key)
        return self._items[refs[-1]]

    def get_default_soul(self) -> LoadedSoul:
        default_ref = getattr(settings, "DEFAULT_SOUL_REF", "teiken_claw_agent@1.5.0")
        try:
            return self.get_soul(default_ref)
        except KeyError:
            souls = self.list_souls()
            if not souls:
                raise
            return souls[0]

    def log_legacy_deprecation_once(self) -> None:
        if self._logged_deprecated:
            return
        self._logged_deprecated = True
        logger.warning(
            "Legacy app.soul adapter path is in use; migrate to app.souls registry APIs",
            extra={"event": "soul_legacy_adapter_deprecated"},
        )


_registry: Optional[SoulRegistry] = None


def get_soul_registry() -> SoulRegistry:
    global _registry
    if _registry is None:
        _registry = SoulRegistry()
    force = bool(getattr(settings, "DEBUG", False) and getattr(settings, "SOULS_HOT_RELOAD", False))
    _registry.load(force=force)
    return _registry


def set_soul_registry(registry: SoulRegistry) -> None:
    global _registry
    _registry = registry
