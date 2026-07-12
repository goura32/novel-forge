# シーン設計生成

## 目的
親章の意図を満たす、Canon ID参照だけを使うシーン設計を生成する。

## 応答方針
表示名からIDを推測しない。許可Canonにない人物・場所を使わず、必要ならreviewで明示的に不備として扱える設計にする。

## 実行指示
pov_character_id、character_ids、location_id はCanonのIDを完全一致で返す。hook は冒頭の読者関心、turning_point は場面の不可逆な転換、ending_hook は次場面を読む理由、key_events は実際の出来事を順に書く。canon_updates は既存entityの単純更新だけを返し、CanonPatchを直接返さない。

canon_updates の各要素は operation / target_id / value を必ず含む。operation は以下の4値のいずれかのみ使用すること（その他の値は禁止）:
- "set_character_state" : キャラクターの状態を更新（target_id = キャラクターID）
- "set_location_state" : 場所の状態を更新（target_id = 場所ID）
- "set_artifact_condition" : アイテムの状態を更新（target_id = アイテムID）
- "transfer_artifact" : アイテムの所持者を変更（target_id = アイテムID、holder_id = 新しい所持者ID）

"update_state" 等の独自値は使用しないこと。target_id は canon_context 内の既存IDを完全一致で指定すること。value は canon_context 内の現在の状態と明確に異なる値を書くこと。現在の状態と同じ値を書くと no-op（空更新）となり拒否されるため、変化がない場合はその update を canon_updates に含めないこと。

### 入力情報
### シリーズ企画
{series_plan}

### 巻と章
{volume_title}

### シーン種
{scene_seed}

### Canon
{canon_context}

## 出力仕様
下記のスキーマに適合する JSON のみ出力すること。

{schema}
