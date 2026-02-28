import pytest

pytest.importorskip("textual")

from textual.widgets import Static

from app.control_plane.tui.uikit import ErrorBanner, ErrorPayload


def test_error_banner_does_not_override_textual_render_hook() -> None:
    # Guard against clobbering Widget._render, which must return a visual.
    assert ErrorBanner._render is Static._render


def test_error_banner_show_and_toggle_updates_text() -> None:
    banner = ErrorBanner()
    payload = ErrorPayload(
        message="Boom",
        code="E_TEST",
        details="stack",
        correlation_id="cid-1",
        logs_path="C:/logs",
    )
    banner.show_error(payload)
    rendered = str(banner.render())
    assert "Error: Boom" in rendered
    assert "code=E_TEST" in rendered
    assert "Details: stack" not in rendered

    banner.toggle_details()
    rendered_with_details = str(banner.render())
    assert "Details: stack" in rendered_with_details
