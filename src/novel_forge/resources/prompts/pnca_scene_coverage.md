# Scene Coverage Extraction

## 目的

固定済みのシーン本文から、publication gate が検証する obligation evidence を抽出する。

## 応答方針

本文を執筆・改稿・要約・言い換えしない。本文内に実在する文字列だけを引用する。

## 実行指示

`obligations.required_beat_indexes` にある **すべての index を漏れなく、かつ余分に出さずに、厳密に一回ずつ** `required_beat` として出力する（例: indexes=[0,1,2] なら required_beat を正確に3つ、index 0/1/2 各1つずつ出力。2つや4つは不可）。`end_constraint` は required beat の代わりではなく、`obligations.requires_end_constraint` が true のときに追加で**厳密に一回だけ**出力する（0回でも2回以上でもなく、必ず1回）。各 obligation の `draft_quote` は本文内の該当箇所を「完全一致」で引用し、paraphrase や要約は禁止。根拠が見つからない義務は推測・要約・創作せず、その evidence を出力しない。

### evidence のフィールドルール（厳守）
- `required_beat` の evidence には、**その beat のゼロ始まり index を `beat_index` に整数で必ず入れる**（例: 3番目の required beat なら `beat_index: 2`）。`beat_index` を省略・null にしてはならない。
- `end_constraint` の evidence には `beat_index` を**含めてはならない**（無視される）。`sentence_index` のみを入れる。
- `sentence_index` は、固定済み本文を句点（。！？）で分割したときのゼロ始まり index で、その obligation を証明する文の位置を指す。
- `obligation` は `"required_beat"` または `"end_constraint"` のいずれかのみ。

## 入力情報

### WriterView

{writer_view}

### Required obligations

{obligations}

### Fixed draft

{draft}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
