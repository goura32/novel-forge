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

## 出力

`series_plan_core_review.json` スキーマに適合する JSON を出力すること。

```json
{
  "issues": [
    {
      "severity": "重大",
      "category": "missing_field",
      "description": "問題の説明",
      "suggestion": [{"before": "修正前", "after": "修正後"}]
    }
  ]
}
```

**注意**:
- 上記テンプレートのキー名は変更しないこと。値のみを埋めること。
- **すべてのフィールドを必ず出力すること。省略禁止。**
- `issues[].severity` は「重大」「重要」「軽微」から選択すること。
- `issues[].suggestion` は**オブジェクトの配列**であること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。
- `category` は以下のいずれかから選択: missing_field, title_power, logline_quality, genre_fit, world_consistency, language_purity

**必須**: issue がない場合でも、具体的に改善点を記述すること。「問題なし」「良好」等の記述は禁止。

## issues 出力ルール（厳守）

11. **1問題 = 1 issue**: 異なる問題は個別の issue 要素として列挙すること
12. **suggestion はペア配列**: 1つの issue に複数の修正箇所がある場合、`suggestion` の配列要素に分割すること
13. **affected_elements の明示**: 問題が特定の巻・キャラクターに関わる場合、`affected_elements` に該当名を列挙すること
14. **重複禁止**: 同じ修正箇所への指摘を複数の issue で重複して出さないこと

**複数指摘事項の出力例:**
```json
{
  "issues": [
    {
      "severity": "重要",
      "category": "world_consistency",
      "description": "第3巻の前提がシリーズの世界観ルールと矛盾している",
      "affected_elements": ["第3巻"],
      "suggestion": [{"before": "第3巻の前提（矛盾する内容）", "after": "世界観ルールに整合した前提"}]
    },
    {
      "severity": "軽微",
      "category": "title_power",
      "description": "タイトルが直球的で印象に残りにくい",
      "suggestion": [{"before": "現在のタイトル", "after": "具体的なイメージを喚起するタイトル"}]
    }
  ],
  "revision_needed": true
}
```

言語: {lang}
