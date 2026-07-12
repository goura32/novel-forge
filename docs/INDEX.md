# ドキュメント索引

最終更新: 2026-07-12

この索引にある「現行」文書を、利用・運用・実装の案内として扱います。過去の再設計案は履歴資料であり、live runtimeの説明には使いません。

## 利用者・運用者

| 目的 | 文書 |
|---|---|
| 導入と最短実行 | [README](../README.md) |
| 基本操作と成果物 | [USER_GUIDE](USER_GUIDE.md) |
| CLI引数と出力 | [CLI_REFERENCE](CLI_REFERENCE.md) |
| 中断、LLM evidence、接続障害 | [OPERATIONS](OPERATIONS.md) |
| 入力キーワードの作り方 | [KEYWORD_SELECTION_GUIDE](KEYWORD_SELECTION_GUIDE.md) |
| 用語 | [GLOSSARY](GLOSSARY.md) |

## 開発者: 現行runtime

| 目的 | 文書 |
|---|---|
| immutable runtime、snapshot、Canon frontier | [ARCHITECTURE](dev/ARCHITECTURE.md) |
| promptの役割・改善方針 | [PROMPTS](PROMPTS.md) |
| prompt / schema / 実行経路 | [PROMPT_SCHEMA_MAP](PROMPT_SCHEMA_MAP.md) |
| LLMのgeneration・review・revision境界 | [LLM_REVIEW_CONTRACT](dev/LLM_REVIEW_CONTRACT.md) |
| JSON Schemaの変更と検証 | [schema_maintenance](dev/schema_maintenance.md) |
| attempt-scoped LLM evidence形式 | [raw_log_format](dev/raw_log_format.md) |
| Ollama接続・payload・retry契約 | [OLLAMA_API](dev/OLLAMA_API.md) |

## 履歴資料

[Runtime Artifact Retention Redesign](dev/RUNTIME_ARTIFACT_RETENTION_REDESIGN.md) と [Series Bible Schema Redesign](dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) は、採用済みの破壊的再設計に関する設計記録です。現在のCLI・artifactパス・設定・LLM evidenceの説明には、上記の現行runtime文書と実装を使用してください。
