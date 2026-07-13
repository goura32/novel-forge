# Scene Coverage Extraction

## 目的

固定済みのシーン本文から、publication gate が検証する obligation evidence を抽出する。

## 応答方針

本文を執筆・改稿・要約・言い換えしない。本文内に実在する文字列だけを引用する。

## 実行指示

`obligations.required_beat_indexes` にある **すべての index を一回ずつ** `required_beat` として出力する。`end_constraint` は required beat の代わりではなく、`obligations.requires_end_constraint` が true のときに追加で一回出力する。`draft.content` を句点（`。`、`！`、`？`）単位で、先頭からゼロ始まりに分割した文の `sentence_index` を返す。本文の文言を出力してはいけない。根拠が見つからない義務は推測・要約・創作せず、その evidence を出力しない。

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
