"""Versioned mode registry loader."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.config.settings import settings
from app.modes.schema import ModeDefinition


@dataclass(frozen=True)
class LoadedMode:
    ref: str
    definition: ModeDefinition
    sha256: str
    source_path: Path


class ModeRegistry:
    def __init__(self, modes_dir: Optional[str] = None) -> None:
        self._modes_dir = Path(modes_dir or getattr(settings, "MODES_DIR", "./modes")).resolve()
        self._items: Dict[str, LoadedMode] = {}
        self._by_name: Dict[str, List[str]] = {}
        self._loaded = False

    def load(self, force: bool = False) -> None:
        if self._loaded and not force:
            return

        if not self._modes_dir.exists():
            self._items = {}
            self._by_name = {}
            self._loaded = True
            return

        items: Dict[str, LoadedMode] = {}
        by_name: Dict[str, List[str]] = {}

        for path in sorted(self._modes_dir.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            mode = ModeDefinition.model_validate(payload)
            ref = f"{mode.name}@{mode.version}"
            canonical = json.dumps(mode.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if ref in items:
                raise ValueError(f"Duplicate mode definition: {ref}")
            loaded = LoadedMode(ref=ref, definition=mode, sha256=digest, source_path=path)
            items[ref] = loaded
            by_name.setdefault(mode.name, []).append(ref)

        for name, refs in by_name.items():
            by_name[name] = sorted(refs)

        self._items = items
        self._by_name = by_name
        self._loaded = True

    def list_modes(self) -> List[LoadedMode]:
        self.load()
        return [self._items[ref] for ref in sorted(self._items.keys())]

    def get_mode(self, name_or_ref: str) -> LoadedMode:
        self.load()
        key = (name_or_ref or "").strip()
        if not key:
            raise KeyError("Mode reference is required")
        if "@" in key:
            loaded = self._items.get(key)
            if not loaded:
                raise KeyError(key)
            return loaded

        refs = self._by_name.get(key)
        if not refs:
            raise KeyError(key)
        return self._items[refs[-1]]

    def get_default_mode(self) -> LoadedMode:
        default_ref = getattr(settings, "DEFAULT_MODE_REF", "builder@1.5.0")
        try:
            return self.get_mode(default_ref)
        except KeyError:
            modes = self.list_modes()
            if not modes:
                raise
            return modes[0]


_registry: Optional[ModeRegistry] = None


def get_mode_registry() -> ModeRegistry:
    global _registry
    if _registry is None:
        _registry = ModeRegistry()
    force = bool(getattr(settings, "DEBUG", False) and getattr(settings, "MODES_HOT_RELOAD", False))
    _registry.load(force=force)
    return _registry


def set_mode_registry(registry: ModeRegistry) -> None:
    global _registry
    _registry = registry
