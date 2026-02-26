"""Install/startup boot report schema and writers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class BootCheckResult:
    name: str
    ok: bool
    message: str
    latency_ms: int


@dataclass(frozen=True)
class BootReport:
    ts_utc: str
    duration_ms: int
    app_name: str
    version: str
    environment: str
    git_sha: str
    python: str
    platform: str
    config_redacted: Dict[str, Any]
    ports_and_urls: Dict[str, str]
    ollama: Dict[str, Any]
    limits: Dict[str, Any]
    checks: List[BootCheckResult]
    agents: List[Dict[str, Any]]
    workers: Dict[str, Any]
    exit_code: int


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(tmp, path)


def write_boot_report(report: BootReport, report_dir: str, latest_path: str) -> str:
    report_dir_path = Path(report_dir)
    report_dir_path.mkdir(parents=True, exist_ok=True)

    slug_ts = report.ts_utc.replace(":", "").replace("-", "")
    timestamped_path = report_dir_path / f"boot_report_{slug_ts}.json"
    payload = asdict(report)
    payload["checks"] = [asdict(check) for check in report.checks]

    _atomic_write_json(timestamped_path, payload)
    _atomic_write_json(Path(latest_path), payload)

    return str(timestamped_path)
