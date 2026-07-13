# PNCA Chapter Contract の生成

## 目的

入力された Volume Contract と chapter request だけを根拠に、指定章の順序付き Scene slot topology を作る。

## 応答方針

親 Volume Contract の authority を超える章目的、scene beats、Canon 事実、本文を作らない。Scene slot は後続 Scene Contract authoring の配置だけを定義する。

## 実行指示

- `parent_volume_contract_id` は入力 parent の `contract_id` と完全一致させる。
- `chapter_ordinal` は入力 request の `chapter_ordinal` と完全一致させる。
- `scene_slots` は空にせず、`ordinal` を 1 から昇順・重複なしにする。
- `slot_id` は Chapter 内で一意な stable ID にする。
- `allowed_admission_allowance_ids` には parent の `admission_allowances` に存在する ID だけを入れる。不要なら空配列にする。
- scene-level goal / conflict / outcome / beats、Canon patch、writer input、本文は出力しない。
- 不自然な英語、簡体字、ハングルを混在させず、自然な日本語で書く。

## 入力情報

### parent

{parent}

### request

{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
