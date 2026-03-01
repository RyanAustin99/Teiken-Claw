from __future__ import annotations

import pytest

from app.tools.files_service import FileOperationError, FileOperationsService


class _CaptureAuditLogger:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def log_event(self, **kwargs):
        self.events.append(dict(kwargs))


MALICIOUS_PATHS = [
    "../outside.md",
    "../../outside.md",
    "..\\outside.md",
    "notes/../../outside.md",
    "/etc/passwd",
    "C:\\Windows\\System32\\drivers\\etc\\hosts",
    "\\\\server\\share\\x.md",
    "\x00bad.md",
    "notes/\x1fbad.md",
    "notes/..",
    "./../../x.md",
    "///etc/passwd",
    "D:/temp/x.md",
    "C:relative-drive.md",
    "..%2foutside.md",
    "%2e%2e/outside.md",
    "notes//..//..//x.md",
    " .. /x.md ",
    "../notes/evil.md",
    "notes\\..\\..\\evil.md",
]


def test_abuse_paths_fail_and_are_audited(monkeypatch, tmp_path):
    capture = _CaptureAuditLogger()
    monkeypatch.setattr("app.tools.files_service.get_file_audit_logger", lambda: capture)

    service = FileOperationsService(tmp_path)

    failures = 0
    for idx, path in enumerate(MALICIOUS_PATHS, start=1):
        with pytest.raises(FileOperationError) as exc:
            service.write_text_file(path, f"payload-{idx}")
        failures += 1
        assert exc.value.code.startswith("ERR_") or exc.value.code in {"WRITE_ERROR", "PERMISSION_DENIED"}

    assert failures == len(MALICIOUS_PATHS)
    assert len(capture.events) == len(MALICIOUS_PATHS)
    assert all(event.get("status") == "failure" for event in capture.events)
    assert all(event.get("op") == "write" for event in capture.events)

