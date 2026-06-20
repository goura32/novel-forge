from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx


class LLMError(Exception):
    pass


class JsonParseError(LLMError):
    pass


class SchemaValidationError(LLMError):
    pass


def _extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _escape_json_string_values(text: str) -> str:
    """Replace unescaped newlines inside JSON string values with \\n."""
    result = []
    i = 0
    n = len(text)
    in_string = False
    escape_next = False
    while i < n:
        ch = text[i]
        if in_string:
            if escape_next:
                result.append(ch)
                escape_next = False
            elif ch == '\\':
                result.append(ch)
                escape_next = True
            elif ch == '"':
                result.append(ch)
                in_string = False
            elif ch == '\n':
                result.append('\\')
                result.append('n')
            else:
                result.append(ch)
        else:
            if ch == '"':
                in_string = True
            result.append(ch)
        i += 1
    return ''.join(result)


def _fix_bracket_quoted_values(s: str) -> str:
    """Replace 「...」-quoted values (after ': ') with "..."-quoted values."""
    result = []
    i = 0
    n = len(s)
    while i < n:
        if (i + 2 < n and s[i] == ':' and s[i + 1] == ' '
                and s[i + 2] == '\u300c'):
            result.append(': ')
            i += 2
            start = i
            j = i
            last_period = -1
            depth = 0
            while j < n:
                if s[j] == '\u300c':
                    depth += 1
                elif s[j] == '\u300d':
                    depth -= 1
                elif s[j] == '。' and depth == 0:
                    last_period = j
                elif s[j] == ',' and depth == 0:
                    break
                elif s[j] == '\n' and depth == 0:
                    break
                j += 1
            end = last_period + 1 if last_period >= 0 else j
            value = s[start:end]
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            result.append('"')
            result.append(escaped)
            result.append('"')
            i = end
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _fix_single_quoted_values(s: str) -> str:
    """Replace single-quoted string values with double-quoted values."""
    result = []
    i = 0
    n = len(s)
    while i < n:
        if (s[i] == "'" and i > 0 and s[i - 1] in (':', ',')):
            j = i + 1
            while j < n:
                if s[j] == "'" and s[j - 1] != '\\':
                    break
                j += 1
            if j < n:
                value = s[i + 1:j]
                escaped = value.replace('\\', '\\\\').replace('"', '\\"')
                result.append('"')
                result.append(escaped)
                result.append('"')
                i = j + 1
                continue
        result.append(s[i])
        i += 1
    return ''.join(result)


def _fix_unquoted_values(s: str) -> str:
    """Wrap bare unquoted string values in double quotes.

    Handles patterns like: "key": value (where value is not quoted)
    The value ends at ,\n or \n at the same nesting level.
    """
    result = []
    i = 0
    n = len(s)
    while i < n:
        if (s[i] == ':' and i + 1 < n and s[i + 1] == ' '
                and i + 2 < n
                and s[i + 2] not in ('"', "'", '{', '[', '}', ']', 'n', 't', 'f')):
            # Check if this is inside a string value (skip if so)
            quote_count = 0
            for k in range(i):
                if s[k] == '"' and (k == 0 or s[k - 1] != '\\'):
                    quote_count += 1
            if quote_count % 2 == 1:
                result.append(s[i])
                i += 1
                continue
            result.append('": "')
            i += 2  # skip ': '
            start = i
            j = i
            depth_brace = 0
            depth_bracket = 0
            last_period = -1
            while j < n:
                if s[j] == '{':
                    depth_brace += 1
                elif s[j] == '}':
                    depth_brace -= 1
                elif s[j] == '[':
                    depth_bracket += 1
                elif s[j] == ']':
                    depth_bracket -= 1
                elif depth_brace == 0 and depth_bracket == 0:
                    if s[j] == '。':
                        last_period = j
                    elif s[j] == ',':
                        break
                    elif s[j] == '\n':
                        break
                j += 1
            end = last_period + 1 if last_period >= 0 else j
            if end < n and s[end] == '"':
                end += 1
            value = s[start:end].rstrip()
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            result.append(escaped)
            result.append('"')
            i = end
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _fix_missing_colons(s: str) -> str:
    """Fix missing colons: "key", "value" -> "key": "value"."""
    import re
    return re.sub(r'"\s*,\s*"([^"]*)"', r'": "\1"', s)


