# NovelForge ドキュメント

## 利用者向け

| 文書 | 目的 |
|---|---|
| [README](../README.md) | インストール、設定、最短のPNCA実行例 |
| [USER_GUIDE.md](USER_GUIDE.md) | Series / Volume / Chapter / Sceneの段階的な利用方法 |
| [OPERATIONS.md](OPERATIONS.md) | 個別工程の運用、復旧、evidence調査 |
| [CLI_REFERENCE.md](CLI_REFERENCE.md) | 公開CLIと引数 |
| [GLOSSARY.md](GLOSSARY.md) | PNCA・artifact・品質用語 |

## 現行の開発契約

| 文書 | 目的 |
|---|---|
| [dev/ARCHITECTURE.md](dev/ARCHITECTURE.md) | PNCA production path、snapshot、artifact境界 |
| [PROMPT_SCHEMA_MAP.md](PROMPT_SCHEMA_MAP.md) | 現行PNCA task、prompt、schemaの対応 |
| [PROMPTS.md](PROMPTS.md) | prompt変更時の責務と検証 |
| [dev/QUALITY_DISPOSITION_POLICY.md](dev/QUALITY_DISPOSITION_POLICY.md) | hard failure / deferred editorial debt / export gate |
| [dev/LLM_REVIEW_CONTRACT.md](dev/LLM_REVIEW_CONTRACT.md) | LLM生成・audit・bounded revision契約 |
| [dev/raw_log_format.md](dev/raw_log_format.md) | attempt-scoped LLM evidence形式 |
| [dev/schema_maintenance.md](dev/schema_maintenance.md) | schema / prompt / production adapterの同期手順 |
| [dev/OLLAMA_API.md](dev/OLLAMA_API.md) | canonical configとOllama API境界 |

## 履歴・将来設計

| 文書 | 状態 |
|---|---|
| [dev/2026-07-14-pnca-audit.md](dev/2026-07-14-pnca-audit.md) | 監査記録。現行仕様ではない |
| [dev/PNCA_IMPLEMENTATION_PLAN.md](dev/PNCA_IMPLEMENTATION_PLAN.md) | 実装計画の履歴。現行仕様ではない |
| [dev/PROGRESSIVE_NARRATIVE_CONTRACT_ARCHITECTURE.md](dev/PROGRESSIVE_NARRATIVE_CONTRACT_ARCHITECTURE.md) | 将来提案。未実装要素を含む |
| [dev/RUNTIME_ARTIFACT_RETENTION_REDESIGN.md](dev/RUNTIME_ARTIFACT_RETENTION_REDESIGN.md) | superseded |
| [dev/CANON_DSL_V2_DESIGN.md](dev/CANON_DSL_V2_DESIGN.md) | superseded |
| [dev/SERIES_BIBLE_SCHEMA_REDESIGN.md](dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) | historical record |

## 読む順序

- **利用者**: README → USER_GUIDE → OPERATIONS → CLI_REFERENCE
- **障害調査**: OPERATIONS → raw_log_format → run / attempt / llm
- **実装変更**: ARCHITECTURE → PROMPT_SCHEMA_MAP → QUALITY_DISPOSITION_POLICY → tests
