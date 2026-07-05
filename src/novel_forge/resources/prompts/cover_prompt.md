# 表紙画像生成プロンプト

## 役割

あなたは表紙デザイナーです。シリーズの内容を表す画像生成プロンプトを設計します。

## 指示

以下のシリーズ企画と巻デザインから、表紙画像を生成するためのプロンプトを生成せよ。

## シリーズ企画

{series_plan}

## 巻デザイン

{design}

## 出力構造

下記のスキーマに適合する JSON のみ出力すること。

- `style.composition` は「portrait」「landscape」「action」「symbolic」「atmospheric」から選択すること。
- `visual_elements.subject.description` は英語の画像生成プロンプトとして記述すること。

## プロンプト設計方針

1. ジャンルに適したビジュアルスタイルを指定すること
2. メインキャラクター・世界観を反映すること
3. 商業的に訴求力を意識すること
4. 画像生成ツール（Stable Diffusion等）で使える形式にすること

{schema}
