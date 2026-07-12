# Ollama API契約

最終更新: 2026-07-12

この文書は、NovelForgeのpublic CLIがOllama `/api/chat` を利用する際の実装契約です。

## 設定と接続

- endpoint: `http://<llm.ollama_host>/api/chat`
- canonical config: `~/.config/novel-forge/config.yaml`
- CLIでのmodel上書き: `--model`
- 診断: `uv run novel-forge doctor -w <workdir>`

productionの `RuntimeConfig.load()` はcanonical configだけを読みます。workspace-local config、カレントディレクトリ探索、`NOVEL_FORGE_CONFIG`、`OLLAMA_HOST` はpublic runtime設定の解決順には含まれません。

## request payload

`LLMClient.complete_json()` は次の形で `/api/chat` を呼び出します。

```json
{
  "model": "qwen3.6:35b-a3b-mtp-q4_K_M",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "format": "json",
  "options": {
    "seed": 123
  },
  "think": false
}
```

`options` には `llm.ollama_options` のうち `think` 以外が加わります。`think` はtop-levelへ送信されます。retryごとにseedは変化します。`think` の扱いは利用モデルで確認してください。

## responseと検証

- `/api/chat` はNDJSONストリーミングで応答する
- 各chunkの `message.content` を結合して最終contentを作る
- task runnerはTaskRegistryから対応schemaを解決し、LLM clientへ渡す
- JSON parseとSchema validationを通過した値だけが候補artifactになる

全LLM呼び出しのrequest・NDJSON・最終content・validationはattempt-scoped evidenceとして保存されます。詳細は [Attempt-scoped LLM evidence形式](raw_log_format.md) を参照してください。

## retryと失敗

JSON parse failure、Schema validation failure、LLM contract failureは `quality.max_retry_count` の上限まで、別attemptとして再生成されます。transport errorはretryableではなく、1回のattemptに `error.json` を残して呼び出し側へ返します。

`quality.max_review_count` と `quality.max_summary_review_count` はreview / reviseサイクルの上限であり、transport retry設定ではありません。

## 接続不良の調査

```bash
curl -fsS http://<ollama-host>/api/tags >/dev/null && echo OK || echo FAIL
uv run novel-forge doctor -w <workdir> --ollama-host <host:port>
```

接続に成功しても生成contractが失敗する場合は、attempt配下の `llm/request.json`、`response.ndjson`、`validation.json` を順に確認してください。
