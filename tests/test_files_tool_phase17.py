import hashlib

import pytest

from app.tools.files_tool import FilesWriteSubtool, runtime_workspace_root


@pytest.mark.asyncio
async def test_files_write_creates_file_and_receipt(tmp_path):
    tool = FilesWriteSubtool()
    with runtime_workspace_root(tmp_path):
        result = await tool.execute(path="hello.md", content="Hello")
    assert result.ok is True
    target = tmp_path / "hello.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Hello"
    receipt = result.metadata["receipt"]
    assert receipt["path"] == "hello.md"
    assert receipt["bytes"] == 5
    assert receipt["sha256"] == hashlib.sha256(b"Hello").hexdigest()


@pytest.mark.asyncio
async def test_files_write_blocks_traversal(tmp_path):
    tool = FilesWriteSubtool()
    with runtime_workspace_root(tmp_path):
        result = await tool.execute(path="../evil.md", content="nope")
    assert result.ok is False
    assert result.error_code == "PATH_SECURITY_ERROR"
    assert not (tmp_path.parent / "evil.md").exists()


@pytest.mark.asyncio
async def test_files_write_blocks_absolute_path(tmp_path):
    tool = FilesWriteSubtool()
    with runtime_workspace_root(tmp_path):
        result = await tool.execute(path=str((tmp_path / "abs.md").resolve()), content="nope")
    assert result.ok is False
    assert result.error_code == "PATH_SECURITY_ERROR"

