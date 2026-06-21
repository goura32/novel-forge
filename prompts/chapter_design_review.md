# 章設計のレビュー

## 指示
以下の章設計を評価し、改善点を指摘せよ。

## シリーズ企画
{series_plan}

## 巻情報
- 巻タイトル: {volume_title}
- 巻の前提: {volume_premise}

## 章設計
- 章番号: {chapter_number}
- 章タイトル: {chapter_title}
- 章の役割: {chapter_purpose}
- 章のテーマ: {chapter_theme}
- 章の感情の弧: {chapter_emotional_arc}
- 伏線メモ: {foreshadowing_notes}
- サブプロットメモ: {subplot_notes}

## 章のシーン一覧
{scene_list}

## 評価基準

1. **役割妥当性** (`role_validity`)
   - 章の役割（導入/展開/転換/クライマックス/収束）が明確か。巻全体の弧線の中で位置づけが適切か。
   - **減点要素**: 章の役割が不明確、巻全体の弧線の中で位置づけが不適切、クライマックスの章が短すぎる
   - **高評価要素**: 章の役割が明確、巻全体の弧線の中で適切に配置されている

2. **テーマ一貫性** (`theme_coherence`)
   - 章のテーマが明確か。シリーズのテーマと矛盾がないか。
   - **減点要素**: 章のテーマが不明確、シリーズテーマと矛盾している
   - **高評価要素**: 章のテーマが明確、シリーズテーマと整合している

3. **感情弧** (`emotional_arc_quality`)
   - 感情の弧が存在するか。自然で説得力があるか。
   - **減点要素**: 感情の弧がない、感情の変化が唐突、感情が平板
   - **高評価要素**: 感情の弧が明確で自然、読者の感情を動かす

4. **シーン配分** (`scene_distribution`)
   - シーン数が章の役割に適切か。シーンで章のテーマを十分にカバーしているか。
   - **減点要素**: シーン数が少なすぎる/多すぎる、シーンでテーマをカバーしていない
   - **高評価要素**: シーン数が適切、シーンでテーマを十分にカバーしている

## 出力

`chapter_design_review.json` スキーマに適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "role_validity": {
    "purpose_clear": false,
    "fits_volume_arc": false,
  },
  "theme_coherence": {
    "theme_clear": false,
    "consistent_with_series": false,
  },
  "emotional_arc_quality": {
    "arc_exists": false,
    "arc_believable": false,
  },
  "scene_distribution": {
    "count_appropriate": false,
    "coverage_sufficient": false,
  },
  "issues": [
    {
      "severity": "重大",
      "category": "カテゴリ名",
      "description": "問題の説明",
      "affected_elements": ["要素1"]
    }
  ],
  "suggestions": ["改善提案1"],
  "revision_needed": false
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- `issues[].severity` は「重大」「重要」「軽微」から選択すること。
- `issues[].category` は評価カテゴリ名から選択すること。
- `issues[].suggestion` は**オブジェクトの配列**であること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。

**suggestion 出力例:**
```json
{
  "severity": "重要",
  "category": "scene_distribution",
  "description": "シーン数が章の役割に比べて不足している",
  "affected_elements": ["第3章"],
  "suggestion": [{"before": "第3章のシーン数（2シーン）", "after": "第3章のシーン数（4シーン）"}]
}
```

**必須**: スコアが 85 未満の場合、必ず `issues` に具体的な問題点を記述すること。問題点がない場合は、改善点を `suggestions` に記述すること。「問題なし」「良好」等の記述は禁止。具体的に何がどう問題かを記述すること。

言語: {lang}
