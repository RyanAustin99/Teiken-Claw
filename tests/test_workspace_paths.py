from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.security.workspace_paths import (
    ERR_PATH_ABSOLUTE,
    ERR_PATH_OUTSIDE_SANDBOX,
    ERR_PATH_SYMLINK_ESCAPE,
    ERR_PATH_TRAVERSAL,
    PathPolicyError,
    initialize_workspace_context,
    normalize_user_path,
    resolve_in_sandbox,
)


def test_normalize_blocks_traversal():
    with pytest.raises(PathPolicyError) as exc:
        normalize_user_path("../outside.md")
    assert exc.value.code == ERR_PATH_TRAVERSAL


def test_normalize_blocks_nested_traversal():
    with pytest.raises(PathPolicyError) as exc:
        normalize_user_path("notes/../../outside.md")
    assert exc.value.code == ERR_PATH_TRAVERSAL


def test_normalize_blocks_absolute_posix():
    with pytest.raises(PathPolicyError) as exc:
        normalize_user_path("/etc/passwd")
    assert exc.value.code == ERR_PATH_ABSOLUTE


def test_normalize_blocks_windows_drive():
    with pytest.raises(PathPolicyError) as exc:
        normalize_user_path(r"C:\Windows\win.ini")
    assert exc.value.code == ERR_PATH_ABSOLUTE


def test_normalize_blocks_unc():
    with pytest.raises(PathPolicyError) as exc:
        normalize_user_path(r"\\server\share\x.md")
    assert exc.value.code == ERR_PATH_ABSOLUTE


def test_normalize_allows_valid_paths():
    assert normalize_user_path("notes/ok.md") == "notes/ok.md"
    assert normalize_user_path("notes//ok.md") == "notes/ok.md"
    assert normalize_user_path("notes/./ok.md") == "notes/ok.md"
    assert normalize_user_path("notes/../notes/today.md") == "notes/today.md"


def test_resolve_stays_within_workspace(tmp_path):
    ctx = initialize_workspace_context(tmp_path)
    resolved = resolve_in_sandbox(ctx, "notes/today.md")
    assert resolved.rel_path == "notes/today.md"
    assert str(resolved.abs_path).startswith(str(tmp_path.resolve()))


def test_resolve_blocks_outside_workspace(tmp_path):
    ctx = initialize_workspace_context(tmp_path)
    with pytest.raises(PathPolicyError) as exc:
        resolve_in_sandbox(ctx, "../x.md")
    assert exc.value.code == ERR_PATH_TRAVERSAL


def test_resolve_blocks_symlink_escape(tmp_path):
    ctx = initialize_workspace_context(tmp_path)
    outside_dir = tmp_path.parent / "outside_for_symlink"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "escape.txt"
    outside_file.write_text("escape", encoding="utf-8")

    link_path = tmp_path / "link_out"
    try:
        os.symlink(outside_dir, link_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not available on this platform/permissions")

    with pytest.raises(PathPolicyError) as exc:
        resolve_in_sandbox(ctx, "link_out/escape.txt")
    assert exc.value.code == ERR_PATH_SYMLINK_ESCAPE

