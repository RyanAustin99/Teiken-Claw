"""Single-instance lock management for control-plane entry."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from app.control_plane.domain.errors import SingleInstanceError


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = (proc.stdout or "").strip()
            if not output:
                return False
            if output.upper().startswith("INFO:"):
                return False
            reader = csv.reader(io.StringIO(output))
            for row in reader:
                if not row:
                    continue
                if row[0].strip().upper().startswith("INFO:"):
                    return False
                if len(row) >= 2:
                    try:
                        return int(row[1].strip()) == pid
                    except ValueError:
                        continue
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


@dataclass
class LockInfo:
    pid: int
    started_at: float
    host: str


class SingleInstanceLock:
    """File lock with stale-lock detection."""

    def __init__(self, lock_path: Path, stale_after_sec: int = 3600) -> None:
        self.lock_path = lock_path
        self.stale_after_sec = stale_after_sec
        self._acquired = False

    def read_lock(self) -> Optional[LockInfo]:
        if not self.lock_path.exists():
            return None
        try:
            payload: Dict[str, object] = json.loads(self.lock_path.read_text(encoding="utf-8"))
            return LockInfo(
                pid=int(payload.get("pid", 0)),
                started_at=float(payload.get("started_at", 0.0)),
                host=str(payload.get("host", "unknown")),
            )
        except Exception:
            return None

    def is_stale(self, lock_info: Optional[LockInfo]) -> bool:
        if lock_info is None:
            return False
        if _pid_exists(lock_info.pid):
            return False
        # If PID is gone, treat lock as stale immediately.
        return True

    def acquire(self, force_unlock: bool = False) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        info = self.read_lock()
        if info and not force_unlock:
            if not self.is_stale(info):
                raise SingleInstanceError(
                    lock_path=str(self.lock_path),
                    details={"pid": info.pid, "host": info.host},
                )
            self.force_unlock()
        elif info and force_unlock:
            self.force_unlock()

        payload = {
            "pid": os.getpid(),
            "started_at": time.time(),
            "host": os.getenv("COMPUTERNAME", "unknown"),
        }
        self.lock_path.write_text(json.dumps(payload), encoding="utf-8")
        self._acquired = True

    def release(self) -> None:
        if self._acquired and self.lock_path.exists():
            self.lock_path.unlink(missing_ok=True)
        self._acquired = False

    def force_unlock(self) -> None:
        self.lock_path.unlink(missing_ok=True)

