# 巻デザインの自己レビュー

## 指示

以下の巻デザインを評価し、改善点を指摘せよ。

## 入力

- 巻デザイン: `{design}`（テキスト形式。シリーズ企画、タイトル、前提、章構成、シーン一覧を含む）
- 出力言語: `{lang}`

## 評価カテゴリ

- `missing_field`: 必須フィールドの完全性
  - 各章に title, purpose が含まれているか確認すること
  - 各シーンに title, goal, outcome が含まれているか確認すること
  - **欠落フィールドがある場合**: severity=「重大」で issue を出力すること。category は `missing_field` とする
  - すべてのフィールドが埋まっている場合は、このカテゴリの issue を出力しないこと

- `structural_validity`: 物語の弧（導入→展開→転換→クライマックス→収束）が明確か
  - **収束の章が必須**: 全章のpurposeに「収束」が1つでもない場合、`chapter_roles_valid` を `false` とすること。これは物語の弧が不完全なため。
  - **減点要素**: 導入が長すぎる（全体の40%以上）、クライマックスが短い（全体の10%以下）、収束がない
- `scene_coherence`: シーン間の論理一貫性があるか
  - **減点要素**: シーン間のつながりが不自然、時間軸に矛盾、キャラクターの状態が不連続
- `pace_analysis`: ペース配分が適切か
  - **減点要素**: 特定の章にシーンが偏っている、導入が長すぎる、クライマックスが短すぎる
- `character_arc_review`: キャラクターアークがあるか
  - `protagonist_has_arc`: 主人公に成長・変化の軌跡があるか（boolean）
  - `arc_believability`: アークの信頼性・自然さ（0-100の数値）。無理のない成長であれば高得点、唐突な変化は低得点
  - `supporting_chars_used`: 補助キャラクターが物語に機能しているか（boolean）
  - **減点要素**: 主人公の成長が不明確、唐突な変化、補助キャラクターが機能していない

## 深刻度

- 「重大」: 物語の根幹に関わる（論理的破綻、致命的な矛盾）
- 「重要」: 品質に大きく影響する（ペースの崩れ、キャラクターの不自然な行動）
- 「軽微」: 改善点としては望ましいが必須ではない

## 改稿要否（revision_needed）の判定

- 「重大」 issue が1つでもある → `true`
- 「重要」 issue が2つ以上ある → `true`
- 「軽微」 issue のみ、または issue なし → `false`
- 「重要」 issue が1つだけ → `false`

## 出力スキーマ

`volume_design_review.json` に適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "structural_validity": {
    "has_clear_arc": true,
    "chapter_roles_valid": true,
    "climax_placement_valid": true,
  },
  "scene_coherence": {
    "scene_transitions_valid": true,
    "no_contradictions": true,
    "state_continuity": true,
  },
  "pace_analysis": {
    "introduction_ratio": 20,
    "development_ratio": 40,
    "climax_ratio": 25,
    "pacing_comment": "ペースのコメント（500文字以内）",
  },
  "character_arc_review": {
    "protagonist_has_arc": true,
    "arc_believability": 85,
    "supporting_chars_used": true,
  },
  "issues": [
    {
      "severity": "重大",
      "category": "カテゴリ名（64文字以内）",
      "description": "問題の説明（500文字以内）",
      "affected_elements": ["要素1", "要素2"],
      "suggestion": [{"before": "修正前", "after": "修正後"}]
    }
  ],
  "revision_needed": false
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- **すべてのフィールドを必ず出力すること。省略禁止。** スキーマに存在するすべてのキーに対応する値を記述すること。
- `pace_analysis` の ratio は 0〜100 の数値。合計が 100 に収まるようにすること。
- `character_arc_review.arc_believability` は 0〜100 の数値。
- `issues[].severity` は「重大」「重要」「軽微」から選択すること。
- `issues[].suggestion` は**オブジェクトの配列**であること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。

**suggestion 出力例:**
```json
{
  "severity": "重大",
  "category": "structural_validity",
  "description": "収束の章が欠落している",
  "affected_elements": ["第5章"],
  "suggestion": [{"before": "第5章のpurpose「転換」", "after": "第5章のpurpose「収束」"}]
}
```

言語: {lang}