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


class LLMClient:
    def __init__(
        self,
        api_url: str = "http://localhost:11434/api/generate",
        model: str = "qwen3.6:35b-a3b-mtp-q4_K_M",
        timeout_seconds: int = 600,
        max_retries: int = 2,
        raw_log_dir: Path | None = None,
    ):
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.raw_log_dir = raw_log_dir

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
        }
        if schema:
            payload["format"] = schema

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self._call_api(payload)
                parsed = _parse_json_response(raw)
                if schema:
                    from novel_forge.schemas import validate_or_raise

                    validate_or_raise(kind, parsed)
                self._write_log(kind, payload, raw, parsed)
                return parsed
            except (JsonParseError, SchemaValidationError, LLMError) as e:
                last_error = e
                if attempt < self.max_retries:
                    continue
        raise last_error or LLMError("LLM request failed")

    def complete_text(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "think": False,
        }
        raw = self._call_api(payload)
        self._write_log(kind, payload, raw, {"text": raw[:200]})
        return raw

    def _call_api(self, payload: dict[str, Any]) -> str:
        try:
            resp = httpx.post(
                self.api_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "") or data.get("message", {}).get("content", "")
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
        log_path = self.raw_log_dir / f"{timestamp}_{kind}.json"
        log_data = {
            "kind": kind,
            "timestamp": timestamp,
            "request": {k: v for k, v in payload.items() if k != "api_key"},
            "response_raw": raw,
            "response_parsed": parsed,
        }
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
