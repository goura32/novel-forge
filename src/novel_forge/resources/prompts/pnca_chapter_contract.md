# PNCA Chapter Contract の生成

## 目的

入力 Volume Contract と chapter request から指定章の Scene slot topology を作る。

## 応答方針

親 Volume の `chapter_plans` から request ordinal と一致する immutable ChapterPlan が既に選択されている。chapter purpose、relationship shift、reader pull、scene_count を変更・再解釈せず、その scene_count と同数の slot を作る。

## 実行指示

各 `scene_slots` item は `slot_id`、一意で昇順の `ordinal`、`mandate` を必須にする。mandate は `start_state`、`required_transition`、`end_state`、`relationship_contribution`、`prohibited_repetition` を全て自然な日本語で具体化する。同じ調査、同じ対話、同じ到達状態を別 slot に反復してはならない。scene-level prose、Canon patch、writer view は出力しない。admission allowance ID は親に存在するものだけを使う。

## 入力情報

### parent
{parent}

### request
{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
