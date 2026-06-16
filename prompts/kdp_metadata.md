# KDP メタデータの生成

## 指示

以下のシリーズ企画と巻アウトラインから、KDP出版用のメタデータを生成せよ。

## 入力

- シリーズ企画: `{series_plan}`（テキスト形式）
- 巻アウトライン: `{outline}`（テキスト形式）
- 出力言語: `{lang}`

## 出力スキーマ

`kdp_metadata.json` に適合する JSON を出力すること。

## 出力項目

- `title`: タイトル
- `subtitle`: サブタイトル
- `author`: 著者名（デフォルト: "NovelForge"）
- `description`: 商品説明（100〜500字）
- `keywords`: 検索キーワード（最大7件）
- `categories`: KDPカテゴリ
- `language`: 言語
- `is_adult`: アダルトコンテンツフラグ
