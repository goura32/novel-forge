# ドキュメント索引

最終更新: 2026-07-10

この索引にある文書だけを現行の案内・仕様として扱います。完了済みの改善計画、過去の監査レポート、廃止済み Bible 仕様は Git 履歴で参照してください。

## 利用者・運用者

| 目的 | 文書 |
|---|---|
| 導入と最短実行 | [README](../README.md) |
| 基本的な操作 | [USER_GUIDE](USER_GUIDE.md) |
| CLI の引数と出力 | [CLI_REFERENCE](CLI_REFERENCE.md) |
| 中断、ログ、接続障害の対応 | [OPERATIONS](OPERATIONS.md) |
| 入力キーワードの作り方 | [KEYWORD_SELECTION_GUIDE](KEYWORD_SELECTION_GUIDE.md) |
| 用語 | [GLOSSARY](GLOSSARY.md) |

## 開発者

| 目的 | 文書 |
|---|---|
| 現在の runtime 構成、データフロー、v2 との境界 | [ARCHITECTURE](dev/ARCHITECTURE.md) |
| prompt の役割・改善方針 | [PROMPTS](PROMPTS.md) |
| prompt / schema / 実行経路 | [PROMPT_SCHEMA_MAP](PROMPT_SCHEMA_MAP.md) |
| JSON Schema の変更と検証 | [schema_maintenance](dev/schema_maintenance.md) |
| raw LLM log の保存形式 | [RAW_LOG_FORMAT](dev/raw_log_format.md) |
| Ollama 接続・payload の実装上の契約 | [OLLAMA_API](dev/OLLAMA_API.md) |

## Series Bible v2

[Series Bible v2 — Canon Event Architecture](dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) が、**未実装の破壊的再設計に関する唯一の仕様正本**です。現行 runtime の `bible.json` を説明する文書ではありません。
