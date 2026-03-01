from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_settings_debug_accepts_release_alias() -> None:
    cfg = Settings(DEBUG="release")
    assert cfg.DEBUG is False


def test_settings_debug_accepts_dev_alias() -> None:
    cfg = Settings(DEBUG="development")
    assert cfg.DEBUG is True


def test_settings_debug_invalid_value_still_fails() -> None:
    with pytest.raises(ValidationError):
        Settings(DEBUG="definitely-not-a-bool")
