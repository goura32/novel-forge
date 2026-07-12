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

### Canon 制約の厳守
canon_context の world_rules / series_constraints / locations[].immutable_constraints に書かれた制約は、key_events / setting / outcome の生成時に絶対に守る。Canon の `characters[]` は `character_id` と表示名の対応表であり、`character_ids` にはこの表にある ID だけを完全一致で入れる。表示名だけから人物や ID を推測せず、対応表にない人物名は登場者・発言者・更新対象として書かない。

`current_state` と場所・アイテムの現在状態は、このシーン開始時点の確定事実である。状態が「解消済み」「離脱中」「局所的」「使用不可」なら、key_events / outcome でその反対の状態を前提にしない。状態を変える必要があるときだけ、原因から結果までが分かる明確な canon_updates を書く。

具体的には以下を破る描写を書かないこと：
- 結界の範囲（例：店外では妖怪への直接干渉は不可能、店内のみ会話・干渉可）
- 年代の統一（例：明治初期＝1870年代。別の時代表記と混在させない）
- 物理法則の扱い（例：怪異の影響であっても急激な凍結・結露等の極端な環境変化は避ける）
- world_rules で限定された知覚・能力・道具の機能を拡張しない。明示されない感官、戦闘機能、増幅・反射などの作用を推測で追加しない
- Canon で定義されていない怪異名・術名・固有名詞を新規に導入しない（既存 entity の名前のみ使用）
- 人物の接触可能性は結界の範囲に従う（例：神楽響は現在結界外にいるため、朔が直接触れ・対話できるのは店内の痕跡「幻燈り」のみ。神楽本人への直接的な応答描写は書かない）
- canon_updates には必ず現在の状態と異なる値を書くこと。シーンで状態変化が生じない場合は canon_updates を空配列 `[]` にすること（重複更新・no-op 更新は書かない）

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
