# Scene Coverage Extraction

## 目的

固定済みのシーン本文から、publication gate が検証する obligation evidence を抽出する。

## 応答方針

本文を執筆・改稿・要約・言い換えしない。本文内に実在する文字列だけを引用する。

## 実行指示

各 obligation を独立に審査する。本文内に、その obligation の要求する行為・発話・到達状態が完了していることを直接証明する一文がある場合だけ、その obligation の evidence を厳密に一回出力する。要求の一部だけに触れた文、近接する別の行為、主語や語句だけが似た文は証拠にしてはならない。根拠が見つからない義務は推測・要約・創作せず、その evidence を出力しない。不足したevidenceはpublication gateが拒否するため、required beatやend constraintの件数を埋める目的で無関係な `sentence_index` を出力してはならない。`obligations.requires_end_constraint` が true のときも、終端状態を直接証明できる場合だけ `end_constraint` を一回出力する。

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
