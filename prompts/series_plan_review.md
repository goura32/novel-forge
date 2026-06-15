# シリーズ企画の自己レビュー

## 指示

以下のシリーズ企画を評価し、改善点を指摘せよ。

## 入力

- シリーズ企画: `{series_plan}`
- 出力言語: `{lang}`

## 評価基準

1. **市場競争力**: 競合との差別化が明確か
2. **ターゲット適合**: 想定読者が具体的か
3. **シリーズ持続性**: 複数巻にわたる展開が見込めるか
4. **タイトル力**: 検索・宣伝に有効か
5. **キャッチコピー**: 読者の興味を引くか

## 出力スキーマ

`series_plan_review.json` に適合する JSON を出力すること。

## 出力形式

```json
{
  "overall_score": 0.0,
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "string",
      "description": "string",
      "suggestion": "string"
    }
  ],
  "strengths": ["string"],
  "recommendations": ["string"]
}
```
