
import json
import httpx
from novel_tool.llm.client import LLMClient


def test_client_sends_openai_compatible_request_and_parses_json(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "model-a"
        assert body["think"] is False
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"total_tokens": 3},
        })
    client = LLMClient(api_url="http://test/v1/chat/completions", model="model-a", timeout_seconds=10, raw_log_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = client.complete_json(kind="test", system_prompt="sys", user_prompt="user", schema={"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]})
    assert result.parsed == {"ok": True}
    assert result.usage["total_tokens"] == 3
    assert list(tmp_path.glob("**/*.json"))


def test_client_retries_after_invalid_json(tmp_path):
    calls = {"n": 0}
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "not json" if calls["n"] == 1 else '{"ok": true}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    client = LLMClient(api_url="http://test/v1/chat/completions", model="model-a", timeout_seconds=10, raw_log_dir=tmp_path, max_retries=1, transport=httpx.MockTransport(handler))
    assert client.complete_json(kind="retry", system_prompt="sys", user_prompt="user").parsed == {"ok": True}
    assert calls["n"] == 2
