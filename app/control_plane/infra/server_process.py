"""Dev-server process management for the control plane supervisor."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DevServerStatus:
    running: bool
    host: str
    port: int
    pid: Optional[int] = None
    attached: bool = False

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class ServerProcessManager:
    """Manage uvicorn lifecycle with PID files and attach detection."""

    def __init__(self, pid_file: Path, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.pid_file = pid_file
        self.host = host
        self.port = port

    def start(self, attach_if_running: bool = True) -> DevServerStatus:
        current = self.status()
        if current.running:
            if attach_if_running:
                current.attached = True
                return current
            self.stop()

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(json.dumps({"pid": proc.pid, "host": self.host, "port": self.port}), encoding="utf-8")
        return DevServerStatus(running=True, host=self.host, port=self.port, pid=proc.pid, attached=False)

    def stop(self) -> DevServerStatus:
        status = self.status()
        if not status.running or not status.pid:
            self.pid_file.unlink(missing_ok=True)
            return DevServerStatus(running=False, host=self.host, port=self.port)

        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(status.pid), "/T", "/F"], check=False, capture_output=True)
            else:
                os.kill(status.pid, 15)
        except Exception:
            pass
        self.pid_file.unlink(missing_ok=True)
        return DevServerStatus(running=False, host=self.host, port=self.port, pid=status.pid)

    def restart(self) -> DevServerStatus:
        self.stop()
        return self.start(attach_if_running=False)

    def status(self) -> DevServerStatus:
        pid = None
        host = self.host
        port = self.port
        if self.pid_file.exists():
            try:
                payload = json.loads(self.pid_file.read_text(encoding="utf-8"))
                pid = int(payload.get("pid", 0))
                host = str(payload.get("host", host))
                port = int(payload.get("port", port))
            except Exception:
                pass

        running = self._is_port_open(host, port)
        if not running:
            pid = None
        return DevServerStatus(running=running, host=host, port=port, pid=pid)

    @staticmethod
    def _is_port_open(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0

