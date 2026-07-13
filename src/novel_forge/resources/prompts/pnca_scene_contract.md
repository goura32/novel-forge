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
- `writer_view` は `start_context`、`narrative_contract`、`end_constraints`、`presentation_constraints`、`required_beats` のみを持つ。`required_beats` は2〜4個の短い順序付き本文到達点で、各項目をPOV人物が知覚可能な行為・台詞・反応として書く。これらの内部 object も、本文を生成するための状況・展開・終点・視点表現だけを記述し、要約、監査、Canon、event log、frontier binding、artifact ID、stable ID、本文を示すキーを一切含めない。
- `writer_view` を含む自然言語値はすべて自然な日本語で書く。簡体字・繁体字・ハングル・混在した外国語表記を出力しない。

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
