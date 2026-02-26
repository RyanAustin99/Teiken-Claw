"""Regression tests for queue throttles module import behavior."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest.mock import patch


def test_throttles_import_without_aiolimiter() -> None:
    """Module must import cleanly even when aiolimiter is unavailable."""
    import app.queue.throttles as throttles

    with patch.dict(sys.modules, {"aiolimiter": None}):
        reloaded: ModuleType = importlib.reload(throttles)
        assert reloaded.HAS_AIOLIMITER is False
        limiter = reloaded.RateLimiter(global_rate=1.0, per_chat_rate=1.0)
        assert limiter.get_stats()["has_aiolimiter"] is False

    # Restore normal module state for later tests.
    importlib.reload(throttles)

