# 巻アウトラインの自己レビュー

## 指示

以下の巻アウトラインを評価し、改善点を指摘せよ。

## 入力

- 巻アウトライン: `{outline}`（テキスト形式。シリーズ企画、タイトル、前提、章構成、シーン一覧を含む）
- 出力言語: `{lang}`

## 評価カテゴリ

- `structural_validity`: 物語の弧（導入→展開→転換→クライマックス→収束）が明確か
- `scene_coherence`: シーン間の論理一貫性があるか
- `pace_analysis`: ペース配分が適切か
- `character_arc_review`: キャラクターアークがあるか
  - `protagonist_has_arc`: 主人公に成長・変化の軌跡があるか（boolean）
  - `arc_believability`: アークの信頼性・自然さ（0-100の数値）。無理のない成長であれば高得点、唐突な変化は低得点
  - `supporting_chars_used`: 補助キャラクターが物語に機能しているか（boolean）
  - `score`: 上記を総合した 0-100 のスコア

## 深刻度

- `critical`: 物語の根幹に関わる（論理的破綻、致命的な矛盾）
- `major`: 品質に大きく影響する（ペースの崩れ、キャラクターの不自然な行動）
- `minor`: 改善点としては望ましいが必須ではない

## スコア制約

`score` は **0 以上 100 以下** の整数とすること。

**スコア計算ルール:**
- `score` = (`structural_validity.score` + `scene_coherence.score` + `pace_analysis.score` + `character_arc_review.score`) / 4
- 各サブスコアも 0〜100 の整数
- `critical` issue がある場合: `score` 最大 50
- `major` issue が 3 つ以上ある場合: `score` 最大 65
- `minor` issue のみの場合: `score` 最低 70

**スコアリングガイド:**
- **90-100**: 商業出版レベル。ほぼ問題なし
- **80-89**: 良好。軽微な改善点があるが、そのまま出版可能
- **70-79**: 合格ライン。いくつかの改善点があるが、全体的に読者を引き込む品質
- **60-69**: 改善が必要。複数の major issue がある
- **50-59**: 大幅な改善が必要
- **0-49**: 書き直しが必要

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
