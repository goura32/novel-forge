from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from novel_forge.json_parser import JsonParseError, coerce_types, parse_json_response
from novel_forge.logging_config import get_logger


class LLMError(Exception):
    pass


class SchemaValidationError(LLMError):
    pass


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """config.yaml を読み込んで設定 dict を返す。"""
    yaml = _try_import_yaml()
    if yaml is None:
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
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _try_import_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        return None


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
    ):
        if api_url is None:
            host = os.environ.get("OLLAMA_HOST", "ws1.local:11434")
            api_url = f"http://{host}/api/chat"
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.raw_log_dir = raw_log_dir
        self.raw_log_enabled = raw_log_enabled
        self.phase = phase
        self.num_ctx = num_ctx if num_ctx else 262144
        self.num_predict = num_predict
        self._ollama_options = ollama_options or {}
        self._log = get_logger("novel_forge.llm")
        self._last_progress_log: float = 0.0
        self._current_kind: str = ""
        if self._ollama_options.get("think", False):
            print(
                "⚠ think=True is enabled — qwen3.6 thinking models may return empty "
                "content with format='json'. Consider think=False for production use."
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
        api_options = {k: v for k, v in self._ollama_options.items() if k != "think"}
        think_value = self._ollama_options.get("think", True)

        payload: dict[str, Any] = {
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
        }
        payload["format"] = "json"
        payload["think"] = think_value
        last_error: Exception | None = None
        current_prompt = user_prompt
        self._current_kind = kind
        raw_text, thinking = "", ""
        for attempt in range(max(self.max_retries, 1)):
            raw_text, thinking = "", ""
            try:
                payload["messages"][1]["content"] = current_prompt
                payload["options"]["seed"] = 42 + attempt + seed_offset
                self._write_raw_log(f"request_{attempt}", json.dumps(payload, ensure_ascii=False))
                self._log.debug(
                    "  [LLM CALL] kind=%s attempt=%d/%d model=%s seed=%d",
                    kind, attempt + 1, self.max_retries, self.model, 42 + attempt + seed_offset,
                )
                _call_start = time.time()
                raw_text, raw, thinking, done_reason = self._call_api(payload)
                _call_elapsed = time.time() - _call_start
                self._log.debug(
                    "  [LLM DONE] kind=%s elapsed=%.1fs",
                    kind, _call_elapsed,
                )
                self._write_raw_log(f"response_{attempt}", raw_text)
                parsed = parse_json_response(raw)
                if schema:
                    parsed = coerce_types(parsed, schema)
                    from novel_forge.schemas import validate_or_raise
                    validate_or_raise(kind, parsed)
                return parsed
            except JsonParseError as e:
                last_error = e
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:100],
                )
                error_hint = str(e)[:100]
                current_prompt = (
                    f"前回の出力はJSONとして解析できませんでした。\n"
                    f"エラー: {error_hint}\n"
                    f"必ず有効なJSONのみを出力してください。\n"
                    f"JSON以外のテキストは一切含めないでください。\n\n"
                    f"元の指示:\n{user_prompt}"
                )
                continue
            except SchemaValidationError as e:
                last_error = e
                self._write_raw_log(f"_schema_err_{attempt}", raw_text)
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:100],
                )
                error_hint = str(e)[:200]
                current_prompt = (
                    f"前回の出力はスキーマ検証に失敗しました。\n"
                    f"エラー: {error_hint}\n"
                    f"不足・不正なフィールドを修正し、必ず有効なJSONのみを出力してください。\n\n"
                    f"元の指示:\n{user_prompt}"
                )
                continue
            except LLMError as e:
                last_error = e
                self._write_raw_log(f"_llm_err_{attempt}", raw_text)
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:100],
                )
                continue
            except Exception as e:
                last_error = e
                self._write_raw_log(f"_err_{attempt}", raw_text)
                self._log.warning(
                    "  [LLM ERROR] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:200],
                )
                raise
        self._write_raw_log("_failed", raw_text)
        self._log.error(
            "  [LLM FAILED] kind=%s attempts=%d error=%s",
            kind, self.max_retries, str(last_error)[:100],
        )
        raise last_error or LLMError("LLM request failed")

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

    def _call_api(self, payload: dict[str, Any]) -> tuple[str, str, str, str]:
        """Call Ollama API with stream=True and return (raw_text, content, thinking, done_reason)."""
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
                            elapsed_h = int(elapsed_total // 3600)
                            elapsed_m = int((elapsed_total % 3600) // 60)
                            elapsed_s = int(elapsed_total % 60)
                            self._log.info(
                                "  [LLM PROGRESS] chunks=%d bytes=%d elapsed=%02d:%02d:%02d",
                                chunk_count, total_bytes, elapsed_h, elapsed_m, elapsed_s,
                            )
                            self._last_progress_log = now
        except httpx.TimeoutException:
            text = "\n".join(lines)
            self._write_raw_log("_timeout", text)
            raise LLMError("Ollama request timed out")
        except httpx.HTTPStatusError as e:
            self._write_raw_log("_http_err", str(e))
            raise LLMError(f"Ollama HTTP error: {e}")
        text = "\n".join(lines)
        result, thinking_combined = self._parse_ndjson(text)
        if not result or not result.strip():
            self._write_raw_log("_empty", text)
            raise LLMError("Ollama returned empty response")
        self._write_raw_log("_resp", text)
        return text, result, thinking_combined, ""

    def _make_call_dir(self, kind: str) -> Path:
        """1回のLLM呼び出し用のディレクトリを作成して返す。"""
        if not self.raw_log_dir:
            return Path("/dev/null")  # dummy
        phase = self.phase if self.phase else "unknown"
        pid = os.getpid()
        run_dir = self.raw_log_dir / phase / f"{pid}_{kind}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_raw_log(self, file_type: str, raw_text: str, payload: dict | None = None) -> None:
        """1回のLLM呼び出しで2ファイルを書き出す。

        file_type: "request" または "response"
        """
        if not self.raw_log_dir or not self.raw_log_enabled:
            return
        # kind は呼び出し元で設定する（_call_api の前で _kind をセット）
        call_dir = self._make_call_dir(self._current_kind)
        try:
            call_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        try:
            gz_path = call_dir / f"{file_type}.json.gz"
            with gzip.open(gz_path, "wb") as f:
                f.write(raw_text.encode("utf-8"))
        except Exception as e:
            self._log.debug("  [RAW LOG WRITE FAILED] %s", e)
