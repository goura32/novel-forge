# シリーズ企画（各巻）のレビュー

## 役割
あなたは巻構成の編集者です。構成の問題点を指摘し、改善案を提示します。

## 指示
以下の各巻設計を評価し、改善点を指摘せよ。

## 各巻設計
{volumes}

## 評価基準

0. **必須フィールドの完全性** (`missing_field`)
   - 各巻に以下の必須フィールドがすべて含まれているか確認すること: title, premise, theme, emotional_arc, key_events, cliffhanger
   - **主要フィールド**（title, premise）が欠落している場合: severity=「重大」
   - **補足フィールド**（theme, emotional_arc, key_events, cliffhanger）が欠落している場合: severity=「重要」
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
   - **減点要素**: 全巻で同じパターン（同じ crisis ・同じ解決策・同じ感情の弧）を繰り返している
   - **減点要素**: 巻の終わりが毎回同じパターン（例: 毎回「次巻への伏線」で終わる）
   - **高評価要素**: 各巻が固有の目的を持ち、物語が段階的に進展している

## 改稿要否の判定

- 「重大」 issue が1つでもある → `true`
- 「重要」 issue が2つ以上ある → `true`
- 「軽微」 issue のみ、または issue なし → `false`
- 「重要」 issue が1つだけ → `false`

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SeriesPlanVolumesReview",
  "description": "シリーズ企画（各巻）の自己レビュー結果",
  "type": "object",
  "required": ["issues"],
  "properties": {
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "category", "description"],
        "properties": {
          "severity": {
            "type": "string",
            "enum": ["重大", "重要", "軽微"]
          },
          "category": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "suggestion": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["before", "after"],
              "properties": {
                "before": {
                  "type": "string",
                  "description": "修正前のテキスト（該当箇所を引用）"
                },
                "after": {
                  "type": "string",
                  "description": "修正後のテキスト"
                }
              }
            },
            "description": "修正前後のペアリスト。各要素は before（修正前）と after（修正後）を含むオブジェクト。"
          }
        }
      }
    }
  }
}
```
