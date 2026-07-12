# 巻設計改訂

## 目的
レビュー指摘を解消した完全な巻設計を返す。

## 応答方針
`issues[].field` に関係しないフィールドは原則として元の値を保持する。整合性調整が必要な場合だけ、最小限変更する。明示的な指摘がない限り変更しない。

## 実行指示
### 改訂対象
{current_volume}

### レビュー指摘
{review}

### 企画
{series_plan}

### Canon
{canon_context}

### 有効なCanon ID（完全白リスト）
{valid_canon_ids}

**差分・JSON Patch・変更箇所だけの出力は禁止。必ず完全なオブジェクトを返す。最上位キー `title`、`premise`、`chapters` をすべて含め、各 `chapters[]` は `title` と `purpose` を必ず含める。**

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
