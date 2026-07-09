# RAW LLM log 形式

`-v` / `--verbose` を付けて実行した場合、runtime は `<workdir>/_raw_logs/` に LLM 呼び出し単位のログを保存します。通常の実行では raw log を保存しません。

```text
_raw_logs/
  <phase>/
    <YYYYMMDD_HHMMSS>_<pid>_<sequence>_<kind>/
      summary.md
      summary/
        request_<attempt>_<seed_offset>.md
        response_<attempt>_<seed_offset>.md
      details/
        request_<attempt>_<seed_offset>.json.gz
        response_<attempt>_<seed_offset>.json.gz
        _timeout.json.gz | _http_err.json.gz | _transport_err.json.gz | _empty.json.gz
```

| 要素 | 内容 |
|---|---|
| `phase` | `plan` / `design` / `write` などの実行工程 |
| `sequence` | 同一プロセス内の LLM 呼び出し番号。再試行・同 kind の上書きを防ぐ |
| `kind` | `scene_design`、`review` などの task 名 |
| `attempt` / `seed_offset` | 生成・改稿の試行識別子 |

## 保存内容

- `details/*.json.gz`: Ollama へ送った payload、または受信した生 NDJSON / 例外文字列。完全な監査対象です。
- `summary.md`: request / response の時系列索引です。
- `summary/request_*.md`: API 設定と prompt 本文を読みやすく表示します。
- `summary/response_*.md`: `message.content` を表示します。`thinking` と transport wrapper は含めません。

raw log にはプロンプト、入力シリーズ情報、モデル応答が含まれ得ます。シリーズ成果物と同様に扱い、Git に追加しないでください。
