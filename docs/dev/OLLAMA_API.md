# Ollama API 契約

この文書は、NovelForge が現在利用する Ollama API の実装上の契約です。特定バージョンでの過去の性能測定や数値を仕様として固定しません。接続先やモデルは `config.yaml` で上書きできます。

## 接続

- endpoint: `http://<ollama-host>/api/chat`
- host の解決: `config.yaml` の `llm.ollama_host` → `OLLAMA_HOST` → runtime 既定値
- 診断: `uv run novel-forge doctor -w <workdir>`

## request payload

`LLMClient.complete_json()` は次の形式で `/api/chat` を呼び出します。

```json
{
  "model": "qwen3.6:35b-a3b-mtp-q4_K_M",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "format": "json",
  "options": {
    "num_ctx": 262144,
    "num_predict": -1,
    "seed": 123,
    "temperature": 0.7,
    "top_p": 0.9
  },
  "think": false
}
```

- `options` には `llm.ollama_options` の値が追加されます。
- `think` は `options` 内ではなく top-level に送信されます。
- `seed` はリトライごとにインクリメントされます。
- `config.example.yaml` の既定値は `think: false` です。`think: true` を使うと JSON 出力時に `content` が空になるモデルがあるため、本番利用前は verbose log と smoke test で確認してください。

## JSON と Schema

- API の `format` は `"json"` です。
- prompt 内の `{schema}` は `PromptManager.render()` が展開済みです。`LLMClient` は受け取った payload をそのまま送信し、後処理で JSON parse と Schema validation を行います。
- 空 content、JSON parse 失敗、Schema 不一致は、`quality.max_generation_count` の上限まで再生成します。transport 層のエラーは `transport_retries` で別に制御します。

## response

- `/api/chat` は NDJSON ストリーミングです。各 chunk の `message.content` を結合して回答とします。
- `message.thinking` などの非表示推論は raw log にのみ保存し、人間向け summary には含めません。
- コンテキスト長は `/api/show` の `context_length` から検出し、取得できない場合は既定値で動作します。

## 失敗時の調査

`-v` を付けると `<workdir>/_raw_logs/` に request / response の生 payload が保存されます。形式は [raw_log_format](raw_log_format.md) を参照してください。
