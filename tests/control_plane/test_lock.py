from pathlib import Path

import pytest

from app.control_plane.domain.errors import SingleInstanceError
import app.control_plane.infra.lock as lock_mod
from app.control_plane.infra.lock import SingleInstanceLock


def test_single_instance_lock_blocks_second_holder(tmp_path):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock_a = SingleInstanceLock(lock_file)
    lock_b = SingleInstanceLock(lock_file)

    lock_a.acquire()
    try:
        with pytest.raises(SingleInstanceError):
            lock_b.acquire()
    finally:
        lock_a.release()


def test_stale_lock_is_replaced_when_pid_missing(tmp_path, monkeypatch):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock_a = SingleInstanceLock(lock_file)

    monkeypatch.setattr(lock_mod, "_pid_exists", lambda _pid: False)

    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text('{"pid": 999999, "started_at": 1, "host": "test"}', encoding="utf-8")
    lock_a.acquire()
    try:
        info = lock_a.read_lock()
        assert info is not None
        assert info.pid > 0
        assert info.pid != 999999
    finally:
        lock_a.release()


def test_pid_exists_windows_ignores_info_rows(monkeypatch):
    class _Proc:
        stdout = "INFO: No tasks are running which match the specified criteria.\r\n"

    monkeypatch.setattr(lock_mod.os, "name", "nt")
    monkeypatch.setattr(lock_mod.subprocess, "run", lambda *args, **kwargs: _Proc())
    assert lock_mod._pid_exists(12345) is False


def test_legacy_lock_with_non_teiken_pid_is_treated_stale(tmp_path, monkeypatch):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock = SingleInstanceLock(lock_file)

    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text('{"pid": 12345, "started_at": 1, "host": "test"}', encoding="utf-8")

    monkeypatch.setattr(lock_mod, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(lock_mod, "_pid_process_name", lambda _pid: "conhost.exe")
    monkeypatch.setattr(lock_mod, "_pid_commandline", lambda _pid: "conhost.exe --headless")

    info = lock.read_lock()
    assert info is not None
    assert lock.is_stale(info) is True


def test_lock_process_name_mismatch_is_treated_stale(tmp_path, monkeypatch):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock = SingleInstanceLock(lock_file)

    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        '{"pid": 12345, "started_at": 1, "host": "test", "process_name": "python.exe"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(lock_mod, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(lock_mod, "_pid_process_name", lambda _pid: "conhost.exe")
    monkeypatch.setattr(lock_mod, "_pid_commandline", lambda _pid: "conhost.exe --headless")

    info = lock.read_lock()
    assert info is not None
    assert lock.is_stale(info) is True


def test_python_pid_without_teiken_commandline_is_stale(tmp_path, monkeypatch):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock = SingleInstanceLock(lock_file)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        '{"pid": 12345, "started_at": 1, "host": "test", "process_name": "python.exe"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(lock_mod, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(lock_mod, "_pid_process_name", lambda _pid: "python.exe")
    monkeypatch.setattr(lock_mod, "_pid_commandline", lambda _pid: "python some_other_script.py")

    info = lock.read_lock()
    assert info is not None
    assert lock.is_stale(info) is True


def test_python_pid_with_teiken_commandline_is_not_stale(tmp_path, monkeypatch):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock = SingleInstanceLock(lock_file)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        '{"pid": 12345, "started_at": 1, "host": "test", "process_name": "python.exe"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(lock_mod, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(lock_mod, "_pid_process_name", lambda _pid: "python.exe")
    monkeypatch.setattr(lock_mod, "_pid_commandline", lambda _pid: "python -m app.control_plane.entrypoint")

    info = lock.read_lock()
    assert info is not None
    assert lock.is_stale(info) is False

