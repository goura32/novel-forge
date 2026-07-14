# NovelForge ドキュメント

## はじめに

| 読むもの | 目的 |
|---|---|
| [README](../README.md) | インストール、PNCA-only の概要、最短の実行例 |
| [USER_GUIDE.md](USER_GUIDE.md) | series / volume / snapshot / artifact の利用方法 |
| [OPERATIONS.md](OPERATIONS.md) | 本番の個別工程フロー、進捗、復旧、LLM evidence の調査 |
| [CLI_REFERENCE.md](CLI_REFERENCE.md) | 全公開 CLI の引数と読み取り／変更区分 |

## 設計と契約

| 読むもの | 目的 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | immutable runtime、PNCA workflow、artifact境界 |
| [PROMPT_SCHEMA_MAP.md](PROMPT_SCHEMA_MAP.md) | 各PNCA taskの prompt / schema / validator 対応 |
| [PROMPTS.md](PROMPTS.md) | prompt編集時の責務と検証方法 |
| [schemas.md](schemas.md) | runtime record と artifact schema の規約 |

## 調査・開発

| 読むもの | 目的 |
|---|---|
| [dev/raw_log_format.md](dev/raw_log_format.md) | attempt-scoped LLM evidence のファイル形式 |
| [dev/2026-07-14-pnca-audit.md](dev/2026-07-14-pnca-audit.md) | 7:30以降の変更の監査、誤解・失敗と是正方針 |
| [dev/QUALITY_DISPOSITION_POLICY.md](dev/QUALITY_DISPOSITION_POLICY.md) | hard failure / editorial debt の工程横断進行ポリシー |
| [dev/acceptance.md](dev/acceptance.md) | acceptance / snapshot の開発時チェック |
| [../AGENTS.md](../AGENTS.md) | リポジトリ作業ルール |

## 読む順序

- **利用者**: README → USER_GUIDE → OPERATIONS → CLI_REFERENCE
- **障害調査**: OPERATIONS → raw_log_format → run / attempt / llm diff
- **実装変更**: ARCHITECTURE → PROMPT_SCHEMA_MAP → schemas → audit記録 → tests

legacy互換・旧mutable stateの文書は置かず、現行PNCA contract と immutable runtime を唯一の仕様とします。
