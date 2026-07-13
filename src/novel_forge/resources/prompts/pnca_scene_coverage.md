# Scene Coverage Extraction

## 目的

固定済みのシーン本文から、publication gate が検証する obligation evidence を抽出する。

## 応答方針

本文を執筆・改稿・要約・言い換えしない。本文内に実在する文字列だけを引用する。

## 実行指示

`draft.content` から文字列をそのままコピーして `draft_quote` に入れる。各 `required_beats` を完了した本文内の箇所を、ゼロ始まりの `beat_index` とともに一件ずつ返す。`end_constraints` が空でなければ、終了状態を示す本文内の箇所を `end_constraint` として一件返す。引用が見つからない義務は推測・要約・創作せず、その evidence を出力しない。

## 入力情報

### WriterView

{writer_view}

### Fixed draft

{draft}

## 出力仕様

下記のスキーマに適合する JSON のみ出力すること。

{schema}
