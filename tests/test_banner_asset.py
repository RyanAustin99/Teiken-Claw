from __future__ import annotations

import hashlib
from pathlib import Path

from teiken_claw.terminal.banner import load_banner_lines


def test_banner_asset_is_immutable() -> None:
    path = Path("teiken_claw/terminal/assets/banner_teiken_claw.txt")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == "2418b485a8586ab032a8a5ce91a91751dab3b8f2b25bee650a50779118dd002c"


def test_banner_asset_shape() -> None:
    lines = load_banner_lines()
    assert len(lines) == 6
    assert max(len(line) for line in lines) == 84

