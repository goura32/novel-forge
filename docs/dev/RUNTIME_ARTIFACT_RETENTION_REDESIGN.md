# Runtime artifact retention redesign（廃止済み設計メモ）

> **Status: superseded — 2026-07-14**
>
> この文書には、かつて存在した合成 `complete` CLI を前提にした lock / run 設計が含まれていました。`complete` は公開CLIから削除済みであり、この文書を現行仕様として参照してはいけません。

## 現行仕様

- 実行は `plan` → `design` → `write` → `export` の個別CLIで行う。
- 各CLI起動が独立した immutable run になる。
- selection snapshot と artifact lineage が工程間の引継ぎの唯一の根拠である。
- LLM呼出しは invocation ごとの attempt となり、request / response NDJSON / content / parsed JSON / validation を `attempts/<id>/llm/` に残す。
- 進捗は `events.jsonl` の `progress` event と標準エラーの `[PROGRESS]` 行で確認する。

運用手順は [OPERATIONS.md](../OPERATIONS.md)、実装判断・過去の誤りは [2026-07-14 PNCA audit](2026-07-14-pnca-audit.md) を参照してください。
