from __future__ import annotations

import gzip
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from novel_forge.json_parser import JsonParseError, coerce_types, parse_json_response
from novel_forge.logging_config import Console, get_logger

console = Console()

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
        cwd = Path.cwd()
        for p in [cwd, *cwd.parents]:
            candidate = p / "config.yaml"
            if candidate.exists():
                paths_to_try.append(candidate)
                break
        env_path = os.environ.get("NOVEL_FORGE_CONFIG")
        if env_path:
            paths_to_try.append(Path(env_path))

    for p in paths_to_try:
        try:
            with open(p, encoding="utf-8") as f:
                data = _YAML.safe_load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
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
        max_retries: int = 2,
        raw_log_dir: Path | None = None,
        raw_log_enabled: bool = False,
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
        self.max_retries = max_retries
        self._series_slug = series_slug
        self._volume = volume
        self.raw_log_dir = raw_log_dir
        self.raw_log_enabled = raw_log_enabled
        self.phase = phase
        self.num_ctx = num_ctx if num_ctx else 262144
        self.num_predict = num_predict
        self._ollama_options = ollama_options or {}
        self._log = get_logger("novel_forge.llm")
        self._last_progress_log: float = 0.0
        self._current_kind: str = ""
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
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "seed": 42,
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
        """リトライ付きで API を呼び出す。"""
        # payload["messages"][1]["content"] already has {schema} replaced by _build_payload
        current_prompt = payload["messages"][1]["content"]
        self._current_kind = kind

        for attempt in range(max(self.max_retries, 1)):
            payload["messages"][1]["content"] = current_prompt
            payload["options"]["seed"] = 42 + attempt + seed_offset
            self._write_raw_log(f"request_{attempt}_{seed_offset}", json.dumps(payload, ensure_ascii=False))
            self._append_raw_summary(f"request_{attempt}_{seed_offset}", json.dumps(payload, ensure_ascii=False))

            meta = self._build_meta()
            self._log.debug(
                "  [LLM CALL] kind=%s attempt=%d/%d model=%s seed=%d%s",
                kind, attempt + 1, self.max_retries, self.model, 42 + attempt + seed_offset, meta,
            )

            raw_text = ""
            try:
                _call_start = time.time()
                raw_text, raw, thinking, done_reason, chunk_count, total_bytes = self._call_api(payload)
                _call_elapsed = time.time() - _call_start

                self._log.debug(
                    "  [LLM DONE] kind=%s chunks=%d bytes=%d elapsed=%.1fs%s done=%s",
                    kind, chunk_count, total_bytes, _call_elapsed, meta, done_reason,
                )
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                self._append_raw_summary(f"response_{attempt}_{seed_offset}", raw_text)

                parsed = parse_json_response(raw)

                if self._is_schema_echo(parsed):
                    self._log.warning(
                        "  [SCHEMA ECHO] kind=%s retry=%d — LLM returned schema structure, retrying",
                        kind, seed_offset,
                    )
                    current_prompt = (
                        f"前回の出力はスキーマ構造そのものでした。データ値を返してください。\\n"
                        f"必ずスキーマの properties に従って、実際のデータ値を埋めた JSON のみを出力してください。\\n\\n"
                        f"元の指示:\n{user_prompt}"
                    )
                    continue

                if schema:
                    parsed = coerce_types(parsed, schema)
                    from novel_forge.schemas import validate_or_raise
                    validate_or_raise(kind, parsed)
                return parsed

            except RuntimeError:
                # --strict mode: propagate after saving raw log
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                continue
            except JsonParseError as e:
                current_prompt = self._handle_retry_error(e, user_prompt, "JSON parse error")
                continue
            except SchemaValidationError as e:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                current_prompt = self._handle_retry_error(e, user_prompt, "schema validation error")
                continue
            except LLMError:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                continue
            except Exception:
                self._write_raw_log(f"response_{attempt}_{seed_offset}", raw_text)
                raise

        raise LLMError("LLM request failed") from None

    def _handle_retry_error(self, e: Exception, user_prompt: str, error_type: str) -> str:
        """リトライ時のエラーメッセージを生成する。"""
        error_hint = str(e)[:200]
        return (
            f"前回の出力は{error_type}でした。\n"
            f"エラー: {error_hint}\n"
            f"修正し、必ず有効なJSONのみを出力してください。\n\n"
            f"元の指示:\n{user_prompt}"
        )

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
        # トップレベルのキーの大部分がスキーマのメタキーなら「スキーマ返り」と判定
        keys = set(parsed.keys())
        schema_key_count = len(keys & schema_keys)
        # $schema + type + properties があればスキーマ構造
        return schema_key_count >= 2 and "properties" in keys

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
            raise LLMError("Ollama request timed out") from None
        except httpx.HTTPStatusError as e:
            self._write_raw_log("_http_err", str(e))
            raise LLMError(f"Ollama HTTP error: {e}") from e
        text = "\n".join(lines)
        result, thinking_combined = self._parse_ndjson(text)
        if not result or not result.strip():
            self._write_raw_log("_empty", text)
            raise LLMError("Ollama returned empty response")
        self._write_raw_log("response", text)
        return text, result, thinking_combined, "", chunk_count, total_bytes

    def _make_call_dir(self, kind: str) -> Path:
        """1回のLLM呼び出し用のディレクトリを作成して返す。

        Format: {raw_log_dir}/{phase}/{timestamp}_{pid}_{kind}/
        pidで実行単位を識別 → 中断再開でも同じPIDのログが纏まる
        """
        if not self.raw_log_dir:
            return Path("/dev/null")  # dummy
        phase = self.phase if self.phase else "unknown"
        import os as _os
        pid = _os.getpid()
        run_dir = self.raw_log_dir / phase / f"{self._run_timestamp}_{pid}_{kind}"
        run_dir.mkdir(parents=True, exist_ok=True)
        # Create details/ subdirectory for JSON.gz files
        (run_dir / "details").mkdir(exist_ok=True)
        return run_dir

    def _write_raw_log(self, file_type: str, raw_text: str) -> None:
        """1回のLLM呼び出しで2ファイルを書き出す。

        file_type: "request" または "response"
        """
        if not self.raw_log_dir or not self.raw_log_enabled:
            return
        call_dir = self._make_call_dir(self._current_kind)
        try:
            gz_path = call_dir / "details" / f"{file_type}.json.gz"
            with gzip.open(gz_path, "wb") as f:
                f.write(raw_text.encode("utf-8"))
        except Exception as e:
            self._log.debug("  [RAW LOG WRITE FAILED] %s", e)

    def _append_raw_summary(self, file_type: str, raw_text: str) -> None:
        """raw_summary.md に人が読める形式で追記する。"""
        if not self.raw_log_dir or not self.raw_log_enabled:
            return
        call_dir = self._make_call_dir(self._current_kind)
        summary_path = call_dir / "raw_summary.md"
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = self._format_for_summary(file_type, raw_text)
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(f"\n## {ts} — {file_type}\n\n{content}\n")
        except Exception as e:
            self._log.debug("  [RAW SUMMARY WRITE FAILED] %s", e)

    def _format_for_summary(self, file_type: str, raw_text: str) -> str:
        """RAWテキストを人が読める形式に整形する。"""
        if file_type.startswith("request"):
            try:
                payload = json.loads(raw_text)
                messages = payload.get("messages", [])
                parts = []
                for i, msg in enumerate(messages):
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    # Unescape
                    content = content.replace("\\n", "\n").replace('\\"', '"')
                    parts.append(f"### messages[{i}] ({role})\n\n{content}\n")
                return "\n".join(parts)
            except (json.JSONDecodeError, TypeError):
                return raw_text.replace("\\n", "\n").replace('\\"', '"')
        else:
            # response
            try:
                parsed = parse_json_response(raw_text)
                if isinstance(parsed, dict):
                    # Remove thinking (too long for summary)
                    parsed.pop("thinking", None)
                    parsed.pop("thinking_combined", None)
                    return "```json\n" + json.dumps(parsed, ensure_ascii=False, indent=2) + "\n```\n"
                return "```\n" + str(parsed) + "\n```\n"
            except Exception:
                # Raw text fallback, unescape
                text = raw_text.replace("\\n", "\n").replace('\\"', '"')
                return text
