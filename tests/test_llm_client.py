"""Tests for llm_client.py — streaming, retry, timeout, schema validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from novel_forge.llm_client import LLMClient, LLMError, SchemaValidationError, load_config

# ── Helpers ─────────────────────────────────────────────────────────────


def _make_streaming_response(chunks: list[str], status_code: int = 200) -> MagicMock:
    """Create a mock that simulates `with httpx.stream(...) as resp:` context manager."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.raise_for_status = MagicMock()
    lines = [chunk.encode() for chunk in chunks]
    mock_resp.iter_lines = MagicMock(return_value=iter(lines))
    # httpx.stream() returns a context manager that yields the response
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_resp)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _ndjson_chunk(content: str, done: bool = False) -> str:
    """Create a single NDJSON chunk."""
    data = {"message": {"content": content}, "done": done}
    return json.dumps(data, ensure_ascii=False)


def _ndjson_response(full_text: str) -> list[str]:
    """Create a sequence of NDJSON chunks for a complete response."""
    chunk_size = 10
    chunks = []
    for i in range(0, len(full_text), chunk_size):
        piece = full_text[i : i + chunk_size]
        chunks.append(_ndjson_chunk(piece, done=False))
    chunks.append(_ndjson_chunk("", done=True))
    return chunks


# ── LLMClient initialization ────────────────────────────────────────────


class TestLLMClientInit:
    def test_default_values(self):
        client = LLMClient(api_url="http://localhost:11434/api/chat")
        assert client.model == "qwen3.6:35b-a3b-mtp-q4_K_M"
        assert client.timeout_seconds == 3600
        assert client.max_retries == 2
        assert client.num_ctx == 262144
        assert client.num_predict == -1

    def test_custom_values(self):
        client = LLMClient(
            api_url="http://custom:11434/api/chat",
            model="custom-model",
            timeout_seconds=120,
            max_retries=5,
            num_ctx=131072,
            num_predict=2048,
        )
        assert client.model == "custom-model"
        assert client.timeout_seconds == 120
        assert client.max_retries == 5
        assert client.num_ctx == 131072
        assert client.num_predict == 2048

    def test_ollama_options(self):
        client = LLMClient(
            api_url="http://localhost:11434/api/chat",
            ollama_options={"temperature": 0.8, "think": False},
        )
        assert client._ollama_options == {"temperature": 0.8, "think": False}

    def test_raw_log_settings(self, tmp_path):
        client = LLMClient(
            api_url="http://localhost:11434/api/chat",
            raw_log_dir=tmp_path,
            raw_log_enabled=True,
        )
        assert client.raw_log_dir == tmp_path
        assert client.raw_log_enabled is True


# ── complete_json — basic ──────────────────────────────────────────────


class TestCompleteJson:
    def test_basic_json_response(self):
        """complete_json should return parsed JSON from NDJSON streaming."""
        full_json = json.dumps({"key": "value", "number": 42}, ensure_ascii=False)
        chunks = _ndjson_response(full_json)
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(api_url="http://localhost:11434/api/chat")
            result = client.complete_json("test_kind", "system prompt", "user prompt")

        assert result == {"key": "value", "number": 42}

    def test_json_with_code_fences(self):
        """complete_json should strip markdown code fences."""
        full_json = "```json\n" + json.dumps({"a": 1}) + "\n```"
        chunks = _ndjson_response(full_json)
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(api_url="http://localhost:11434/api/chat")
            result = client.complete_json("test_kind", "sys", "usr")
        assert result == {"a": 1}

    def test_empty_response_raises(self):
        """Empty response should raise LLMError."""
        chunks = _ndjson_response("")
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(api_url="http://localhost:11434/api/chat")
            with pytest.raises(LLMError):
                client.complete_json("test_kind", "sys", "usr")

    def test_malformed_json_raises(self):
        """Malformed JSON should raise LLMError."""
        chunks = _ndjson_response("this is not json")
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(api_url="http://localhost:11434/api/chat")
            with pytest.raises(LLMError):
                client.complete_json("test_kind", "sys", "usr")


# ── complete_json — retry ──────────────────────────────────────────────


