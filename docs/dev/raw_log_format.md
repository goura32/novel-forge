# RAWログフォーマット

## 概要

`llm_client.py` は `--raw-log` 有効時、Ollama API へ送った payload と、Ollama から受け取った生NDJSONを gzip 圧縮で保存する。

raw log は調査・再現性確保のための監査ログであり、通常は Git 管理外とする。

## 保存先

```text
{workdir}/_raw_logs/{phase}/{run_timestamp}_{pid}_{sequence}_{kind}/
  raw_summary.md
  details/
    request_{attempt}_{seed_offset}.json.gz
    response_{attempt}_{seed_offset}.json.gz
    response.json.gz
    _timeout.json.gz
    _http_err.json.gz
    _empty.json.gz
```

| 要素 | 形式 | 説明 |
|---|---|---|
| `phase` | `plan`, `design`, `write`, `export`, `resume`, `complete`, `unknown` | CLIフェーズ |
| `run_timestamp` | `YYYYMMDD_HHMMSS` | `LLMClient` 生成時刻 |
| `pid` | 数字 | 実行プロセスID |
| `sequence` | `0001`, `0002`, ... | 同一プロセス内の LLM 呼び出し連番。同一 `kind` 複数回実行の上書きを防ぐ |
| `kind` | 例: `scene_draft`, `review`, `volume_design` | 呼び出し元のタスク識別子 |
| `attempt` | `0`, `1`, ... | リトライ試行番号 |
| `seed_offset` | 数字 | 呼び出し側から渡された seed offset |

## 保存内容

### `details/request_{attempt}_{seed_offset}.json.gz`

Ollama `/api/chat` へ送る payload を `json.dumps(..., ensure_ascii=False)` した文字列をそのまま保存する。

含まれる主な内容:

- `model`
- `messages[0]` system prompt
- `messages[1]` user prompt（schema展開後）
- `format: "json"`
- `options` (`num_ctx`, `num_predict`, `seed`, config由来の Ollama options)
- `think`

### `details/response_{attempt}_{seed_offset}.json.gz`

Ollama から受け取った生NDJSONを、改行で結合した文字列のまま保存する。JSON parse / schema validation に失敗した場合も保存する。

### `details/response.json.gz`

`_call_api()` 内部が正常HTTPレスポンス受信時に保存する補助ログ。監査上の正は attempt 番号付きの `response_{attempt}_{seed_offset}.json.gz` とする。

### `details/_timeout.json.gz`, `_http_err.json.gz`, `_empty.json.gz`

API呼び出し中にタイムアウト、HTTPエラー、空レスポンスが発生した場合の補助ログ。可能な範囲で受信済みの生データまたはエラー文字列を保存する。

## 上書き防止

- 1回の `complete_json()` 呼び出しごとに `sequence` 付きの専用ディレクトリを作る。
- リトライごとに `request_{attempt}_{seed_offset}` / `response_{attempt}_{seed_offset}` を分ける。
- 同名ファイルが既に存在する場合は `_1`, `_2`, ... の suffix を付けて保存し、既存ログを上書きしない。

## 人間向け summary

各呼び出しディレクトリの `raw_summary.md` に、リクエスト/レスポンスを読みやすい形式で追記する。

`raw_summary.md` は可読性のために整形される。完全な監査対象は `details/*.json.gz` とする。

## 設計方針

- 送信 payload を欠落なく保存する。
- 受信 raw NDJSON を欠落なく保存する。
- JSON parse error / schema validation error / LLMError / unexpected error の発生時も、可能な限り request と response を保存する。
- retry と同一 kind の複数呼び出しで、過去ログが消えないようにする。
