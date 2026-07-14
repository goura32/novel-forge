# Ollama API Contract

## Configuration

productionの`RuntimeConfig.load()`は`~/.config/novel-forge/config.yaml`だけを読みます。workspace-local config、カレントディレクトリ探索、`NOVEL_FORGE_CONFIG`、`OLLAMA_HOST`、`OLLAMA_OPTIONS` overlayはpublic runtime設定の解決順に含まれません。

```yaml
quality:
  max_generation_attempts: 3
llm:
  ollama_host: "ws1.local:11434"
```

未知・廃止キーはエラーです。

## Request boundary

`LLMClient.complete_json()`はOllama `/api/chat`を呼び、attempt-scoped captureへrequest、stream response、parsed payload、validation結果を保存します。PNCA production adapterはtask registryが許可したprojectionとresource schemaだけを渡します。

## Retry boundary

JSON parse、schema validation、schema echoは`quality.max_generation_attempts`まで再生成します。初回も1回として数えます。transport / provider errorは自動retryせず、1 attemptを失敗として確定します。

hard repairは最大2回、quality polishは最大1回であり、Ollama transport retry設定ではありません。