def _parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response with progressive fallback fixes."""
    text = _extract_json_text(text)

    # Attempt 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Fix literal newlines in string values
    fixed = _escape_json_string_values(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 3-6: Progressive structural fixes
    fix_chain = [
        _fix_bracket_quoted_values,
        _fix_single_quoted_values,
        _fix_unquoted_values,
        _fix_missing_colons,
    ]
    patched = fixed
    for fix_fn in fix_chain:
        patched = fix_fn(patched)
        try:
            return json.loads(patched)
        except json.JSONDecodeError:
            continue

    # Last resort: extract JSON object boundaries
    start = patched.find("{")
    end = patched.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(patched[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise JsonParseError(f"Failed to parse JSON from response: {text[:200]}...")


def _coerce_types(data: dict, schema: dict) -> dict:
    """Coerce LLM output types to match schema expectations.

    Handles common LLM mistakes:
    - dict/object → string (e.g. target_audience: {age: "..."} → "...")
    - string → array (when schema expects array but LLM returns comma-separated string)
    - array → string (when schema expects string but LLM returns array)
    """
    if not isinstance(data, dict) or not isinstance(schema, dict):
        return data

    props = schema.get("properties", {})
    required = schema.get("required", [])

    # Add missing required fields with empty defaults
    for field in required:
        if field not in data:
            field_schema = props.get(field, {})
            ftype = field_schema.get("type", "")
            if ftype == "array":
                data[field] = []
            elif ftype == "object":
                data[field] = {}
            elif ftype == "string":
                data[field] = ""
            elif ftype == "integer":
                data[field] = 0

    for field, value in list(data.items()):
        if field not in props:
            continue
        field_schema = props.get(field, {})
        expected_type = field_schema.get("type", "")

        if expected_type == "string" and isinstance(value, dict):
            # Convert dict to concatenated string
            parts = []
            for k, v in value.items():
                if isinstance(v, list):
                    v = "、".join(str(x) for x in v)
                parts.append(f"{k}: {v}")
            data[field] = "、".join(parts)

        elif expected_type == "string" and isinstance(value, list):
            # Convert list to comma-separated string
            data[field] = "、".join(str(x) for x in value)

        elif expected_type == "array" and isinstance(value, str):
            # Convert comma/newline separated string to array
            import re
            items = [x.strip() for x in re.split(r"[,\n。]", value) if x.strip()]
            data[field] = items

        elif expected_type == "object" and isinstance(value, dict):
            # Recurse into nested objects
            nested_required = field_schema.get("required", [])
            for nr in nested_required:
                if nr not in value:
                    value[nr] = "" if field_schema.get("properties", {}).get(nr, {}).get("type") == "string" else []
            data[field] = _coerce_types(value, field_schema)

    return data


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
    def __init__(
        self,
        api_url: str | None = None,
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        timeout_seconds: int = 3600,
        max_retries: int = 2,
        raw_log_dir: Path | None = None,
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
        self.num_ctx = num_ctx if num_ctx else 262144
        self.num_predict = num_predict
        self._ollama_options = ollama_options or {}

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
            import sys
            print(f"[LLMClient] Warning: could not detect max context length: {e}", file=sys.stderr)
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
                import sys as _sys
                _sys.stderr.write(f"  [LLM CALL] kind={kind} attempt={attempt+1}/{self.max_retries} model={self.model} seed={42+attempt}\n")
                _call_start = time.time()
                raw_text, raw, thinking = self._call_api(payload)
                _call_elapsed = time.time() - _call_start
                _sys.stderr.write(f"  [LLM DONE] kind={kind} attempt={attempt+1} elapsed={_call_elapsed:.1f}s raw_len={len(raw)}\n")
                parsed = _parse_json_response(raw)
                if schema:
                    # Coerce types and fill missing required fields before validation
                    parsed = _coerce_types(parsed, schema)
                    from novel_forge.schemas import validate_or_raise
                    validate_or_raise(kind, parsed)
                self._write_log(kind, payload, raw, parsed, thinking=thinking, raw_text=raw_text)
                return parsed
            except JsonParseError as e:
                last_error = e
                self._write_log(kind + "_json_error", payload, raw, {"error": str(e), "raw_preview": raw[:500]}, thinking=thinking)
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
                self._write_log(kind + "_schema_error", payload, raw, {"error": str(e), "raw_preview": raw[:500]}, thinking=thinking)
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
                self._write_log(kind + "_llm_error", payload, raw, {"error": str(e)}, thinking=thinking)
                continue
        self._write_log(kind + "_FAILED", payload, raw, {"error": str(last_error), "raw_preview": raw[:500]}, thinking=thinking)
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
    ) -> None:
        if not self.raw_log_dir:
            return
        self.raw_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # Organize logs by phase: plan/outline/write/error
        PHASE_MAP = {
            "series": "plan",
            "chapter": "outline",
            "scene": "write",
            "volume": "outline",
        }
        kind_prefix = kind.split("_")[0]
        phase = PHASE_MAP.get(kind_prefix, "other")
        sub_dir = self.raw_log_dir / phase
        sub_dir.mkdir(exist_ok=True)
        idx = 0
        while True:
            suffix = f"_{idx:03d}" if idx > 0 else ""
            log_path = sub_dir / f"{timestamp}_{kind}{suffix}.json"
            if not log_path.exists():
                break
            idx += 1
        # Truncate thinking for readability (keep first/last 500 chars)
        thinking_saved = thinking
        if len(thinking) > 2000:
            thinking_saved = thinking[:500] + f"\n... [truncated {len(thinking) - 1000} chars] ...\n" + thinking[-500:]
        # Build compact request log: omit system_prompt (same for all calls),
        # keep only user_prompt and non-prompt fields
        req_log = {k: v for k, v in payload.items() if k not in ("api_key", "messages")}
        if "messages" in payload:
            user_msgs = [m for m in payload["messages"] if m.get("role") == "user"]
            if user_msgs:
                req_log["user_prompt"] = user_msgs[-1]["content"]
        # Strip thinking from raw_text to avoid duplication with response_thinking
        raw_for_log = raw_text if raw_text else raw
        if raw_for_log and thinking_saved:
            try:
                # Try to parse and remove thinking from raw JSON
                raw_data = json.loads(raw_for_log)
                if isinstance(raw_data, dict) and "message" in raw_data:
                    raw_data["message"].pop("thinking", None)
                    raw_for_log = json.dumps(raw_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass  # Keep raw_for_log as-is if parsing fails
        log_data = {
            "kind": kind,
            "timestamp": timestamp,
            "request": req_log,
            "response_raw": raw_for_log,
            "response_parsed": parsed,
        }
        if thinking_saved:
            log_data["response_thinking"] = thinking_saved
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
