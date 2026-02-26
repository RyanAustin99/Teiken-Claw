"""Local JSON config persistence with schema-version migrations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


CURRENT_CONFIG_VERSION = 2


class ConfigStore:
    """Persist non-secret user config in a small JSON file."""

    def __init__(self, config_file: Path) -> None:
        self.config_file = config_file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return {"config_version": CURRENT_CONFIG_VERSION}
        try:
            payload = json.loads(self.config_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"config_version": CURRENT_CONFIG_VERSION}
            migrated = self._migrate(payload)
            return migrated
        except Exception:
            return {"config_version": CURRENT_CONFIG_VERSION}

    def save(self, payload: Dict[str, Any]) -> None:
        data = dict(payload)
        data["config_version"] = CURRENT_CONFIG_VERSION
        temp_file = self.config_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        temp_file.replace(self.config_file)

    def patch(self, patch_data: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.load()
        existing.update(patch_data)
        self.save(existing)
        return self.load()

    def _migrate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        version = int(payload.get("config_version", 0))
        migrated = dict(payload)
        if version < 1:
            migrated["config_version"] = 1
        if "configured" not in migrated:
            migrated["configured"] = False
        if version < 2 and "agent_prompt_template_version" not in migrated:
            migrated["agent_prompt_template_version"] = "1.0.0"
            migrated["config_version"] = 2
        return migrated

