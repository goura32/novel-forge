# 表紙画像生成プロンプト

## 役割
あなたは表紙デザイナーです。シリーズの内容を表す画像生成プロンプトを設計します.

## 指示

以下のシリーズ企画と巻デザインから、表紙画像を生成するためのプロンプトを生成せよ。

## 入力

- シリーズ企画: `{series_plan}`
- 巻デザイン: `{design}`
- 出力言語: `{lang}`

## 出力スキーマ

`cover_prompt.json` に適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "title": "作品タイトル",
  "visual_elements": {
    "subject": {
      "description": "メインビジュアルの詳細説明（英語、500文字以内）",
      "characters": [
        {
          "name": "キャラクター名（64文字以内）",
          "appearance": "外見（200文字以内）"
        }
      ]
    },
    "background": {
      "setting": "背景の場面説明（300文字以内）",
      "atmosphere": "雰囲気（200文字以内）"
    },
    "items": [
      {
        "name": "アイテム名（64文字以内）",
        "significance": "物語での意味（200文字以内）"
      }
    ]
  },
  "style": {
    "genre": "ジャンル（64文字以内）",
    "tone": "トーン（64文字以内）",
    "color_palette": ["#color1", "#color2", "#color3"],
    "composition": "portrait"
  },
  "negative_prompt": "除外したい要素（500文字以内）",
  "metadata": {
    "series_name": "シリーズ名（128文字以内）",
    "volume_number": 1,
    "target_audience": "ターゲット読者（50文字以内）"
  }
}
```

**注意**:
- `style.composition` は「portrait」「landscape」「action」「symbolic」「atmospheric」から選択すること。
- `visual_elements.subject.description` は英語の画像生成プロンプトとして記述すること。

## 出力項目

- `title`: タイトル
- `visual_elements`: ビジュアル要素（subject, background, items）
- `style`: スタイル指定（genre, tone, color_palette, composition）
- `negative_prompt`: ネガティブプロンプト
- `metadata`: メタデータ（series_name, volume_number, target_audience）

## プロンプト設計方針

1. ジャンルに適したビジュアルスタイルを指定すること
2. メインキャラクター・世界観を反映すること
3. 商業的に訴求力を意識すること
4. 画像生成ツール（Stable Diffusion等）で使える形式にすること
