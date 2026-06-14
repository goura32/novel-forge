
import pytest
from novel_tool.llm.json_parser import extract_json_text, parse_json_response, JsonParseError


def test_extracts_json_from_markdown_fence():
    text = "```json\n{\"ok\": true}\n```"
    assert extract_json_text(text) == '{"ok": true}'


def test_extracts_first_json_object_after_reasoning_text():
    text = "説明です\n{\"title\": \"港の商人\", \"hooks\": [\"交易\"]}\n以上"
    assert parse_json_response(text)["title"] == "港の商人"


def test_raises_structured_error_for_invalid_json():
    with pytest.raises(JsonParseError) as exc:
        parse_json_response("not json")
    assert "JSON" in str(exc.value)
