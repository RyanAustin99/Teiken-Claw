import pytest

from app.interfaces.tc_profile_strip import extract_tc_profile


def test_extract_tc_profile_valid_block():
    raw = '<tc_profile>{"agent_display_name":"Forge","agent_voice":["calm"]}</tc_profile>\n\nHello there.'
    profile, stripped, error = extract_tc_profile(raw)
    assert error is None
    assert profile is not None
    assert profile["agent_display_name"] == "Forge"
    assert stripped == "Hello there."


def test_extract_tc_profile_missing_block():
    raw = "Hello there."
    profile, stripped, error = extract_tc_profile(raw)
    assert profile is None
    assert error is None
    assert stripped == raw


def test_extract_tc_profile_invalid_json_is_stripped_without_leak():
    raw = "<tc_profile>{invalid json}</tc_profile>\n\nHi."
    profile, stripped, error = extract_tc_profile(raw)
    assert profile is None
    assert error is not None
    assert "<tc_profile>" not in stripped
    assert "invalid json" not in stripped
    assert stripped == "Hi."