class TestCompleteJsonRetry:
    def test_retry_on_failure(self):
        """Should retry on httpx errors and succeed."""
        full_json = json.dumps({"ok": True})
        chunks = _ndjson_response(full_json)
        mock_resp = _make_streaming_response(chunks)

        import httpx

        call_count = 0

        def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            return mock_resp

        with patch("novel_forge.llm_client.httpx.stream", side_effect=mock_stream):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                max_retries=2,
            )
            result = client.complete_json("test_kind", "sys", "usr")
        assert result == {"ok": True}
        assert call_count == 2

    def test_retry_exhausted_raises(self):
        """Should raise LLMError after all retries exhausted."""
        import httpx

        with patch(
            "novel_forge.llm_client.httpx.stream", side_effect=httpx.TimeoutException("timeout")
        ):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                max_retries=2,
            )
            with pytest.raises(LLMError):
                client.complete_json("test_kind", "sys", "usr")

    def test_no_retry_when_zero(self):
        """max_retries=0 should not retry."""
        import httpx

        call_count = 0

        def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timeout")

        with patch("novel_forge.llm_client.httpx.stream", side_effect=mock_stream):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                max_retries=0,
            )
            with pytest.raises(LLMError):
                client.complete_json("test_kind", "sys", "usr")
        assert call_count == 1


# ── complete_json — payload structure ──────────────────────────────────


class TestCompleteJsonPayload:
    def test_payload_contains_required_fields(self):
        """Payload should contain model, messages, format, think, options."""
        chunks = _ndjson_response('{"ok": true}')
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp) as mock_stream:
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                model="test-model",
            )
            client.complete_json("test_kind", "my system", "my user")

        # Get the actual call payload
        call_args = mock_stream.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert payload["model"] == "test-model"
        assert payload["format"] == "json"
        assert payload["think"] is True
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "my system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "my user"
        assert "options" in payload
        assert "num_ctx" in payload["options"]
        assert "seed" in payload["options"]

    def test_think_false_in_options(self):
        """think=False should be passed as API-level param, not in options."""
        chunks = _ndjson_response('{"ok": true}')
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp) as mock_stream:
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                ollama_options={"think": False},
            )
            client.complete_json("test_kind", "sys", "usr")

        call_args = mock_stream.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["think"] is False
        # think should NOT be in options
        assert "think" not in payload["options"]

    def test_custom_ollama_options_in_payload(self):
        """Custom ollama_options should appear in payload options."""
        chunks = _ndjson_response('{"ok": true}')
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp) as mock_stream:
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                ollama_options={"temperature": 0.9, "top_p": 0.95},
            )
            client.complete_json("test_kind", "sys", "usr")

        call_args = mock_stream.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["options"]["temperature"] == 0.9
        assert payload["options"]["top_p"] == 0.95


# ── complete_json — raw log ────────────────────────────────────────────


class TestCompleteJsonRawLog:
    def test_raw_log_saved_when_enabled(self, tmp_path):
        """Raw log should be saved when raw_log_enabled=True."""
        full_json = json.dumps({"test": "data"}, ensure_ascii=False)
        chunks = _ndjson_response(full_json)
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                raw_log_enabled=True,
            )
            client.complete_json("test_kind", "sys prompt", "usr prompt")

        # Check that raw log files were created
        log_files = list(tmp_path.rglob("*.json.gz"))
        assert len(log_files) > 0

    def test_no_raw_log_when_disabled(self, tmp_path):
        """No raw log files when raw_log_enabled=False."""
        chunks = _ndjson_response('{"ok": true}')
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                raw_log_enabled=False,
            )
            client.complete_json("test_kind", "sys", "usr")

        log_files = list(tmp_path.rglob("*.json.gz"))
        assert len(log_files) == 0


# ── SchemaValidationError ──────────────────────────────────────────────


class TestSchemaValidationError:
    def test_is_llm_error_subclass(self):
        assert issubclass(SchemaValidationError, LLMError)

    def test_can_be_raised(self):
        with pytest.raises(SchemaValidationError):
            raise SchemaValidationError("field X is missing")


# ── load_config ────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("llm:\n  model: test-model\n", encoding="utf-8")

        config = load_config(config_file)
        assert config["llm"]["model"] == "test-model"

    def test_return_empty_on_missing(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config == {}

    def test_return_empty_on_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("{{invalid yaml", encoding="utf-8")

        config = load_config(config_file)
        assert config == {}

    def test_return_empty_on_non_dict(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- item1\n- item2\n", encoding="utf-8")

        config = load_config(config_file)
        assert config == {}
