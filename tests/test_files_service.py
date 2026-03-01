from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.files_service import (
    ERR_BINARY_NOT_SUPPORTED,
    ERR_EXT_NOT_ALLOWED,
    ERR_FILE_TOO_LARGE,
    FileOperationError,
    FileOperationsService,
    FilePolicy,
)


def _service(tmp_path: Path, **policy_kwargs) -> FileOperationsService:
    policy = FilePolicy(**policy_kwargs)
    return FileOperationsService(tmp_path, policy=policy)


def test_write_and_read_roundtrip(tmp_path):
    svc = _service(tmp_path, max_read_bytes=1024 * 1024, max_write_bytes=1024 * 1024)
    write = svc.write_text_file("notes/plan.md", "hello world")
    assert write["ok"] is True
    assert (tmp_path / "notes" / "plan.md").read_text(encoding="utf-8") == "hello world"

    read = svc.read_text_file("notes/plan.md")
    assert read["ok"] is True
    assert read["content"] == "hello world"


def test_atomic_write_failure_does_not_corrupt_target(tmp_path, monkeypatch):
    svc = _service(tmp_path, max_read_bytes=1024 * 1024, max_write_bytes=1024 * 1024)
    target = tmp_path / "notes" / "plan.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old-content", encoding="utf-8")

    def _raise(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("app.tools.files_service.os.replace", _raise)

    with pytest.raises(FileOperationError) as exc:
        svc.write_text_file("notes/plan.md", "new-content")
    assert exc.value.code == "WRITE_ERROR"
    assert target.read_text(encoding="utf-8") == "old-content"


def test_oversized_write_blocked(tmp_path):
    svc = _service(tmp_path, max_read_bytes=1024 * 1024, max_write_bytes=10)
    with pytest.raises(FileOperationError) as exc:
        svc.write_text_file("notes/plan.md", "x" * 11)
    assert exc.value.code == ERR_FILE_TOO_LARGE
    assert not (tmp_path / "notes" / "plan.md").exists()


def test_overwrite_policy_respected(tmp_path):
    svc = _service(tmp_path, max_read_bytes=1024 * 1024, max_write_bytes=1024 * 1024, allow_overwrite=False)
    svc.write_text_file("notes/plan.md", "v1")
    with pytest.raises(FileOperationError) as exc:
        svc.write_text_file("notes/plan.md", "v2")
    assert exc.value.code == "ERR_OVERWRITE_NOT_ALLOWED"
    assert (tmp_path / "notes" / "plan.md").read_text(encoding="utf-8") == "v1"


def test_write_extension_allowlist(tmp_path):
    svc = _service(tmp_path, max_read_bytes=1024 * 1024, max_write_bytes=1024 * 1024)
    with pytest.raises(FileOperationError) as exc:
        svc.write_text_file("notes/run.exe", "nope")
    assert exc.value.code == ERR_EXT_NOT_ALLOWED


def test_binary_read_blocked(tmp_path):
    svc = _service(tmp_path, max_read_bytes=1024 * 1024, max_write_bytes=1024 * 1024)
    target = tmp_path / "notes" / "a.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x00\x01")
    with pytest.raises(FileOperationError) as exc:
        svc.read_text_file("notes/a.exe")
    assert exc.value.code == ERR_BINARY_NOT_SUPPORTED


def test_soft_limit_warning_logged(tmp_path, caplog):
    svc = _service(
        tmp_path,
        max_read_bytes=1024 * 1024,
        max_write_bytes=100,
        soft_write_warn_ratio=0.75,
    )
    with caplog.at_level("WARNING"):
        result = svc.write_text_file("notes/warn.md", "x" * 80)
    assert result["ok"] is True
    assert any("approaching_write_cap" in rec.message or rec.__dict__.get("event") == "approaching_write_cap" for rec in caplog.records)


def test_delete_file_only(tmp_path):
    svc = _service(tmp_path)
    svc.write_text_file("notes/delete.md", "remove")
    deleted = svc.delete("notes/delete.md")
    assert deleted["ok"] is True
    assert not (tmp_path / "notes" / "delete.md").exists()

    (tmp_path / "notes" / "dir").mkdir(parents=True, exist_ok=True)
    with pytest.raises(FileOperationError) as exc:
        svc.delete("notes/dir")
    assert exc.value.code == "NOT_FILE"

