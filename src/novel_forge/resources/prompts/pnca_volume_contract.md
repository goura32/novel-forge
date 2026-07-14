# PNCA Volume Contract の生成

## 目的

入力された Series Contract と volume request だけを根拠に、指定された一巻の bounded contract を作る。

## 応答方針

親 Series Contract の指定巻 purpose を越えて物語を解像度上げしない。未確定の chapter / scene / Canon 事実を作らない。

## 実行指示

- `parent_series_contract_id` は入力 parent の `contract_id` と完全一致させる。
- `volume_ordinal` は入力 request の `volume_ordinal` と完全一致させる。
- parent の同じ ordinal の `volume_purposes` を、その巻が担う唯一の目的として守る。
- `purpose` は parent の同じ ordinal の `volume_purposes[].purpose` を一字も変えずにそのまま出力する。この値は後続の Chapter / Scene に渡される達成責務である。
- `chapter_plans` はrequestの章数範囲内で巻内の章ごとに一件ずつ作る。各章で`chapter_purpose`、`relationship_shift`、`reader_pull`を具体化し、同じ逡巡・同じ危機・同じ引きを繰り返さない。scene数は2〜5から選ぶ。2は余韻・静かな近接・短い発見、3〜4は標準的な変化、5は複数の不可逆変化が連鎖する大転換だけに使い、5 scenesの章は巻内で最大2章にする。全章のscene数合計もrequestの巻budget内に収める。対立だけで連打せず、近接・安心・発見・選択を緩急として配分する。
- `admission_allowances` は、この巻で追加が必要な補助 entity に限定する。不要なら空配列にする。
- chapter 構成、scene beats、scene-level Canon patch、本文は出力しない。
- 不自然な英語、簡体字、ハングルを混在させず、自然な日本語で書く。

## 入力情報

### parent

{parent}

### request

{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
