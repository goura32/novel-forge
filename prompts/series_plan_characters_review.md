# シリーズ企画（キャラクター）のレビュー

## 役割
あなたはキャラクター設計の編集者です。キャラクターの問題点を指摘し、改善案を提示します。

## 指示
以下のキャラクター設計を評価し、改善点を指摘せよ。

## キャラクター設計
{characters}

## 評価基準

0. **必須フィールドの完全性** (`missing_field`)
   - 各キャラクターに以下の必須フィールドがすべて含まれているか確認すること: name, role, personality, motivation, flaw, growth
   - **主要フィールド**（name, role, personality, motivation, flaw, growth）が欠落している場合: severity=「重大」
   - **補足フィールド**（gender, age, occupation, appearance, background, arc）が欠落している場合: severity=「重要」
   - すべてのフィールドが埋まっている場合は、このカテゴリの issue を出力しないこと

1. **設定一貫性** (`consistency`)
   - キャラクターの行動・性格が設定（性別、年齢、職業）と矛盾しないか
   - **減点要素**: 性格と行動が矛盾している、年齢に合わない言動、職業に合わない知識・技能
   - **高評価要素**: 設定が行動・性格・背景で一貫している

2. **キャラクター差別化** (`differentiation`)
   - 各キャラクターが明確に区別されているか
   - **減点要素**: キャラクター同士が似ている、口調・行動パターンが同じ、名前以外に違いがない
   - **高評価要素**: 各キャラクターに独自の口癖・行動特性・価値観がある
   - **重複キャラクターの検出**: `main_characters` 内に同じ名前のキャラクターが複数存在する場合、severity=「重大」で issue を出力すること。category は `differentiation` とする。description に「キャラクター「XXX」がN回重複しています。各キャラクターは異なる名前・性格・背景を持つように修正してください」と記載すること。

3. **成長弧** (`growth_arc`)
   - 各キャラクターに成長の方向性があるか
   - **減点要素**: 成長が不明確、変化がない、成長が唐突
   - **高評価要素**: 具体的な成長の方向性があり、物語のテーマと連動している

4. **世界観適合** (`world_fit`)
   - キャラクターが世界観に適合しているか
   - **減点要素**: 世界観のルールに合わない能力・知識、時代設定に合わない言動
   - **高評価要素**: 世界観の中で自然に存在するキャラクター

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
  "title": "SeriesPlanCharactersReview",
  "description": "シリーズ企画（キャラクター）の自己レビュー結果",
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
