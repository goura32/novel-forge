from __future__ import annotations

import json
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
    import os
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

    # Map kind prefix to log subdirectory
    PHASE_MAP: dict[str, str] = {
        "series": "plan",
        "chapter": "design",
        "scene": "write",
        "volume": "design",
    }
    def __init__(
        self,
        api_url: str | None = None,
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        timeout_seconds: int = 3600,
        max_retries: int = 2,
        raw_log_dir: Path | None = None,
        raw_log_enabled: bool = False,
        num_ctx: int | None = None,
        num_predict: int = -1,
        ollama_options: dict[str, Any] | None = None,
    ):
        if api_url is None:
            import os
            host = os.environ.get("OLLAMA_HOST", "ws1.local:11434")
            api_url = f"http://{host}/api/chat"
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.raw_log_dir = raw_log_dir
        self.raw_log_enabled = raw_log_enabled
        self.num_ctx = num_ctx if num_ctx else 262144
        self.num_predict = num_predict
        self._ollama_options = ollama_options or {}
        self._log = get_logger("novel_forge.llm")

    def _detect_max_ctx(self) -> int:
        """Ollama /api/show からモデルの context_length を取得する。"""
        import os
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
    ) -> dict[str, Any]:
        # Separate ollama_options into API-level and options-level
        # "think" is an API-level parameter, not part of options
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
        payload["format"] = schema if schema else "json"
        payload["think"] = think_value

        last_error: Exception | None = None
        current_prompt = user_prompt
        raw = ""
        thinking = ""
        for attempt in range(self.max_retries):
            try:
                payload["messages"][1]["content"] = current_prompt
                # Increment seed on each retry to get different output
                payload["options"]["seed"] = 42 + attempt
                self._log.debug(
                    "  [LLM CALL] kind=%s attempt=%d/%d model=%s seed=%d",
                    kind, attempt + 1, self.max_retries, self.model, 42 + attempt,
                )
                _call_start = time.time()
                raw_text, raw, thinking = self._call_api(payload)
                _call_elapsed = time.time() - _call_start
                self._log.debug(
                    "  [LLM DONE] kind=%s attempt=%d elapsed=%.1fs raw_len=%d",
                    kind, attempt + 1, _call_elapsed, len(raw),
                )
                parsed = parse_json_response(raw)
                if schema:
                    # Coerce types and fill missing required fields before validation
                    parsed = coerce_types(parsed, schema)
                    from novel_forge.schemas import validate_or_raise
                    validate_or_raise(kind, parsed)
                self._write_log(kind, payload, raw, parsed, thinking=thinking, raw_text=raw_text, elapsed=_call_elapsed, attempt=attempt)
                return parsed
            except JsonParseError as e:
                last_error = e
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:100],
                )
                self._write_log(kind + "_json_error", payload, raw, {"error": str(e), "raw_preview": raw[:500]}, thinking=thinking, elapsed=0.0, attempt=attempt)
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
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:100],
                )
                self._write_log(kind + "_schema_error", payload, raw, {"error": str(e), "raw_preview": raw[:500]}, thinking=thinking, elapsed=0.0, attempt=attempt)
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
                self._log.warning(
                    "  [LLM RETRY] kind=%s attempt=%d/%d error=%s",
                    kind, attempt + 1, self.max_retries, str(e)[:100],
                )
                self._write_log(kind + "_llm_error", payload, raw, {"error": str(e)}, thinking=thinking, elapsed=0.0, attempt=attempt)
                continue
        self._log.error(
            "  [LLM FAILED] kind=%s attempts=%d error=%s",
            kind, self.max_retries, str(last_error)[:100],
        )
        self._write_log(kind + "_FAILED", payload, raw, {"error": str(last_error), "raw_preview": raw[:500]}, thinking=thinking, elapsed=0.0, attempt=self.max_retries)
        raise last_error or LLMError("LLM request failed")

    def _call_api(self, payload: dict[str, Any]) -> tuple[str, str, str]:
        """Call Ollama API and return (raw_text, content, thinking).

        raw_text: raw Ollama response text (NDJSON or single JSON)
        content: extracted content (may be empty for thinking-only responses)
        thinking: extracted thinking (may be empty if model doesn't use CoT)
        """
        try:
            payload = {**payload, "stream": False}
            resp = httpx.post(
                self.api_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            text = resp.text.strip()
            thinking_combined = ""
            if "\n" in text:
                # NDJSON: each line is a JSON object
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
                result = "".join(parts)
                thinking_combined = "".join(thinking_parts)
                # Do NOT fall back to thinking content — it's English chain-of-thought
                # that would contaminate Japanese output. Empty content = error.
            else:
                data = json.loads(text)
                if "error" in data:
                    raise LLMError(f"Ollama error: {data['error']}")
                result = data.get("message", {}).get("content", "")
                thinking_combined = data.get("message", {}).get("thinking", "")
            if not result or not result.strip():
                raise LLMError("Ollama returned empty response")
            return text, result, thinking_combined
        except httpx.HTTPError as e:
            raise LLMError(f"HTTP error: {e}") from e

    def _write_log(
        self,
        kind: str,
        payload: dict[str, Any],
        raw: str,
        parsed: Any,
        thinking: str = "",
        raw_text: str = "",
        elapsed: float = 0.0,
        attempt: int = 0,
    ) -> None:
        if not self.raw_log_dir or not self.raw_log_enabled:
            return
        self.raw_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # Organize logs by phase: plan/design/write/error
        kind_prefix = kind.split("_")[0]
        phase = LLMClient.PHASE_MAP.get(kind_prefix, "other")
        sub_dir = self.raw_log_dir / phase
        sub_dir.mkdir(exist_ok=True)
        idx = 0
        while True:
            suffix = f"_{idx:03d}" if idx > 0 else ""
            log_path = sub_dir / f"{timestamp}_a{attempt}_{kind}{suffix}.json"
            if not log_path.exists():
                break
            idx += 1
        # Truncate thinking: keep first/last 200 chars
        thinking_saved = thinking
        if len(thinking) > 500:
            thinking_saved = (
                thinking[:200]
                + f"\n... [中略 {len(thinking) - 400} chars] ...\n"
                + thinking[-200:]
            )
        # Build compact request log: omit system_prompt (same for all calls),
        # keep only user_prompt and non-prompt fields
        req_log = {k: v for k, v in payload.items() if k not in ("api_key", "messages")}
        if "messages" in payload:
            user_msgs = [m for m in payload["messages"] if m.get("role") == "user"]
            if user_msgs:
                req_log["user_prompt"] = user_msgs[-1]["content"]
        # Strip thinking from raw_text to avoid duplication
        raw_for_log = raw_text if raw_text else raw
        if raw_for_log and thinking_saved:
            try:
                raw_data = json.loads(raw_for_log)
                if isinstance(raw_data, dict) and "message" in raw_data:
                    raw_data["message"].pop("thinking", None)
                    raw_for_log = json.dumps(raw_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass
        log_data = {
            "kind": kind,
            "timestamp": timestamp,
            "elapsed_seconds": round(elapsed, 1),
            "model": self.model,
            "attempt": attempt,
            "request": req_log,
            "response_raw": raw_for_log,
            "response_parsed": parsed,
        }
        if thinking_saved:
            log_data["response_thinking"] = thinking_saved
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
