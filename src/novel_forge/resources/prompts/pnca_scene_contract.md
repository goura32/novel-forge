# PNCA Scene Contract Proposal の生成

## 目的

入力された Chapter Contract、固定された Canon frontier と Canon projection、scene request だけを根拠に、指定された一つの slot の実行可能な Scene Contract proposal を作る。

## 応答方針

frontier artifact ID、frontier digest、snapshot ID、artifact ID は出力しない。これらは repository が入力 provenance から materialize する。writer に渡せる authority は `writer_view` の四フィールドだけであり、Canon payload や stable ID を混ぜない。

## 実行指示

- `slot_id` は入力 scene request の `slot_id` と完全一致させる。
- Chapter Contract に存在しない slot を作らない。
- `canon_effect` が `none` の場合、`canon_patch` は省略する。
- `canon_effect` が `mutates` の場合だけ、frontier と slot authority に根拠を持つ non-empty `canon_patch` を返す。
- `requirement_dispositions` は parent requirement ledger が入力で明示された場合だけ、その各 requirement を一度ずつ扱う。この入力では parent ledger は提供されないため、必ず空配列 `[]` を返し、存在しない requirement を推測・作成しない。
- `admission_consumptions` は Volume Contract の allowance 定義がこの入力に含まれる場合だけ消費できる。現在の Scene Contract 入力にはその定義が含まれないため、必ず空配列 `[]` を返す。IDや上限を推測してはならない。
- `writer_view` は `start_context`、`narrative_contract`、`end_constraints`、`presentation_constraints` のみを持つ。
- summary、audit、event log、frontier binding、artifact ID、本文を出力しない。

## 入力情報

### Chapter Contract
{parent}

### Canon frontier
{frontier}

### Canon projection
{canon_projection}

`seed` は不変の系列設定、`events` はこの frontier までに確定した時系列事実である。新規人物・場所・組織・artifact は許可済み admission を消費して `canon_patch` に明示登録し、既存 Canon と矛盾させない。

### Scene request
{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
