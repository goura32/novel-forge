# 廃止：Series Bible 旧仕様

> **この文書は 2026-07-10 に廃止されました。実装仕様として使用してはいけません。**
>
> Series Bible v2 の唯一の仕様正本は
> [`SERIES_BIBLE_SCHEMA_REDESIGN.md`](SERIES_BIBLE_SCHEMA_REDESIGN.md) です。

旧仕様は、次の v2 決定と矛盾するため内容を保持しません。

- volume / chapter design が Canon を更新すること
- 文字列・description・位置番号を identity として扱うこと
- `apply_design_update()` による暗黙マッピング
- `bible.json` を唯一の正本とすること
- event replay なしの snapshot 巻き戻し
- runtime の facts / continuity notes を Canon 更新に利用できること

履歴が必要な場合は Git でこの文書の過去 revision を参照してください。
