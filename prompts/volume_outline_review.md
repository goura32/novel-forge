# 巻アウトラインの自己レビュー

## 指示

以下の巻アウトラインを評価し、改善点を指摘せよ。

## 入力

- 巻アウトライン: `{outline}`
- シリーズ企画: `{series_plan}`
- 出力言語: `{lang}`

## 評価カテゴリ

- `structural_validity`: 物語の弧（導入→展開→転換→クライマックス→収束）が明確か
- `scene_coherence`: シーン間の論理一貫性があるか
- `pace_analysis`: ペース配分が適切か
- `character_arc_review`: キャラクターアークがあるか

## 深刻度

- `critical`: 物語の根幹に関わる（論理的破綻、致命的な矛盾）
- `major`: 品質に大きく影響する（ペースの崩れ、キャラクターの不自然な行動）
- `minor`: 改善点としては望ましいが必須ではない

## 出力スキーマ

`volume_outline_review.json` に適合する JSON を出力すること。

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
  "has_clear_arc": true,
  "chapter_roles_valid": true,
  "climax_placement_valid": true,
  "scene_transitions_valid": true,
  "state_continuity": true
}
```
