"""Log query/follow/export service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable, List, Optional


class LogService:
    """Read app logs for status and diagnostics."""

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.logs_dir / "app.log"
        self.json_log_file = self.logs_dir / "app.json.log"

    def query(self, component: Optional[str] = None, limit: int = 200) -> List[str]:
        file_path = self.log_file if self.log_file.exists() else self.json_log_file
        if not file_path.exists():
            return []
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if component:
            lines = [line for line in lines if component.lower() in line.lower()]
        return lines[-limit:]

    async def follow(self, component: Optional[str] = None, poll_sec: float = 0.5):
        file_path = self.log_file if self.log_file.exists() else self.json_log_file
        if not file_path.exists():
            return
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(0, 2)
            while True:
                line = handle.readline()
                if line:
                    if component is None or component.lower() in line.lower():
                        yield line.rstrip("\n")
                else:
                    await asyncio.sleep(poll_sec)

    def export(self, export_path: Path, lines: Iterable[str]) -> Path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text("\n".join(lines), encoding="utf-8")
        return export_path

