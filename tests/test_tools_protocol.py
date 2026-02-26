import json

from app.tools.protocol import (
    extract_tool_calls,
    extract_tool_results,
    render_tool_result,
    ToolResultEnvelope,
)


def test_extract_single_tool_call():
    text = (
        "Plan:\n"
        "<TEIKEN_TOOL_CALL>{\"id\":\"tc_1\",\"tool\":\"files.write\",\"args\":{\"path\":\"hello.md\",\"content\":\"Hello\"}}</TEIKEN_TOOL_CALL>\n"
        "Done."
    )
    parsed = extract_tool_calls(text)
    assert len(parsed.calls) == 1
    assert parsed.calls[0].tool == "files.write"
    assert parsed.calls[0].args["path"] == "hello.md"
    assert "TEIKEN_TOOL_CALL" not in parsed.clean_text


def test_extract_multiple_tool_calls():
    text = (
        "<TEIKEN_TOOL_CALL>{\"id\":\"tc_1\",\"tool\":\"files.list\",\"args\":{\"dir\":\".\"}}</TEIKEN_TOOL_CALL>"
        "<TEIKEN_TOOL_CALL>{\"id\":\"tc_2\",\"tool\":\"files.exists\",\"args\":{\"path\":\"hello.md\"}}</TEIKEN_TOOL_CALL>"
    )
    parsed = extract_tool_calls(text)
    assert [item.tool for item in parsed.calls] == ["files.list", "files.exists"]
    assert parsed.clean_text == ""


def test_code_fence_is_ignored():
    text = "```bash\nfiles.write(\"hello.md\", \"Hello\")\n```"
    parsed = extract_tool_calls(text)
    assert parsed.calls == []
    assert parsed.parse_failures == []
    assert "files.write" in parsed.clean_text


def test_invalid_json_does_not_crash():
    text = "<TEIKEN_TOOL_CALL>{not-json}</TEIKEN_TOOL_CALL>"
    parsed = extract_tool_calls(text)
    assert parsed.calls == []
    assert len(parsed.parse_failures) == 1
    assert parsed.parse_failures[0].ok is False
    assert parsed.parse_failures[0].error["type"] == "parse_error"


def test_render_and_extract_result_round_trip():
    envelope = ToolResultEnvelope(
        id="tc_1",
        tool="files.write",
        ok=True,
        result={"path": "hello.md", "bytes": 5},
        elapsed_ms=12,
    )
    rendered = render_tool_result(envelope)
    extracted = extract_tool_results(rendered)
    assert len(extracted) == 1
    assert extracted[0].tool == "files.write"
    assert extracted[0].result["path"] == "hello.md"
    assert json.loads(rendered.replace("<TEIKEN_TOOL_RESULT>", "").replace("</TEIKEN_TOOL_RESULT>", ""))["id"] == "tc_1"

