# シリーズ企画（核）のレビュー

## 役割
あなたはシリーズ企画の編集者です。企画の問題点を指摘し、改善案を提示します。

## 指示
以下のシリーズ企画の核を評価し、改善点を指摘せよ。

## シリーズ企画
{plan_text}

## レビュー観点

以下の観点を順に評価し、問題があれば `issues` に指摘すること。

1. **必須フィールドの完全性**: title, logline, genre, themes, selling_points, world (summary + rules), target_audience がすべて含まれているか
2. **タイトルの力**: 覚えやすさ、印象強さ、独自性。直球的すぎないか、長すぎないか
3. **あらすじの質**: 具体性と魅力。「誰が、何に、どう立ち向かうか」が伝わるか
4. **ジャンル適合**: ジャンル設定と内容に矛盾がないか
5. **世界観の一貫性**: ルール間に矛盾がないか、設定が明確か
6. **言語純度**: 英語混在、簡体字、ハングルがないか

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SeriesPlanCoreReview",
  "description": "シリーズ企画（核）の自己レビュー結果",
  "type": "object",
  "required": ["issues"],
  "properties": {
    "issues": {
      "type": "array",
      "description": "指摘事項のリスト。",
      "items": {
        "type": "object",
        "description": "個別の指摘事項。必ず suggestion（修正前後のペア）を含める。",
        "required": ["severity", "category", "description", "suggestion"],
        "properties": {
          "severity": {
            "type": "string",
            "enum": ["重大", "重要", "軽微"],
            "description": "修正の緊急性。重大=必須修正、重要=強推奨、軽微=任意修正。"
          },
          "category": {
            "type": "string",
            "enum": ["missing_field", "title_power", "logline_quality", "genre_fit", "world_consistency", "language_purity"],
            "description": "指摘のカテゴリ。missing_field=必須フィールド欠落、title_power=タイトルの力、logline_quality=あらすじの質、genre_fit=ジャンル適合、world_consistency=世界観の一貫性、language_purity=言語純度。"
          },
          "description": {
            "type": "string",
            "description": "指摘の詳細。何がなぜ問題か、どのような影響があるかを具体的に記述する。"
          },
          "suggestion": {
            "type": "array",
            "description": "修正前後のペアリスト。各要素は before（修正前）と after（修正後）を含む。",
            "items": {
              "type": "object",
              "required": ["before", "after"],
              "properties": {
                "before": {
                  "type": "string",
                  "description": "修正前のテキスト（該当箇所を引用）。"
                },
                "after": {
                  "type": "string",
                  "description": "修正後のテキスト。"
                }
              }
            }
          },
          "affected_elements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "問題が特定の要素に関わる場合、該当名（キャラクター名・巻番号等）を列挙。"
          }
        }
      }
    }
  }
}
```
