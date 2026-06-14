#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_URL = "http://ws1.local:11434/v1/chat/completions"
MODELS_URL = "http://ws1.local:11434/v1/models"
MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
OUT_DIR = Path("docs")
RAW_DIR = Path("workspace/logs/llm/probe")


def post_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 3600) -> tuple[int | None, dict[str, Any] | str, float]:
    start = time.perf_counter()
    try:
        if payload is None:
            req = urllib.request.Request(url, method="GET")
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - start
            try:
                return resp.status, json.loads(body), elapsed
            except json.JSONDecodeError:
                return resp.status, body, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return None, {"error_type": type(exc).__name__, "error": str(exc)}, elapsed


def completion(messages: list[dict[str, str]], max_tokens: int = 512, temperature: float = 0.1, timeout: float = 3600, extra: dict[str, Any] | None = None):
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra:
        payload.update(extra)
    status, body, elapsed = post_json(API_URL, payload, timeout=timeout)
    raw = {"request": payload, "status": status, "elapsed_sec": elapsed, "body": body}
    return raw


def extract_content(raw: dict[str, Any]) -> str:
    body = raw.get("body")
    if isinstance(body, dict):
        try:
            return body["choices"][0]["message"]["content"]
        except Exception:
            return json.dumps(body, ensure_ascii=False)[:2000]
    return str(body)


