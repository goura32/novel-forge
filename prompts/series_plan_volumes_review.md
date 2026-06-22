# シリーズ企画（各巻）のレビュー

## 指示
以下の各巻設計を評価し、改善点を指摘せよ。

## 各巻設計
{volumes}

## 評価基準

0. **必須フィールドの完全性** (`missing_field`)
   - 各巻に以下の必須フィールドがすべて含まれているか確認すること: title, premise, theme, emotional_arc, key_events, cliffhanger
   - **欠落フィールドがある場合**: severity=「重大」で issue を出力すること。category は `missing_field` とする
   - **出力例**: `{"severity": "重大", "category": "missing_field", "description": "第3巻「繋がる味と再生の板前」に必須フィールド「theme」「emotional_arc」「key_events」「cliffhanger」が欠落しています。", "affected_elements": ["第3巻"], "suggestion": [{"before": "(欠落)", "after": "各フィールドの具体的な記述"}]}`
   - すべてのフィールドが埋まっている場合は、このカテゴリの issue を出力しないこと

1. **巻の独自性** (`volume_uniqueness`)
   - 各巻が明確に異なる目的・テーマを持っているか
   - **減点要素**: 各巻のテーマが重複している、各巻の目的が不明確
   - **高評価要素**: 各巻が明確に異なるテーマ・目的を持っている

2. **シリーズ全体の流れ** (`series_flow`)
   - 巻間の連続性と変化があるか
   - **減点要素**: 巻間のつながりがない、変化が急激すぎる、同じパターンが繰り返される
   - **高評価要素**: 巻間で自然な連続性があり、かつ各巻で新しい展開がある

3. **クライフハンガー** (`cliffhanger`)
   - 次巻への引きがあるか（最終巻を除く）
   - **減点要素**: クライフハンガーがない（最終巻以外）、唐突な終わり方
   - **高評価要素**: 次巻を読みたくなる具体的な謎・危機・決断が提示されている

4. **テーマの一貫性** (`theme_consistency`)
   - シリーズのテーマと各巻のテーマが整合しているか
   - **減点要素**: シリーズテーマと各巻テーマが乖離している
   - **高評価要素**: 各巻のテーマがシリーズテーマを深めている

5. **巻間多様性** (`volume_diversity`)
   - 各巻が異なる危機・解決方法・感情の弧を持っているか
   - **減点要素**: 全巻で同じパターン（同じ危機・同じ解決策・同じ感情の弧）を繰り返している
   - **減点要素**: 巻の終わりが毎回同じパターン（例: 毎回「次巻への伏線」で終わる）
   - **高評価要素**: 各巻が固有の目的を持ち、物語が段階的に進展している
   - **重要**: 禁止パターンを確認すること。全巻で「料理で解決」「結界が軋む」「味覚が回復する」等の同じパターンが繰り返されている場合は severity=「重大」で指摘すること

## 出力

`series_plan_volumes_review.json` スキーマに適合する JSON を出力すること。

**以下のJSONテンプレートの構造とフィールド名を厳守すること。フィールド名や構造を変更しないこと。**

```json
{
  "volume_uniqueness": {
    "score": 85,
    "summary": "各巻は明確に異なるテーマ・目的を持っている。",
    "details": "第1巻は入門編、第2巻は対立編、第3巻は解決編と段階的な構成。"
  },
  "series_flow": {
    "score": 80,
    "summary": "巻間の連続性は概ね自然。ただし第2巻から第3巻の変化がやや急激。",
    "details": "第1巻のクライフハンガーが第2巻の冒頭に繋がしている。"
  },
  "cliffhanger": {
    "score": 75,
    "summary": "第1巻・第2巻のクライフハンガーは良好。最終巻は不要。",
    "details": "第2巻末尾の次巻への引きをさらに強化できる。"
  },
  "theme_consistency": {
    "score": 88,
    "summary": "シリーズテーマと各巻のテーマは整合している。",
    "details": "各巻が「遺伝子」というテーマを異なる角度で深めている。"
  },
  "issues": [
    {
      "severity": "重大",
      "category": "theme_consistency",
      "description": "第2巻のテーマがシリーズテーマと乖離している",
      "affected_elements": ["第2巻"],
      "suggestion": [{"before": "第2巻のテーマ（乖離する内容）", "after": "シリーズテーマに整合したテーマ"}]
    }
  ],
  "suggestions": ["各巻のテーマが重複しないように見直してください"],
  "revision_needed": true
}
```

**注意**:
- `volume_uniqueness`, `series_flow`, `cliffhanger`, `theme_consistency` は **オブジェクト** で出力すること。文字列は禁止。
- 各オブジェクトには `score` (0-100), `summary` (評価の要約), `details` (具体例) を含めること。
- `issues[].severity` は「重大」「重要」「軽微」から選択すること。

**必須**: スコアが 85 未満の場合、必ず `issues` に具体的な問題点を記述すること。問題点がない場合は、改善点を `suggestions` に記述すること。「問題なし」「良好」等の記述は禁止。具体的に何がどう問題かを記述すること。

## 改稿要否（revision_needed）の判定

`revision_needed` は以下の条件のいずれかに該当する場合のみ `true` とすること:

- 「重大」 issue が1つでもある → `true`
- 「重要」 issue が2つ以上ある → `true`
- 「軽微」 issue のみ、または issue なし → `false`
- 「重要」 issue が1つだけ → `false`

`revision_needed` は JSON のトップレベルフィールドとして出力すること。

## issues 出力ルール（厳守）

1. **1問題 = 1 issue**: 異なる問題は個別の issue 要素として列挙すること
2. **suggestion はペア配列**: 1つの issue に複数の修正箇所がある場合、`suggestion` の配列要素に分割すること。各要素は `before`（修正前）と `after`（修正後）を含むオブジェクト。
3. **affected_elements の明示**: 問題が特定の巻に関わる場合、`affected_elements` に該当巻番号を列挙すること
4. **重複禁止**: 同じ修正箇所への指摘を複数の issue で重複して出さないこと

**複数指摘事項の出力例:**
```json
{
  "issues": [
    {
      "severity": "重大",
      "category": "theme_consistency",
      "description": "第2巻のテーマがシリーズテーマと乖離している",
      "affected_elements": ["第2巻"],
      "suggestion": [{"before": "第2巻のテーマ（乖離する内容）", "after": "シリーズテーマに整合したテーマ"}]
    },
    {
      "severity": "重要",
      "category": "cliffhanger",
      "description": "第1巻のクライフハンガーがなく、次巻への引きが弱い",
      "affected_elements": ["第1巻"],
      "suggestion": [{"before": "第1巻の末尾（平坦な終わり）", "after": "次巻を読みたくなる具体的な謎・危機を追加"}]
    }
  ],
  "suggestions": ["各巻のテーマが重複しないように見直してください"],
  "revision_needed": true
}
```

言語: {lang}
