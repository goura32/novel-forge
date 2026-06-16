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
- `scene_completeness`: シーン完結。本文が途中で切断されておらず、最後の文が完全な文であるか
- `language_purity`: 言語純度。英語・簡体字・ハングルが混入していないか。混入がある場合は severity=blocker とすること
- `pov_consistency`: POV 一貫性。視点人物がシーン内で切り替わっていないか。以下のチェックポイントを必ず確認すること:
  - 他キャラクターの内面（思考・感情・感覚）に直接立ち入っていないか
  - 視点人物が見聞きできない情報が描写されていないか
  - フィルター単語（「～と思った」「～と感じた」）を使って内面を推測していないか
  - 切り替わりがある場合は severity=critical とし、該当箇所を具体的に指摘すること

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
      "severity": "critical|major|minor|blocker",
      "category": "string",
      "description": "string",
      "suggestion": "具体的な修正指示を日本語で記述すること。修正箇所の該当テキストを引用し、どう変えるべきかを明示すること。"
    }
  ],
  "strengths": ["string"],
  "revision_needed": true
}
```

**重要**: `issue.suggestion` は具体的な記述にすること。「修正が必要」という曖昧な記述ではなく、**該当テキストを引用して「この部分を○○に変えよ」と明示すること**。例:
- ❌ 「英語表現を日本語に直してください」
- ✅ 「3行目の「weapon」を「兵器」に置換してください。15行目の「backdoor」を「裏口」に置換してください」
