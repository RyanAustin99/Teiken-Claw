from pathlib import Path


def test_tui_source_has_ascii_only_literals():
    tui_root = Path("app/control_plane/tui")
    for py_file in tui_root.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert content.isascii(), f"Non-ASCII characters found in {py_file}"
