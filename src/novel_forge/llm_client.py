from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, cast

import httpx
from jsonschema import ValidationError as JsonSchemaValidationError

from novel_forge.json_parser import JsonParseError, parse_json_response
from novel_forge.logging_config import Console, get_logger
from novel_forge.runtime import AttemptCapture

console = Console()
_log = get_logger("novel_forge.llm")

_OLLAMA_OPTION_KEYS = [
    "temperature", "top_k", "top_p", "repeat_penalty",
    "presence_penalty", "frequency_penalty", "num_ctx",
    "num_predict", "seed", "stop", "tfs_z", "typical_p",
    "mirostat", "mirostat_tau", "mirostat_eta", "penalize_newline",
]


def _build_ollama_options(llm_cfg: dict) -> dict:
    """config.yaml から ollama options 辞書を構築する。"""
    options = dict(llm_cfg.get("ollama_options") or {})
    for key in _OLLAMA_OPTION_KEYS:
        if key in llm_cfg and llm_cfg[key] is not None:
            options[key] = llm_cfg[key]
    if "think" in llm_cfg:
        options["think"] = llm_cfg["think"]
    return options


class LLMError(Exception):
    pass


class LLMTransportError(LLMError):
    """Transient LLM API/transport failure eligible for transport retries."""


class SchemaValidationError(LLMError):
    """Schema validation error with path information."""
    def __init__(self, message: str, absolute_path: list | None = None):
        super().__init__(message)
        self.message = message
        self.absolute_path = absolute_path or []


def _try_import_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        return None


_YAML = _try_import_yaml()


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """config.yaml を読み込んで設定 dict を返す。"""
    if _YAML is None:
        return {}

    paths_to_try = []
    if config_path:
        paths_to_try.append(config_path)
    else:
        env_path = os.environ.get("NOVEL_FORGE_CONFIG")
        if env_path:
            paths_to_try.append(Path(env_path))
        cwd = Path.cwd()
        for p in [cwd, *cwd.parents]:
            candidate = p / "config.yaml"
            if candidate.exists():
                paths_to_try.append(candidate)
                break

    for p in paths_to_try:
        try:
            with open(p, encoding="utf-8") as f:
                data = _YAML.safe_load(f)
            if isinstance(data, dict):
                return data
            _log.warning("Config file is not a mapping; ignoring: %s", p)
        except Exception as exc:
            _log.warning("Failed to load config file; ignoring: %s", p, exc_info=exc)
    return {}


