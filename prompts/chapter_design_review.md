# 章設計のレビュー

## 役割
あなたは章設計の編集者です。章の問題点を指摘し、改善案を提示します。

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

## 評価カテゴリ

- `missing_field`: 必須フィールドの完全性
  - 章設計に title, purpose, theme, emotional_arc が含まれているか確認すること
  - **欠落フィールドがある場合**: severity=「重大」で issue を出力すること。category は `missing_field` とする
  - すべてのフィールドが埋まっている場合は、このカテゴリの issue を出力しないこと

- `role_validity`: 章の役割（導入/展開/転換/クライマックス/収束）が明確か。巻全体の弧線の中で位置づけが適切か。
  - **減点要素**: 章の役割が不明確、巻全体の弧線の中で位置づけが不適切、クライマックスの章が短すぎる
  - **高評価要素**: 章の役割が明確、巻全体の弧線の中で適切に配置されている
  - **章番号とpurposeの整合性チェック**: 第1章は「導入」、最終章は「収束」であること。中間章は「展開」「転換」「クライマックス」のいずれかであること。第2章が「導入」の場合、severity=「重要」でissueを出力すること。

- `theme_coherence`: 章のテーマが明確か。シリーズのテーマと矛盾がないか。
  - **減点要素**: 章のテーマが不明確、シリーズテーマと矛盾している
  - **高評価要素**: 章のテーマが明確、シリーズテーマと整合している

- `emotional_arc_quality`: 感情の弧が存在するか。自然で説得力があるか。
  - **減点要素**: 感情の弧がない、感情の変化が唐突、感情が平板
  - **高評価要素**: 感情の弧が明確で自然、読者の感情を動かす

- `scene_distribution`: シーン配分について（章設計の段階ではシーン一覧は未設計であるため、シーン配分の評価は行わないこと。シーン一覧が空欄の場合、これは正常な状態であり、issue を出力してはならない）。シーン一覧が入力された場合のみ、シーン数が章の役割に適切か評価すること。

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
  "title": "ChapterDesignReview",
  "description": "章設計の自己レビュー結果",
  "type": "object",
  "required": ["issues"],
  "properties": {
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "severity",
          "category",
          "description",
          "affected_elements"
        ],
        "properties": {
          "severity": {
            "type": "string",
            "enum": [
              "重大",
              "重要",
              "軽微"
            ]
          },
          "category": {
            "type": "string",
            "description": "問題のカテゴリ名"
          },
          "description": {
            "type": "string",
            "description": "問題の説明"
          },
          "affected_elements": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "suggestion": {
            "type": "array",
            "items": {
              "type": "object",
              "required": [
                "before",
                "after"
              ],
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
