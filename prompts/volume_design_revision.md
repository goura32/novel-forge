# 巻デザインの自己修正

## 役割
あなたは巻架構の改稿者です。レビュー結果に基づき、章構成を修正します。

## 指示
以下の巻デザインとレビュー結果に基づき、デザインを修正せよ。

## 入力
- 現在のデザイン: `{current_design}`
- レビュー結果: `{review}`
- シリーズ企画: `{series_plan}`
- 前巻デザイン: `{previous_design}`（第1巻の場合は空文字列）

## 修正指摘

### 修正順序（厳守）
1. `severity` が `致命的` の issue を最優先で修正すること
2. `severity` が `重大` の issue を必ず修正すること
3. `severity` が `重要` の issue を可能な限り修正すること
4. `severity` が `軽微` の issue は余力があれば修正すること

### 修正時の必須処理
- レビュー結果の `issues` 配列に含まれる**すべての issue** を確認すること
- 各 issue の `description` を読み、何が問題かを正確に理解すること
- 各 issue の `suggestion` 配列に記載された修正指示に**すべて**従うこと
- `affected_elements` に記載された章番号・シーンタイトルを特定し、該当箇所を重点的に修正すること
- レビューの `suggestions` も参考に、具体的に文言を修正すること
- 言語純度の問題（英語混在、簡体字、ハングル）は最優先で修正すること
- 英語の一般名詞・動詞・形容詞・副詞はすべて日本語に翻訳すること
- **章の役割（導入/展開/転換/クライマックス/収束）が明確であること。必ず「収束」の章を含めること。** レビューで収束章の欠如が指摘された場合は、収束章を追加すること
- 各シーンの outcome が次のシーンの goal に繋がっていること
- 前巻デザインが提供されている場合、前巻との整合性を保つこと（キャラクターの状態、伏線、サブプロットの進捗）
- レビューで指摘されていない部分を勝手に変更しないこと

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "VolumeDesignRevision",
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "巻タイトル"
    },
    "premise": {
      "type": "string",
      "description": "巻の前提"
    },
    "chapters": {
      "type": "array",
      "description": "章のリスト。1巻あたり4-8章が標準。3章以下は短すぎ、10章以上は長すぎ。",
      "items": {
        "type": "object",
        "required": [
          "title",
          "purpose"
        ],
        "properties": {
          "title": {
            "type": "string"
          },
          "purpose": {
            "type": "string",
            "enum": [
              "導入",
              "展開",
              "転換",
              "クライマックス",
              "収束"
            ],
            "description": "章の役割。日本語で指定: 導入/展開/転換/クライマックス/収束"
          },
          "scenes": {
            "type": "array",
            "description": "シーンのリスト。1章あたり2-4シーンが標準。",
            "items": {
              "type": "object",
              "required": [
                "title",
                "goal",
                "outcome"
              ],
              "properties": {
                "title": {
                  "type": "string"
                },
                "pov": {
                  "type": "string"
                },
                "goal": {
                  "type": "string"
                },
                "conflict": {
                  "type": "string"
                },
                "outcome": {
                  "type": "string"
                },
                "characters": {
                  "type": "array",
                  "items": {
                    "type": "string"
                  }
                },
                "key_events": {
                  "type": "array",
                  "items": {
                    "type": "string"
                  },
                  "description": "主要イベント"
                },
                "setting": {
                  "type": "string",
                  "description": "舞台設定"
                }
              }
            }
          }
        }
      }
    }
  },
  "required": [
    "chapters"
  ],
  "description": "LLMは chapters ごとに title, purpose, scenes を生成する。number と chapter_number は engine で機械採番されるため含めない。"
}
```