class LLMClient:
    """LLM client for Ollama API."""

    _THINKING_TRUNCATE_THRESHOLD = 500
    _THINKING_KEEP_CHARS = 200

    def __init__(
        self,
        api_url: str | None = None,
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        timeout_seconds: int = 3600,
        max_retries: int | None = None,
        transport_retries: int | None = None,
        raw_log_dir: Path | None = None,
        capture: AttemptCapture | None = None,
        phase: str = "",
        num_ctx: int | None = None,
        num_predict: int = -1,
        ollama_options: dict[str, Any] | None = None,
        series_slug: str = "",
        volume: str = "",
    ):
        if api_url is None:
            host = os.environ.get("OLLAMA_HOST", "ws1.local:11434")
            api_url = f"http://{host}/api/chat"
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        resolved_transport_retries = transport_retries if transport_retries is not None else max_retries
        self.transport_retries = 2 if resolved_transport_retries is None else resolved_transport_retries
        self.max_retries = self.transport_retries  # Backward-compatible alias.
        self._series_slug = series_slug
        self._volume = volume
        # ``raw_log_dir`` is intentionally ignored by the destructive runtime
        # redesign.  LLM bodies may only be saved by an attempt-scoped capture.
        self.raw_log_dir = raw_log_dir
        self._capture = capture
        self.phase = phase
        self.num_ctx = num_ctx if num_ctx else 262144
        self.num_predict = num_predict
        self._ollama_options = ollama_options or {}
        self._log = get_logger("novel_forge.llm")
        self._last_progress_log: float = 0.0
        self._current_kind: str = ""
        self._call_sequence: int = 0

        if self._ollama_options.get("think", False):
            console.print(
                "[yellow]⚠ think=True is enabled — qwen3.6 thinking models may return empty "
                "content with format='json'. Consider think=False for production use.[/yellow]"
            )

    def _detect_max_ctx(self) -> int:
        """Ollama /api/show からモデルの context_length を取得する。"""
        host = os.environ.get("OLLAMA_HOST", "ws1.local:11434")
        show_url = f"http://{host.rsplit('/', 1)[0]}/api/show"
        try:
            resp = httpx.post(
                show_url,
                json={"name": self.model},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            model_info = data.get("model_info", {})
            for key, val in model_info.items():
                if key.endswith(".context_length") and isinstance(val, (int, float)):
                    return int(val)
        except Exception as e:
            self._log.warning("Could not detect max context length: %s", e)
        return 32768

    def complete_json(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
        seed_offset: int = 0,
    ) -> dict[str, Any]:
        payload = self._build_payload(system_prompt, user_prompt, schema)
        return self._retry_call(kind, payload, user_prompt, schema, seed_offset)

    def _build_payload(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """APIリクエストの payload を構築する。"""
        api_options = {k: v for k, v in self._ollama_options.items() if k != "think"}
        think_value = self._ollama_options.get("think", True)

        self._log.debug("build_payload called: schema=%s, user_prompt_len=%d, has_schema=%s",
                        type(schema).__name__, len(user_prompt), "{schema}" in user_prompt)

        if schema is not None:
            # Schema should already be injected by PromptManager.render()
            # Just verify schema is available for validation later
            pass
        else:
            self._log.warning("build_payload: schema is None")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "seed": int(time.time_ns() & 0xffffffff),
                **api_options,
            },
            "think": think_value,
        }

        self._log.debug("build_payload: payload user_prompt_len=%d, has_schema=%s",
                        len(payload["messages"][1]["content"]), "{schema}" in payload["messages"][1]["content"])

        return payload

    def _retry_call(
        self,
        kind: str,
        payload: dict[str, Any],
        user_prompt: str,
        schema: dict[str, Any] | None,
        seed_offset: int,
    ) -> dict[str, Any]:
        """Call the API with retries for transport and invalid model outputs."""
        # payload["messages"][1]["content"] already has {schema} replaced by _build_payload
        current_prompt = payload["messages"][1]["content"]
        self._current_kind = kind
        self._call_sequence += 1
        attempt_limit = max(self.transport_retries, 1)
        last_error: LLMError | None = None

        for attempt in range(attempt_limit):
            payload["messages"][1]["content"] = current_prompt
            base_seed = payload["options"]["seed"]
            payload["options"]["seed"] = base_seed + attempt + seed_offset
            if self._capture is not None:
                self._capture.request(payload)

            meta = self._build_meta()
            self._log.debug(
                "  [LLM CALL] kind=%s attempt=%d/%d model=%s seed=%d%s",
                kind, attempt + 1, attempt_limit, self.model, base_seed + attempt + seed_offset, meta,
            )

            raw_text = ""
            try:
                call_start = time.time()
                raw_text, raw, thinking, done_reason, chunk_count, total_bytes = self._call_api(payload)
                call_elapsed = time.time() - call_start

                self._log.debug(
                    "  [LLM DONE] kind=%s chunks=%d bytes=%d elapsed=%.1fs%s done=%s",
                    kind, chunk_count, total_bytes, call_elapsed, meta, done_reason,
                )
                self._capture_response(raw_text, raw)

                parsed = parse_json_response(raw)

                if self._is_schema_echo(parsed):
                    raise LLMError("LLM returned schema structure instead of data")

                if schema:
                    if kind == "review" and isinstance(parsed, dict):
                        self._normalize_review_output(parsed)
                    # Normalize slug before validation (LLM may output hyphens which
                    # the schema regex ^[a-z0-9_]+$ rejects — normalize to underscores first).
                    if isinstance(parsed, dict) and "slug" in parsed:
                        parsed["slug"] = re.sub(r"[^a-z0-9_]", "_", str(parsed["slug"]).lower())
                    from novel_forge.schemas import validate_data_or_raise
                    validate_data_or_raise(kind, schema, parsed)
                if self._capture is not None:
                    self._capture.parsed(cast(dict[str, Any], parsed))
                    self._capture.validation({"outcome": "passed"})
                return cast(dict[str, Any], parsed)

            except RuntimeError:
                raise
            except JsonParseError as e:
                if self._capture is not None:
                    self._capture.validation({"outcome": "failed", "error_code": "JSON_PARSE_ERROR"})
                raise LLMError(f"JSON parse error: {str(e)[:200]}") from e
            except (SchemaValidationError, JsonSchemaValidationError) as e:
                if self._capture is not None:
                    self._capture.validation({"outcome": "failed", "error_code": "SCHEMA_VALIDATION_ERROR"})
                raise LLMError(f"schema validation error: {str(e)[:200]}") from e
            except LLMTransportError as e:
                last_error = e
            except LLMError:
                raise
            except Exception:
                raise

            if attempt < attempt_limit - 1:
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d reason=%s%s",
                    kind, attempt + 1, attempt_limit, last_error, meta,
                )
                continue
            if last_error is not None:
                raise last_error

        raise LLMError("LLM request failed") from None

    def _build_meta(self) -> str:
        """ログ用のメタ文字列を構築する。"""
        meta = ""
        if self._series_slug:
            meta += f" series={self._series_slug}"
        if self._volume:
            meta += f" vol={self._volume}"
        return meta

    @staticmethod
    def _is_schema_echo(parsed: dict[str, Any]) -> bool:
        """LLMがスキーマ構造をそのまま返したか判定。"""
        schema_keys = {"$schema", "title", "type", "properties", "required", "description"}
        if not isinstance(parsed, dict):
            return False
        keys = set(parsed.keys())
        schema_key_count = len(keys & schema_keys)
        return schema_key_count >= 2 and "properties" in keys

    @staticmethod
    def _normalize_review_output(parsed: dict[str, Any]) -> None:
        """Drop legacy review bookkeeping fields before schema validation.

        The review schema intentionally contains only actionable issues.  Older
        prompts/models may still emit summary or publication-readiness fields;
        remove them so the pipeline contract stays issue-count based.
        """
        issues = parsed.get("issues")
        for key in (
            "ready_for_publication",
            "overall_assessment",
            "strengths",
            "recommendations",
            "score",
            "revision_needed",
        ):
            parsed.pop(key, None)
        if not isinstance(issues, list):
            return
        parsed["issues"] = issues[:8]
        for issue in parsed["issues"]:
            if not isinstance(issue, dict):
                continue
            issue.pop("publication_blocking", None)
            severity = issue.get("severity")
            if isinstance(severity, str):
                issue["severity"] = severity.strip()


    @staticmethod
    def _parse_ndjson(text: str) -> tuple[str, str]:
        """Parse NDJSON response into (content, thinking)."""
        parts: list[str] = []
        thinking_parts: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in chunk:
                raise LLMError(f"Ollama error: {chunk['error']}")
            msg = chunk.get("message", {})
            content = msg.get("content", "")
            if content:
                parts.append(content)
            thinking = msg.get("thinking", "")
            if thinking and thinking not in thinking_parts:
                thinking_parts.append(thinking)
        return "".join(parts), "".join(thinking_parts)

    def _call_api(self, payload: dict[str, Any]) -> tuple[str, str, str, str, int, int]:
        """Call Ollama API with stream=True.

        Returns: (raw_text, content, thinking, done_reason, chunk_count, total_bytes)
        """
        stream_payload = {**payload, "stream": True}
        lines: list[str] = []
        chunk_count = 0
        total_bytes = 0
        call_start = time.time()
        try:
            with httpx.stream(
                "POST",
                self.api_url,
                json=stream_payload,
                timeout=self.timeout_seconds,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.strip():
                        lines.append(line.decode("utf-8") if isinstance(line, bytes) else line)
                        chunk_count += 1
                        total_bytes += len(line)
                        now = time.time()
                        if now - self._last_progress_log >= 60:
                            elapsed_total = now - call_start
                            self._log.info(
                                "  [LLM PROGRESS] chunks=%d bytes=%d elapsed=%.1fs%s",
                                chunk_count, total_bytes, elapsed_total, self._build_meta(),
                            )
                            self._last_progress_log = now
        except httpx.TimeoutException:
            text = "\n".join(lines)
            self._capture_response(text, "")
            raise LLMTransportError("Ollama request timed out") from None
        except httpx.HTTPStatusError as e:
            raise LLMTransportError(f"Ollama HTTP error: {e}") from e
        except httpx.RequestError as e:
            text = "\n".join(lines)
            self._capture_response(text, "")
            raise LLMTransportError(f"Ollama transport error: {e}") from e
        text = "\n".join(lines)
        result, thinking_combined = self._parse_ndjson(text)
        if not result or not result.strip():
            self._capture_response(text, "")
            raise LLMError("Ollama returned empty response")
        return text, result, thinking_combined, "", chunk_count, total_bytes

    def _capture_response(self, raw_text: str, content: str) -> None:
        """Persist a streamed response only when an attempt capture is attached.

        Raw bodies are never written unless the capture is verbose; content is
        kept separately so verbatim analysis matches the parsed object.
        """
        if self._capture is None:
            return
        lines: list[dict[str, Any]] = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._capture.response_ndjson(lines)
        if content:
            self._capture.response_content(content)
