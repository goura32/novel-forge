# シリーズ企画（核）のレビュー

## 指示
以下のシリーズ企画の核を評価し、改善点を指摘せよ。

## シリーズ企画
{plan_text}

## 評価基準

1. **タイトルの力**: 覚えやすいか、検索しやすいか、商業的に魅力的か
2. **あらすじの質**: 明確か、読者の興味を引くか
3. **ジャンル適合**: ジャンルは適切か、競合と差別化されているか
4. **世界観の独自性**: オリジナルか、一貫したルールがあるか

## 出力スキーマ
`series_plan_core_review.json` に適合する JSON を出力すること。

**重要**: すべての `score` フィールドは **0-100の整数** で出力すること。小数点や100を超える値は禁止。

```json
{
  "title_power": {"memorable": true, "searchable": true, "score": 85},
  "logline_quality": {"clear": true, "compelling": true, "score": 80},
  "genre_fit": {"appropriate": true, "differentiated": true, "score": 75},
  "world_uniqueness": {"original": true, "consistent": true, "score": 90},
  "score": 82,
  "issues": [],
  "suggestions": ["改善提案1"]
}
```

言語: {lang}
