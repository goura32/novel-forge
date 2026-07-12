# シーン設計改訂

## 目的
レビュー指摘を解消した完全なID-onlyシーン設計を返す。

## 応答方針
`issues[].field` に関係しないフィールドは原則として元の値を保持する。整合性調整が必要な場合だけ、最小限変更する。明示的な指摘がない限り変更しない。

## 実行指示
title、goal、conflict、outcomeを完全に返す。IDはCanonにある完全一致だけを用い、CanonPatchを直接返さない。

canon_updates の各要素は operation / target_id / value を必ず含む。operation は以下の4値のいずれかのみ使用すること（その他の値は禁止）:
- "set_character_state" : キャラクターの状態を更新（target_id = キャラクターID）
- "set_location_state" : 場所の状態を更新（target_id = 場所ID）
- "set_artifact_condition" : アイテムの状態を更新（target_id = アイテムID）
- "transfer_artifact" : アイテムの所持者を変更（target_id = アイテムID、holder_id = 新しい所持者ID）

"update" 等の独自値は使用しないこと。target_id は canon_context 内の既存IDを完全一致で指定すること。value は canon_context 内の現在の状態と明確に異なる値を書くこと。変化がない場合はその update を canon_updates に含めないこと。

### レビュー指摘の適用ルール
- review で「no-op（空更新）」「現在の状態と重複」「不要な更新」と指摘された canon_updates 要素は、canon_updates から除外すること。残すべき更新がない場合は空配列 `[]` を返すこと（空配列は許容される）。
- 除外後に canon_updates が空になるのは正常なので、無理に更新を捏造しないこと。
- 結界の範囲・年代・物理法則などの Canon 制約（canon_context の world_rules / series_constraints / locations[].immutable_constraints）に反する描写が review で指摘された場合、該当の key_events / setting / outcome を制約に合うよう書き換えること。

### 改訂対象
{current_scene}

### レビュー指摘
{review}

レビューの `after` に canon_context に存在しないIDが含まれていた場合、その指摘は適用せず元の有効な値を保持する（誤ったIDの混入を防ぐ）。既存の有効な `location_id` を、場所名の細部を表現するために `loc_00x` のような未定義IDへ置き換えてはならない。Canonに未定義の場所名は、現在の有効な `location_id` を維持したまま、その場所の範囲・周辺として setting / key_events を書き換える。canon_updates の target_id も canon_context に存在するIDのみを用い、新規エンティティの作成・追加は行わない。**「有効なCanon ID」リストにあるIDを新規作成・追加するような変更は絶対に行わない。**

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
