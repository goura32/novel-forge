# RAWログフォーマット

## 概要

`llm_client.py` の `_write_raw_log` は、Ollama APIとの通信内容を gzip 圧縮で保存する。
`--raw-log` オプション時に有効化され、デフォルトでは無効。

## ファイル命名規則

```
{timestamp}_pid{pid}_{kind}{suffix}.json.gz
```

| 要素 | 形式 | 説明 |
|---|---|---|
| timestamp | `YYYYMMDD_HHMMSS` | ログ作成時刻 |
| pid | 数字 | プロセスID |
| kind | 文字列 | ログの種類（後述） |
| suffix | `_000`, `_001`, ... | 同一タイムスタンプの重複回避用（0の場合は省略） |

### kind 一覧

| kind | 意味 |
|---|---|
| `_resp` | 正常レスポンス（Ollama の生NDJSON） |
| `_req` | リクエストペイロード |
| `_json_err` | JSONパースエラー |
| `_schema_err` | スキーマ検証エラー |
| `_llm_err` | LLM API エラー（タイムアウト等） |
| `_err` | 予期しないエラー（catch-all） |
| `_failed` | 全リトライ失敗 |
| `_timeout` | タイムアウト |
| `_http_err` | HTTPステータスエラー |
| `_empty` | 空レスポンス |

`kind` は `_call_api` の内部ログ（`_resp`, `_req`, `_timeout`, `_http_err`, `_empty`）と、`complete_json` のエラーパス（`_json_err`, `_schema_err`, `_llm_err`, `_err`, `_failed`）に分かれる。

`complete_json` のエラーパスでは、`kind` は呼び出し元の識別子にサフィックスを付加した形式になる。例：
- `series_plan_characters_json_err` — キャラクター生成のJSONパースエラー
- `plan_chars_err` — キャラクター生成の予期しないエラー

## ファイル構造（JSON）

```json
{
  "kind": "plan_chars_err",
  "timestamp": "20260622_084506",
  "pid": 383609,
  "model": "qwen3.6:35b-a3b-mtp-q4_K_M",
  "request": {
    "system": "...(システムプロンプト)...",
    "user": "...(ユーザープロンプト)...",
    "options": { "num_ctx": 262144, "num_predict": -1, "seed": 42 },
    "format": "json",
    "think": false
  },
  "raw_response": "...(Ollamaの生NDJSON)...",
  "thinking": "...(thinkingトークン、省略時は未設定)...",
  "response": {
    "error": "Illegal trailing comma...",
    "error_type": "JsonParseError"
  }
}
```

### フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| kind | string | ログの種類 |
| timestamp | string | 作成時刻 `YYYYMMDD_HHMMSS` |
| pid | number | プロセスID |
| model | string | モデル名 |
| request | object \| 未設定 | リクエストペイロード（`_req` のみ） |
| raw_response | string | Ollama の生NDJSONレスポンス |
| thinking | string \| 未設定 | thinkingトークン（10MB超は切り捨て） |
| response | object \| 未設定 | パース済みレスポンスまたはエラー情報 |

## 保存先

```
{workdir}/_raw_logs/
```

`plan` コマンド: `{workdir}/_raw_logs/`（workdir = `/mnt/hdd/novel/`）
`complete` コマンド: `{series_dir}/_raw_logs/`（series_dir = `{workdir}/series_{hash}/`）

## 圧縮

全ファイル gzip 圧縮（`.json.gz`）。

## 設計方針

- リクエストとレスポンスの両方を保存し、再現性を確保
- thinking トークンも保存し、モデルの推論過程を調査可能に
- エラー時はエラーメッセージとエラータイプを `response` に記録
- 10MB 超の thinking は先頭5MB に切り捨て（ディスク節約）
