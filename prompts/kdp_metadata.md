# KDP メタデータの生成

## 指示

以下のシリーズ企画と巻デザインから、KDP出版用のメタデータを生成せよ。

## 入力

- シリーズ企画: `{series_plan}`（テキスト形式）
- 巻デザイン: `{design}`（テキスト形式）
- 出力言語: `{lang}`

## 出力スキーマ

`kdp_metadata.json` に適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "title": "タイトル",
  "subtitle": "サブタイトル",
  "series_name": "シリーズ名",
  "description": "商品説明",
  "back_cover_text": "裏表紙テキスト",
  "target_audience": "ターゲット読者",
  "keywords": ["キーワード1", "キーワード2", "キーワード3"],
  "categories": ["カテゴリ1", "カテゴリ2"],
  "content_warnings": ["警告1"],
  "author_note": "著者ノート"
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- `keywords` は最大7件。
- `categories` はKDPのカテゴリ名から選択すること。

## 出力項目

- `title`: タイトル
- `subtitle`: サブタイトル
- `series_name`: シリーズ名
- `description`: 商品説明（100〜500字）
- `keywords`: 検索キーワード（最大7件）
- `categories`: KDPカテゴリ
- `back_cover_text`: 裏表紙テキスト
- `target_audience`: ターゲット読者
- `content_warnings`: コンテンツ警告
- `author_note`: 著者ノート
