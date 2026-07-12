# シーン設計改訂

## 目的
レビュー指摘を解消した、物語設計と完全 `canon_patch` を返す。

## 応答方針
`issues[].field` に関係しないフィールドは原則として元の値を保持する。整合性調整が必要な場合だけ、最小限変更する。明示的な指摘がない限り変更しない。レビューが空なら candidate を不必要に作り替えない。

## Canon mutation の改訂規則
- `canon_patch` は旧 `canon_updates` ではなく、section ごとの strict CanonPatch を返す。
- 既存 entity は valid Canon ID を完全一致で参照し、型付き update を使う。表示名や推測 ID に置き換えない。
- 新規 entity は該当 section の `create` に必須属性と `creation_key` を書く。final stable ID は書かない。
- 同一 scene 内の新規 entity の参照は `@created:<creation_key>` に統一する。POV / cast / setting と patch 内参照にも使える。
- review が「未定義の場所・人物・物品・知識が物語上必要」と指摘した場合、既存 ID に無理に寄せず、適切な create payload を追加する。
- review が create の過剰・必須属性不足・Canon 矛盾を指摘した場合だけ、その create を削除または修正する。
- no-op update は削除する。変化がないなら update を捏造しない。
- review の `after` に未定義 final ID があっても採用しない。新規 entity は ID 推測でなく `creation_key` と create payload で表現する。

## 実行指示
title、goal、conflict、outcome、POV、cast、setting、`canon_patch` を完全に返す。新規 location をこの scene の setting にする場合は `locations.create` と `location_id: "@created:<creation_key>"` を同時に返す。新規 character をこの scene の POV / cast にする場合は `characters.create` と `@created:<creation_key>` を使う。world_rules / series_constraints / immutable_constraints / current_state に反する描写・変更を入れない。

### 改訂対象
{current_scene}

### レビュー指摘
{review}

### 企画
{series_plan}

### シーン種
{scene_seed}

### Canon
{canon_context}

### 有効なCanon ID（完全白リスト）
{valid_canon_ids}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
