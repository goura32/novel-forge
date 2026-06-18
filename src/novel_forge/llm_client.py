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


def _parse_json_response(text: str) -> Any:
    text = _extract_json_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise JsonParseError(f"Failed to parse JSON from response: {text[:200]}...")


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
        timeout_seconds: int = 600,
        max_retries: int = 2,
        raw_log_dir: Path | None = None,
        num_ctx: int | None = None,
        num_predict: int = 65536,
        ollama_options: dict[str, Any] | None = None,
    ):
        if api_url is None:
            import os
            host = os.environ.get("OLLAMA_HOST", "ws1.local:11434")
            api_url = f"http://{host}/api/generate"
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
        return 262144  # フォールバック（qwen3.6:35b ネイティブコンテキスト長）

    def complete_json(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "think": False,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                **self._ollama_options,
            },
        }
        # format=schema hangs/times out on Ollama 0.30.8 with qwen3.6:35b.
        # format="json" works correctly and enforces JSON-only output.
        payload["format"] = "json"

        # Unified retry loop: JSON parse + schema validation errors share the
        # same budget of MAX_RETRIES attempts.  On JsonParseError we feed
        # the bad response back so the model can correct itself.
        last_error: Exception | None = None
        MAX_RETRIES = 10
        current_prompt = user_prompt
        raw = ""
        for attempt in range(MAX_RETRIES):
            try:
                payload["prompt"] = current_prompt
                raw = self._call_api(payload)
                parsed = _parse_json_response(raw)
                if schema:
                    from novel_forge.schemas import validate_or_raise
                    validate_or_raise(kind, parsed)
                self._write_log(kind, payload, raw, parsed)
                return parsed
            except JsonParseError as e:
                last_error = e
                # Feed the bad response back and ask for JSON correction
                current_prompt = (
                    f"前回の出力はJSONではありませんでした。\n\n"
                    f"前回の出力:\n{raw[:500]}\n\n"
                    f"以下のスキーマに従い、必ず有効なJSONのみを出力してください。\n"
                    f"JSON以外のテキスト（説明、注釈、マークダウン等）は一切含めないでください。\n\n"
                    f"スキーマ: {json.dumps(schema, ensure_ascii=False)}\n\n"
                    f"元の指示:\n{user_prompt}"
                )
                continue
            except SchemaValidationError as e:
                last_error = e
                # Feed schema validation error back so model can fix missing/incorrect fields
                current_prompt = (
                    f"前回の出力はスキーマ検証に失敗しました。\n\n"
                    f"検証エラー:\n{e}\n\n"
                    f"前回の出力:\n{raw[:500]}\n\n"
                    f"以下のスキーマに従い、必須フィールドを含めて修正してください。\n"
                    f"JSON以外のテキスト（説明、注釈、マークダウン等）は一切含めないでください。\n\n"
                    f"スキーマ: {json.dumps(schema, ensure_ascii=False)}\n\n"
                    f"元の指示:\n{user_prompt}"
                )
                continue
            except LLMError as e:
                last_error = e
                continue
        raise last_error or LLMError("LLM request failed")

    def _call_api(self, payload: dict[str, Any]) -> str:
        try:
            resp = httpx.post(
                self.api_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            # Check for Ollama error responses (e.g. CUDA out of memory)
            if "error" in data:
                raise LLMError(f"Ollama error: {data['error']}")
            result = data.get("response", "") or data.get("message", {}).get("content", "")
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
