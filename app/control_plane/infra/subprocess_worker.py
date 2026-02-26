"""Minimal subprocess runner worker for deterministic IPC skeleton."""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any, Dict


def _emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _heartbeat_loop(stop_event: threading.Event, interval_sec: float = 2.0) -> None:
    while not stop_event.is_set():
        _emit({"event": "heartbeat", "ts": time.time()})
        stop_event.wait(interval_sec)


def main() -> None:
    stop_event = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat_loop, args=(stop_event,), daemon=True)
    heartbeat.start()

    _emit({"event": "ready", "ts": time.time()})

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            cmd = json.loads(raw)
            action = cmd.get("action")
            request_id = cmd.get("request_id")
            if action == "status":
                _emit({"event": "status", "request_id": request_id, "ok": True})
            elif action == "send_message":
                content = cmd.get("message", "")
                _emit(
                    {
                        "event": "message",
                        "request_id": request_id,
                        "ok": True,
                        "content": f"[subprocess runner] {content}",
                    }
                )
            elif action in ("stop", "shutdown"):
                _emit({"event": "stopped", "request_id": request_id, "ok": True})
                break
            elif action == "start":
                _emit({"event": "ready", "request_id": request_id, "ok": True})
            else:
                _emit(
                    {
                        "event": "error",
                        "request_id": request_id,
                        "ok": False,
                        "error": f"Unknown action: {action}",
                    }
                )
        except Exception as exc:  # pragma: no cover - defensive
            _emit({"event": "error", "ok": False, "error": str(exc)})

    stop_event.set()
    _emit({"event": "stopped", "ts": time.time()})


if __name__ == "__main__":
    main()

