"""Tests for llm_client.py — streaming, retry, timeout, schema validation."""

from __future__ import annotations

import gzip
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


def _ndjson_chunk(content: str, done: bool = False, thinking: str = "") -> str:
    """Create a single NDJSON chunk."""
    message = {"content": content}
    if thinking:
        message["thinking"] = thinking
    data = {"message": message, "done": done}
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
        assert client.transport_retries == 2
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
        assert client.transport_retries == 5
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
        )
        assert client.raw_log_dir == tmp_path


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
        """Should raise LLMError after all transport retries are exhausted."""
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

    def test_retries_json_parse_failure(self):
        """Malformed model output should retry as an invalid generation."""
        bad_resp = _make_streaming_response(_ndjson_response("not json"))
        good_resp = _make_streaming_response(_ndjson_response(json.dumps({"ok": True})))

        with patch("novel_forge.llm_client.httpx.stream", side_effect=[bad_resp, good_resp]) as mock_stream:
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                max_retries=2,
            )
            result = client.complete_json("test_kind", "sys", "usr")

        assert result == {"ok": True}
        assert mock_stream.call_count == 2

    def test_retries_schema_echo_failure(self):
        """Schema echo should retry as an invalid generation."""
        schema_echo = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        bad_resp = _make_streaming_response(_ndjson_response(json.dumps(schema_echo)))
        good_resp = _make_streaming_response(_ndjson_response(json.dumps({"ok": True})))

        with patch("novel_forge.llm_client.httpx.stream", side_effect=[bad_resp, good_resp]) as mock_stream:
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                max_retries=2,
            )
            result = client.complete_json("test_kind", "sys", "usr")

        assert result == {"ok": True}
        assert mock_stream.call_count == 2

    def test_retries_schema_validation_failure(self):
        """Schema validation failures should retry before surfacing to callers."""
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        bad_resp = _make_streaming_response(_ndjson_response(json.dumps({"bad": True})))
        good_resp = _make_streaming_response(_ndjson_response(json.dumps({"ok": True})))

        with patch("novel_forge.llm_client.httpx.stream", side_effect=[bad_resp, good_resp]) as mock_stream:
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                max_retries=2,
            )
            result = client.complete_json("test_kind", "sys", "usr", schema)

        assert result == {"ok": True}
        assert mock_stream.call_count == 2

    def test_normalizes_review_readiness_from_blocking_flags(self):
        """Review readiness should be derived from publication_blocking flags."""
        review = {
            "ready_for_publication": True,
            "issues": [
                {"severity": "重要", "field": "x", "description": "x", "suggestion": "x", "before": "x", "after": "x"},
                {
                    "severity": "重要",
                    "field": "y",
                    "description": "y",
                    "suggestion": "y",
                    "before": "y",
                    "after": "y",
                    "publication_blocking": True,
                },
            ],
        }

        LLMClient._normalize_review_output(review)

        assert review["ready_for_publication"] is False
        assert review["issues"][0]["publication_blocking"] is False

    def test_normalizes_review_ready_true_when_no_blocking_flags(self):
        """A ready=false review with no blocking issues should become ready=true."""
        review = {
            "ready_for_publication": False,
            "issues": [
                {
                    "severity": "重要",
                    "field": "x",
                    "description": "x",
                    "suggestion": "x",
                    "before": "x",
                    "after": "x",
                    "publication_blocking": False,
                }
            ],
        }

        LLMClient._normalize_review_output(review)

        assert review["ready_for_publication"] is True

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
    @staticmethod
    def _read_gzip(path):
        with gzip.open(path, "rb") as f:
            return f.read().decode("utf-8")

    def test_raw_log_preserves_exact_request_and_response_payload(self, tmp_path):
        """Raw log should save exact outgoing payload and exact incoming NDJSON."""
        full_json = json.dumps({"test": "data"}, ensure_ascii=False)
        chunks = _ndjson_response(full_json)
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                phase="write",
            )
            client.complete_json("test_kind", "sys prompt", "usr prompt")

        request_files = list(tmp_path.rglob("details/request_0_0.json.gz"))
        response_files = list(tmp_path.rglob("details/response_0_0.json.gz"))
        assert len(request_files) == 1
        assert len(response_files) == 1

        payload = json.loads(self._read_gzip(request_files[0]))
        assert payload["messages"] == [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "usr prompt"},
        ]
        assert self._read_gzip(response_files[0]) == "\n".join(chunks)

    def test_raw_log_preserves_failed_json_parse_response(self, tmp_path):
        """Raw log should be written even when parsing fails."""
        chunks = _ndjson_response("this is not json")
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                max_retries=1,
                phase="write",
            )
            with pytest.raises(LLMError):
                client.complete_json("test_kind", "sys", "usr")

        request_files = list(tmp_path.rglob("details/request_0_0.json.gz"))
        response_files = list(tmp_path.rglob("details/response_0_0.json.gz"))
        assert len(request_files) == 1
        assert len(response_files) == 1
        assert self._read_gzip(response_files[0]) == "\n".join(chunks)

    def test_raw_log_transport_retries_use_distinct_attempt_files(self, tmp_path):
        """Transport retries must keep every attempt's request and response without overwriting."""
        import httpx

        good_chunks = _ndjson_response(json.dumps({"ok": True}))
        good_resp = _make_streaming_response(good_chunks)

        with patch("novel_forge.llm_client.httpx.stream", side_effect=[httpx.TimeoutException("timeout"), good_resp]):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                transport_retries=2,
                phase="write",
            )
            assert client.complete_json("test_kind", "sys", "usr") == {"ok": True}

        for filename in [
            "request_0_0.json.gz",
            "response_0_0.json.gz",
            "request_1_0.json.gz",
            "response_1_0.json.gz",
        ]:
            assert len(list(tmp_path.rglob(f"details/{filename}"))) == 1

    def test_raw_log_multiple_same_kind_calls_do_not_overwrite(self, tmp_path):
        """Two calls with same kind must produce two independent raw-log call dirs."""
        first_chunks = _ndjson_response(json.dumps({"n": 1}))
        second_chunks = _ndjson_response(json.dumps({"n": 2}))

        with patch(
            "novel_forge.llm_client.httpx.stream",
            side_effect=[
                _make_streaming_response(first_chunks),
                _make_streaming_response(second_chunks),
            ],
        ):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                phase="write",
            )
            assert client.complete_json("test_kind", "sys1", "usr1") == {"n": 1}
            assert client.complete_json("test_kind", "sys2", "usr2") == {"n": 2}

        request_files = sorted(tmp_path.rglob("details/request_0_0.json.gz"))
        response_files = sorted(tmp_path.rglob("details/response_0_0.json.gz"))
        assert len(request_files) == 2
        assert len(response_files) == 2
        request_payloads = [json.loads(self._read_gzip(path)) for path in request_files]
        assert [p["messages"][1]["content"] for p in request_payloads] == ["usr1", "usr2"]

    def test_human_summary_is_split_and_excludes_thinking(self, tmp_path):
        """Human-readable summaries should be separate from raw gzip and omit thinking."""
        chunks = [
            _ndjson_chunk('{"ok": ', thinking="internal chain of thought"),
            _ndjson_chunk('true}', done=True, thinking="more private reasoning"),
        ]
        mock_resp = _make_streaming_response(chunks)

        with patch("novel_forge.llm_client.httpx.stream", return_value=mock_resp):
            client = LLMClient(
                api_url="http://localhost:11434/api/chat",
                raw_log_dir=tmp_path,
                phase="plan",
                model="test-model",
                ollama_options={"think": True, "temperature": 0.1},
            )
            assert client.complete_json("test_kind", "sys prompt", "usr prompt") == {"ok": True}

        call_dirs = [path for path in (tmp_path / "plan").iterdir() if path.is_dir()]
        assert len(call_dirs) == 1
        call_dir = call_dirs[0]

        assert (call_dir / "details" / "request_0_0.json.gz").exists()
        assert (call_dir / "details" / "response_0_0.json.gz").exists()
        assert not (call_dir / "details" / "response.json.gz").exists()
        assert (call_dir / "summary.md").exists()
        assert (call_dir / "summary" / "request_0_0.md").exists()
        assert (call_dir / "summary" / "response_0_0.md").exists()

        response_summary = (call_dir / "summary" / "response_0_0.md").read_text(encoding="utf-8")
        aggregate_summary = (call_dir / "summary.md").read_text(encoding="utf-8")
        request_summary = (call_dir / "summary" / "request_0_0.md").read_text(encoding="utf-8")

        assert "internal chain of thought" not in response_summary
        assert "more private reasoning" not in response_summary
        assert "thinking" not in response_summary
        assert '"ok": true' in response_summary
        assert "test-model" in request_summary
        assert "temperature" in request_summary
        assert "usr prompt" in request_summary
        assert "response_0_0" in aggregate_summary


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

    def test_env_path_takes_precedence_over_cwd_config(self, monkeypatch, tmp_path):
        cwd_config = tmp_path / "config.yaml"
        cwd_config.write_text("llm:\n  model: cwd-model\n", encoding="utf-8")
        env_config = tmp_path / "env-config.yaml"
        env_config.write_text("llm:\n  model: env-model\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("NOVEL_FORGE_CONFIG", str(env_config))

        config = load_config()

        assert config["llm"]["model"] == "env-model"
