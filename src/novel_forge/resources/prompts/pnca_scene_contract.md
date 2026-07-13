# PNCA Scene Contract Proposal の生成

## 目的

入力された Chapter Contract、固定された Canon frontier、scene request だけを根拠に、指定された一つの slot の実行可能な Scene Contract proposal を作る。

## 応答方針

frontier artifact ID、frontier digest、snapshot ID、artifact ID は出力しない。これらは repository が入力 provenance から materialize する。writer に渡せる authority は `writer_view` の四フィールドだけであり、Canon payload や stable ID を混ぜない。

## 実行指示

- `slot_id` は入力 scene request の `slot_id` と完全一致させる。
- Chapter Contract に存在しない slot を作らない。
- `canon_effect` が `none` の場合、`canon_patch` は省略する。
- `canon_effect` が `mutates` の場合だけ、frontier と slot authority に根拠を持つ non-empty `canon_patch` を返す。
- `requirement_dispositions` は parent requirements の扱いを明示し、deferred は許可済み descendant slot だけを指す。
- `admission_consumptions` は selected slot が許可した allowance だけを消費する。
- `writer_view` は `start_context`、`narrative_contract`、`end_constraints`、`presentation_constraints` のみを持つ。
- summary、audit、event log、frontier binding、artifact ID、本文を出力しない。

## 入力情報

### Chapter Contract
{parent}

### Canon frontier
{frontier}

### Scene request
{request}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
