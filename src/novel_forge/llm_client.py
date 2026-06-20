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
    """Replace unescaped newlines inside JSON string values with \\n.

    Ollama /api/chat sometimes returns JSON where string values contain
    literal newlines instead of \\n escapes, causing json.loads to fix.

    Uses a simple state machine to only touch content inside string
    values, avoiding structural quotes (key names, delimiters).
    """
    result = []
    i = 0
    n = len(text)
    in_string = False
    escape_next = False
    while i < n:
        ch = text[i]
        if in_string:
            if escape_next:
                # Copy escaped char as-is (\", \\, \/, \n etc.)
                result.append(ch)
                escape_next = False
            elif ch == '\\':
                result.append(ch)
                escape_next = True
            elif ch == '"':
                # End of string value
                result.append(ch)
                in_string = False
            elif ch == '\n':
                # Literal newline inside string — escape it
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


def _parse_json_response(text: str) -> Any:
    text = _extract_json_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Ollama may emit literal newlines inside string values — fix and retry
    fixed = _escape_json_string_values(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Ollama sometimes produces invalid JSON. Try increasingly aggressive fixes.
    # Fix 1: Replace 「...」-quoted values with "..."-quoted values.
    # Fix 2: Replace single-quoted values with double-quoted values.
    # Fix 3: Wrap bare unquoted string values in quotes.
    # Fix 4: Fix missing colons between key and value.

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
            # Match pattern: ': 'value'  (single-quoted value after colon-space)
            if (s[i] == "'" and i > 0 and s[i - 1] in (':', ',')):
                # Find the matching closing single quote
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
            # Look for pattern: ": value  (colon, space, then non-quote, non-brace, non-bracket)
            if (s[i] == ':' and i + 1 < n and s[i + 1] == ' '
                    and i + 2 < n
                    and s[i + 2] not in ('"', "'", '{', '[', '}', ']', 'n', 't', 'f')):
                # Check if this is inside a string value (skip if so)
                # Simple heuristic: count unescaped quotes before this position
                quote_count = 0
                for k in range(i):
                    if s[k] == '"' and (k == 0 or s[k - 1] != '\\'):
                        quote_count += 1
                if quote_count % 2 == 1:
                    # Inside a string, skip
                    result.append(s[i])
                    i += 1
                    continue
                result.append(': "')
                i += 2  # skip ': '
                start = i
                # Find end of value: ,\n or \n at depth 0
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
                # Skip a misplaced " after the value (LLM sometimes produces
                # value" instead of value, where " is the next key's opening quote)
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

    # Apply fixes in sequence
    patched = _fix_bracket_quoted_values(fixed)
    try:
        return json.loads(patched)
    except json.JSONDecodeError:
        pass
    patched = _fix_single_quoted_values(patched)
    try:
        return json.loads(patched)
    except json.JSONDecodeError:
        pass
    patched = _fix_unquoted_values(patched)
    try:
        return json.loads(patched)
    except json.JSONDecodeError:
        pass
    patched = _fix_missing_colons(patched)
    try:
        return json.loads(patched)
    except json.JSONDecodeError:
        pass
    # Last resort: try to extract JSON object from the text
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
    """config.yaml を読み込んで設定 dict を返す。
    config_path が None の場合は親ディレクトリから探す。
    見つからない場合は空 dict。
    """
    import os
    yaml = _try_import_yaml()
    if yaml is None:
        return {}

    paths_to_try = []
    if config_path:
        paths_to_try.append(config_path)
    else:
        # カレントディレクトリから親へ辿って config.yaml を探す
        cwd = Path.cwd()
        for p in [cwd, *cwd.parents]:
            candidate = p / "config.yaml"
            if candidate.exists():
                paths_to_try.append(candidate)
                break
        # 環境変数で指定されたパス
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
        num_predict: int = 32768,
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
        self.num_predict = num_predict
        self.num_ctx = num_ctx or self._detect_max_ctx()
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
            # モデル固有の context_length キーを探す (例: qwen35moe.context_length)
            for key, val in model_info.items():
                if key.endswith(".context_length") and isinstance(val, (int, float)):
                    return int(val)
        except Exception as e:
            import sys
            print(f"[LLMClient] Warning: could not detect max context length: {e}", file=sys.stderr)
        return 32768  # フォールバック（qwen3.6:35b の安定動作値）

    def complete_json(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
                **self._ollama_options,
            },
        }
        # format=schema は Ollama 0.30.10 でネストされたオブジェクト構造を
        # 正しく適用できないため、format=json を使用し
        # スキーマバリデーションは Python 側で行う
        # think: true は LLM がスキーマをより正確に遵守できるようにする
        payload["format"] = "json"
        payload["think"] = True

        # Unified retry loop: JSON parse + schema validation errors share the
        # same budget of max_retries attempts.  On JsonParseError we feed
        # the bad response back so the model can correct itself.
        last_error: Exception | None = None
        current_prompt = user_prompt
        raw = ""
        for attempt in range(self.max_retries):
            try:
                payload["messages"][1]["content"] = current_prompt
                raw = self._call_api(payload)
                parsed = _parse_json_response(raw)
                if schema:
                    from novel_forge.schemas import validate_or_raise
                    validate_or_raise(kind, parsed)
                self._write_log(kind, payload, raw, parsed)
                return parsed
            except JsonParseError as e:
                last_error = e
                self._write_log(kind + "_json_error", payload, raw, {"error": str(e), "raw_preview": raw[:500]})
                # 失敗内容は要約してフィードバック（プロンプト肥大化防止）
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
                self._write_log(kind + "_schema_error", payload, raw, {"error": str(e), "raw_preview": raw[:500]})
                # エラーメッセージは短縮してフィードバック（プロンプト肥大化防止）
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
                self._write_log(kind + "_llm_error", payload, raw, {"error": str(e)})
                continue
        # All retries exhausted — save final failure log
        self._write_log(kind + "_FAILED", payload, raw, {"error": str(last_error), "raw_preview": raw[:500]})
        raise last_error or LLMError("LLM request failed")

    def _call_api(self, payload: dict[str, Any]) -> str:
        try:
            # stream: false を指定して一括取得
            # think は complete_json で設定される（デフォルト: true）
            payload = {**payload, "stream": False}
            resp = httpx.post(
                self.api_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            # Ollama /api/chat may return NDJSON (streaming) or single JSON.
            text = resp.text.strip()
            if "\n" in text:
                # NDJSON: each line is a JSON object
                # For chat API, content is in message.content (may also be in message.thinking for thinking models)
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
                # If content is empty but thinking has output, use thinking (qwen3.6 behavior)
                if not result.strip() and thinking_parts:
                    result = "".join(thinking_parts)
            else:
                data = json.loads(text)
                if "error" in data:
                    raise LLMError(f"Ollama error: {data['error']}")
                result = data.get("message", {}).get("content", "")
            if not result or not result.strip():
                raise LLMError("Ollama returned empty response")
            return result
        except httpx.HTTPError as e:
            raise LLMError(f"HTTP error: {e}") from e

    def _write_log(
        self,
        kind: str,
        payload: dict[str, Any],
        raw: str,
        parsed: Any,
    ) -> None:
        if not self.raw_log_dir:
            return
        self.raw_log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # Find unique filename with index
        idx = 0
        while True:
            suffix = f"_{idx:03d}" if idx > 0 else ""
            log_path = self.raw_log_dir / f"{timestamp}_{kind}{suffix}.json"
            if not log_path.exists():
                break
            idx += 1
        log_data = {
            "kind": kind,
            "timestamp": timestamp,
            "request": {k: v for k, v in payload.items() if k != "api_key"},
            "response_raw": raw,
            "response_parsed": parsed,
        }
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
