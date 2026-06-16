# 巻アウトラインの自己修正

## 指示

以下の巻アウトラインを、レビュー結果に基づいて修正せよ。

## 入力

- 現在のアウトライン: `{outline}`（テキスト形式）
- レビュー結果: `{review}`（テキスト形式）
- シリーズ企画: `{series_plan}`（テキスト形式）
- 出力言語: `{lang}`

## 修正方針

1. `critical` の issue は必ず修正すること
2. `major` の issue は可能な限り修正すること
3. `minor` の issue は余力があれば修正すること
4. 部分修正を基本とする。全体再生成は最終手段

## 出力スキーマ

`volume_outline.json` に適合する JSON を出力すること。修正前後の差分を `volume_outline_revision_log.json` に記録すること。
