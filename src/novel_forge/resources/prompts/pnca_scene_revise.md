# PNCA Scene Draft の改訂

## 目的

WriterViewを唯一の本文 authority とし、入力された草稿を audit issues の根拠に従って改訂する。指摘のない内容を壊さない。

## 応答方針

本文以外を出力せず、既存の語り・場面・設定の連続性を維持する。

## 実行指示

- `issues` の各指摘を本文で解消する。
- `WriterView` は唯一の事実源である。`start_context` の場所・時刻・登場人物・現在状況、`end_constraints` の到達状態、`presentation_constraints` の視点・文体をすべて保持する。特に場所は `start_context` にある一つだけを使い、他の入力中の固有名詞から場所を推測・置換してはならない。
- issue が WriterView 内の複数箇所を引用していても、`start_context` と `end_constraints` を優先し、矛盾する語句は本文に持ち込まない。
- `issues[].field` に関係しないフィールドは原則として元の値を保持する。
- 整合性調整が必要な場合だけ、最小限変更する。
- 明示的な指摘がない限り変更しない。
- WriterViewにない設定・Canon・固有IDを追加しない。
- 日本語だけで自然な散文にする。

## 入力情報

### WriterView
{writer_view}

### Current draft
{draft}

### Audit issues
{issues}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
