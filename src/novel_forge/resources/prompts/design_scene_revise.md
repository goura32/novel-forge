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

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