def try_parse_json(text: str) -> tuple[bool, Any, str | None]:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return True, json.loads(s), None
    except json.JSONDecodeError as exc:
        return False, None, str(exc)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat(), "api_url": API_URL, "model": MODEL, "tests": {}}

    status, body, elapsed = post_json(MODELS_URL, None, timeout=30)
    results["tests"]["models_endpoint"] = {"status": status, "elapsed_sec": elapsed, "body_sample": body if isinstance(body, dict) else str(body)[:1000]}

    cases = []
    cases.append(("basic_connect_and_model_load", [
        {"role":"system","content":"あなたはJSONだけを返すアシスタントです。"},
        {"role":"user","content":"次をJSONで返してください: {\"ok\": true, \"message\": \"接続確認\"}"},
    ], 256, 0.0, 3600, None))

    for i in range(3):
        cases.append((f"json_stability_{i+1}", [
            {"role":"system","content":"必ずJSONのみを返してください。Markdownコードフェンスは禁止です。"},
            {"role":"user","content":"日本語で短い小説企画をJSONで返してください。キーは title, genre, hooks(配列3件), protagonist.name, protagonist.goal のみ。"},
        ], 512, 0.2, 3600, None))

    schema = {
        "type":"object",
        "properties":{
            "overall_status":{"type":"string","enum":["合格","要修正","再生成推奨"]},
            "issues":{"type":"array","items":{"type":"object","properties":{"severity":{"type":"string","enum":["低","中","高","致命的"]},"category":{"type":"string","enum":["設定矛盾","文章品質","その他"]},"target":{"type":"string"},"problem":{"type":"string"},"suggested_fix":{"type":"string"}},"required":["severity","category","target","problem","suggested_fix"]}}
        },
        "required":["overall_status","issues"]
    }
    cases.append(("schema_following_prompt_only", [
        {"role":"system","content":"必ずJSONのみ。次のJSON Schemaに厳密に従ってください。\n"+json.dumps(schema, ensure_ascii=False)},
        {"role":"user","content":"次の文をレビューしてください: 主人公は朝に死んだ。しかし同じ朝に何事もなく朝食を食べた。"},
    ], 768, 0.1, 3600, None))
    cases.append(("schema_following_response_format_json_object", [
        {"role":"system","content":"必ずJSONのみ。次のJSON Schemaに厳密に従ってください。\n"+json.dumps(schema, ensure_ascii=False)},
        {"role":"user","content":"次の文をレビューしてください: 主人公は朝に死んだ。しかし同じ朝に何事もなく朝食を食べた。"},
    ], 768, 0.1, 3600, {"response_format":{"type":"json_object"}}))

    long_input = "設定: " + ("主人公は港町の若い商人。交易、政略、家族、契約、禁制品、嵐、港湾ギルド。" * 400)
    cases.append(("long_input_long_output", [
        {"role":"system","content":"日本語で、JSONのみを返してください。"},
        {"role":"user","content":long_input + "\nこの設定から章立て案をJSONで返してください。chapters配列は10件、各summaryは120字程度。"},
    ], 2048, 0.2, 3600, None))

    for name, messages, max_tokens, temp, timeout, extra in cases:
        raw = completion(messages, max_tokens=max_tokens, temperature=temp, timeout=timeout, extra=extra)
        content = extract_content(raw)
        ok, parsed, parse_error = try_parse_json(content)
        raw["content_parse"] = {"json_ok": ok, "parse_error": parse_error, "parsed_sample": parsed if ok else None, "content_sample": content[:2000]}
        results["tests"][name] = raw
        (RAW_DIR / f"{name}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # timeout behavior: intentionally tiny timeout
    raw_timeout = completion([
        {"role":"system","content":"普通に回答してください。"},
        {"role":"user","content":"タイムアウトテストです。1000字程度で説明してください。"},
    ], max_tokens=512, temperature=0.2, timeout=0.001)
    results["tests"]["client_timeout_0_001_sec"] = raw_timeout

    # invalid model behavior
    invalid_payload = {"model":"definitely-not-installed-model","messages":[{"role":"user","content":"hi"}],"max_tokens":16}
    status, body, elapsed = post_json(API_URL, invalid_payload, timeout=60)
    results["tests"]["invalid_model_error"] = {"status": status, "elapsed_sec": elapsed, "body": body}

    results["finished_at"] = datetime.now(timezone.utc).isoformat()
    (RAW_DIR / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_line(name: str, data: dict[str, Any]) -> str:
        parse = data.get("content_parse", {}) if isinstance(data, dict) else {}
        status = data.get("status") if isinstance(data, dict) else None
        elapsed = data.get("elapsed_sec") if isinstance(data, dict) else None
        return f"- {name}: status={status}, elapsed={elapsed:.2f}s, json_ok={parse.get('json_ok')}" if isinstance(elapsed, float) else f"- {name}: {data}"

    lines = [
        "# LLM実動作検証レポート",
        "",
        f"- 検証日時(UTC): {results['started_at']} 〜 {results['finished_at']}",
        f"- API URL: `{API_URL}`",
        f"- モデル: `{MODEL}`",
        "- クライアントタイムアウト想定: 3600秒",
        "",
        "## 結果サマリー",
    ]
    for name, data in results["tests"].items():
        if name == "models_endpoint":
            lines.append(f"- {name}: status={data['status']}, elapsed={data['elapsed_sec']:.2f}s")
        elif isinstance(data, dict) and "elapsed_sec" in data:
            lines.append(test_line(name, data))
        else:
            lines.append(f"- {name}: {data}")
    lines += [
        "",
        "## 観測事項",
        "",
        "- 詳細RAWログは `workspace/logs/llm/probe/*.json` に保存した。",
        "- JSON安定性は `json_ok` と parse_error を基準に評価した。",
        "- `response_format={\"type\":\"json_object\"}` の効果も検証対象に含めた。",
        "- タイムアウトはクライアント側で短時間タイムアウトを発生させ、例外形状を確認した。",
        "- 不正モデル指定により、APIエラー形状を確認した。",
        "",
        "## 実装方針への反映",
        "",
        "- LLM応答は不正JSON・コードフェンス混入を前提に、抽出→JSON parse→スキーマ検証→修復リトライの順で処理する。",
        "- OpenAI互換APIの `response_format` は利用可能なら送るが、プロンプト側の明示スキーマと後段検証を必須にする。",
        "- 1時間タイムアウトを既定値にしつつ、RAWログに経過時間・例外・リトライ回数を必ず残す。",
        "- モデルロード時間が長い前提で、小さなLLM呼び出しの大量分割を避け、階層ごとにまとまった設計生成を行う。",
    ]
    (OUT_DIR / "llm_behavior_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote docs/llm_behavior_report.md and workspace/logs/llm/probe/summary.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
