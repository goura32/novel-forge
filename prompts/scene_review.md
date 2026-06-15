# シーンのレビュー

## 指示

以下のシーン本文を評価し、改善点を指摘せよ。本文の新規生成は指示しない。

## 入力

- シーン本文: `{scene}`
- 巻アウトライン: `{outline}`
- コンテキスト: `{context}`
- 出力言語: `{lang}`

## 評価カテゴリ

- `opening_hook`: 冒頭のフック。シーン1が読者を引き込む衝撃的な冒頭か
- `character_distinction`: キャラ立ち。キャラクターが行動とセリフで個性を示しているか
- `foreshadowing_consistency`: 伏線の整合性。仕込んだ伏線に矛盾はないか
- `sensory_coverage`: 五感の網羅。シーンに3つ以上の感覚描写が含まれているか
- `page_turner`: ページターナー。章末に次章を読みたくなる仕掛けがあるか
- `dialogue_naturalness`: 台詞の自然さ。キャラクター口調が一貫し、不自然な表現がないか
- `tone_consistency`: 文体統一。地の文の文体（ですます調）が一貫しているか

## 深刻度

- `critical`: 物語の根幹に関わる
- `major`: 品質に大きく影響する
- `minor`: 改善点としては望ましいが必須ではない

## 出力スキーマ

`scene_review.json` に適合する JSON を出力すること。

**重要**: `score` は 0 から 100 の数値で評価すること（10 段階ではない）。

## 出力形式

```json
{
  "score": 0.0,
  "dimensions": [
    {
      "name": "string",
      "score": 0.0
    }
  ],
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "string",
      "description": "string",
      "suggestion": "string"
    }
  ],
  "strengths": ["string"],
  "revision_needed": true
}
```
