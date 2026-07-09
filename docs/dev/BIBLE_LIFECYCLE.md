# 廃止：Series Bible 旧ライフサイクル

> **この文書は 2026-07-10 に廃止されました。実装仕様として使用してはいけません。**
>
> Series Bible v2 の唯一の仕様正本は
> [`SERIES_BIBLE_SCHEMA_REDESIGN.md`](SERIES_BIBLE_SCHEMA_REDESIGN.md) です。

旧ライフサイクルは、次の v2 決定と矛盾するため内容を保持しません。

- `bible.json` を唯一の正本とし、巻末 snapshot を復元根拠にすること
- volume / chapter design が Canon を直接更新すること
- scene 番号・名称・description による暗黙的な identity / 冪等処理
- runtime 抽出された fact / continuity note を Canon に反映すること
- event replay、dependency validation、segment replacement が存在しないこと

履歴が必要な場合は Git でこの文書の過去 revision を参照してください。
