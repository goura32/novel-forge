from __future__ import annotations

import gzip
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import httpx
from jsonschema import ValidationError as JsonSchemaValidationError

from novel_forge.json_parser import JsonParseError, parse_json_response
from novel_forge.logging_config import Console, get_logger

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
        self.raw_log_dir = raw_log_dir
        self.phase = phase
        self.num_ctx = num_ctx if num_ctx else 262144
        self.num_predict = num_predict
        self._ollama_options = ollama_options or {}
        self._log = get_logger("novel_forge.llm")
        self._last_progress_log: float = 0.0
        self._current_kind: str = ""
        self._call_sequence: int = 0
        self._active_call_dir: Path | None = None
        self._run_timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
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
        self._active_call_dir = None
        attempt_limit = max(self.transport_retries, 1)
        last_error: LLMError | None = None

        for attempt in range(attempt_limit):
            payload["messages"][1]["content"] = current_prompt
            base_seed = payload["options"]["seed"]
            payload["options"]["seed"] = base_seed + attempt + seed_offset
            self._write_raw_log(f"request_{attempt}_{seed_offset}", json.dumps(payload, ensure_ascii=False))
            self._append_raw_summary(f"request_{attempt}_{seed_offset}", json.dumps(payload, ensure_ascii=False))

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
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                self._write_content_log(f"response_{attempt}_{seed_offset}", raw)
                self._append_raw_summary(f"response_{attempt}_{seed_offset}", raw_text)

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
                return cast(dict[str, Any], parsed)

            except RuntimeError:
                # --strict mode: propagate after saving raw log
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                raise
            except JsonParseError as e:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                raise LLMError(f"JSON parse error: {str(e)[:200]}") from e
            except (SchemaValidationError, JsonSchemaValidationError) as e:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                raise LLMError(f"schema validation error: {str(e)[:200]}") from e
            except LLMTransportError as e:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                last_error = e
            except LLMError:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                raise
            except Exception:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
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
            self._write_raw_log("_timeout", text)
            raise LLMTransportError("Ollama request timed out") from None
        except httpx.HTTPStatusError as e:
            self._write_raw_log("_http_err", str(e))
            raise LLMTransportError(f"Ollama HTTP error: {e}") from e
        except httpx.RequestError as e:
            text = "\n".join(lines)
            self._write_raw_log("_transport_err", text or str(e))
            raise LLMTransportError(f"Ollama transport error: {e}") from e
        text = "\n".join(lines)
        result, thinking_combined = self._parse_ndjson(text)
        if not result or not result.strip():
            self._write_raw_log("_empty", text)
            raise LLMError("Ollama returned empty response")
        return text, result, thinking_combined, "", chunk_count, total_bytes

    def _make_call_dir(self, kind: str) -> Path:
        """1回のLLM呼び出し用のディレクトリを作成して返す。

        Format: {raw_log_dir}/{phase}/{timestamp}_{pid}_{sequence}_{kind}/
        sequenceで同一kindの複数呼び出しを区別し、リトライや再実行でも上書きを防ぐ。
        """
        if not self.raw_log_dir:
            return Path("/dev/null")  # dummy
        if self._active_call_dir is not None:
            return self._active_call_dir
        phase = self.phase if self.phase else "unknown"
        import os as _os
        pid = _os.getpid()
        run_dir = (
            self.raw_log_dir
            / phase
            / f"{self._run_timestamp}_{pid}_{self._call_sequence:04d}_{kind}"
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "details").mkdir(exist_ok=True)
        self._active_call_dir = run_dir
        return run_dir

    @staticmethod
    def _non_overwriting_path(path: Path) -> Path:
        """Return path or a suffixed sibling so existing raw logs are never overwritten."""
        if not path.exists():
            return path
        suffixes = "".join(path.suffixes)
        stem = path.name[: -len(suffixes)] if suffixes else path.name
        for i in range(1, 10000):
            candidate = path.with_name(f"{stem}_{i}{suffixes}")
            if not candidate.exists():
                return candidate
        raise FileExistsError(f"Could not find free raw log path for {path}")

    def _write_raw_log(self, file_type: str, raw_text: str) -> None:
        """1回のLLM呼び出しで2ファイルを書き出す。

        file_type: "request" または "response"
        """
        if not self.raw_log_dir:
            return
        call_dir = self._make_call_dir(self._current_kind)
        try:
            gz_path = self._non_overwriting_path(call_dir / "details" / f"{file_type}.json.gz")
            with gzip.open(gz_path, "wb") as f:
                f.write(raw_text.encode("utf-8"))
        except Exception as e:
            self._log.debug("  [RAW LOG WRITE FAILED] %s", e)

    def _write_content_log(self, file_type: str, content_text: str) -> None:
        """Write the LLM content only (no thinking, no NDJSON wrapper) as plain JSON.

        This makes post-hoc analysis trivial: json.load() the .content.json file
        directly instead of parsing Ollama streaming NDJSON.
        """
        if not self.raw_log_dir:
            return
        if file_type.startswith("request"):
            return
        call_dir = self._make_call_dir(self._current_kind)
        try:
            path = self._non_overwriting_path(call_dir / f"{file_type}.content.json")
            path.write_text(content_text, encoding="utf-8")
        except Exception as e:
            self._log.debug("  [CONTENT LOG WRITE FAILED] %s", e)

    def _append_raw_summary(self, file_type: str, raw_text: str) -> None:
        """Write human-readable summaries next to exact raw gzip files.

        Layout per LLM call:
        - summary.md: compact chronological index for the call
        - summary/<request_or_response>.md: split readable payloads
        - details/*.json.gz: exact raw payloads (written by _write_raw_log)
        """
        if not self.raw_log_dir:
            return
        call_dir = self._make_call_dir(self._current_kind)
        summary_dir = call_dir / "summary"
        summary_path = call_dir / "summary.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = self._format_for_summary(file_type, raw_text)
        try:
            summary_dir.mkdir(exist_ok=True)
            split_path = summary_dir / f"{file_type}.md"
            split_path.write_text(
                f"# {file_type}\n\n"
                f"- generated_at: {ts}\n"
                f"- kind: {self._current_kind}\n"
                f"- phase: {self.phase or 'unknown'}\n\n"
                f"{content}\n",
                encoding="utf-8",
            )
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(
                    f"\n## {ts} — {file_type}\n\n"
                    f"- detail: `summary/{file_type}.md`\n"
                    f"- raw: `details/{file_type}.json.gz`\n"
                )
        except Exception as e:
            self._log.debug("  [SUMMARY WRITE FAILED] %s", e)

    @staticmethod
    def _content_from_ndjson(raw_text: str) -> str:
        """Return only streamed message.content from Ollama NDJSON.

        message.thinking and other transport metadata deliberately stay in
        details/*.json.gz only. Human summaries should show the prompt-visible
        answer, not private reasoning or stream wrappers.
        """
        parts: list[str] = []
        saw_ndjson = False
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict) or "message" not in chunk:
                continue
            saw_ndjson = True
            message = chunk.get("message")
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str) and content:
                    parts.append(content)
        if saw_ndjson:
            return "".join(parts)
        return raw_text

    def _format_request_for_summary(self, raw_text: str) -> str:
        try:
            payload = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            return raw_text.replace("\\n", "\n").replace('\\"', '"')

        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        metadata = {
            "model": payload.get("model"),
            "format": payload.get("format"),
            "think": payload.get("think"),
            "options": payload.get("options", {}),
        }
        parts = ["## API settings", "", "```json", json.dumps(metadata, ensure_ascii=False, indent=2), "```", ""]
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            content = content.replace("\\n", "\n").replace('\\"', '"')
            parts.append(f"## messages[{i}] ({role})\n\n{content}\n")
        return "\n".join(parts)

    def _format_response_for_summary(self, raw_text: str) -> str:
        content_text = self._content_from_ndjson(raw_text)
        try:
            parsed = parse_json_response(content_text)
            if isinstance(parsed, dict):
                return "```json\n" + json.dumps(parsed, ensure_ascii=False, indent=2) + "\n```\n"
            return "```\n" + str(parsed) + "\n```\n"
        except Exception:
            text = content_text.replace("\\n", "\n").replace('\\"', '"')
            return "```\n" + text + "\n```\n"

    def _format_for_summary(self, file_type: str, raw_text: str) -> str:
        """Format raw request/response into human-readable Markdown."""
        if file_type.startswith("request"):
            return self._format_request_for_summary(raw_text)
        return self._format_response_for_summary(raw_text)
