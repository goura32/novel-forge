# 章設計の改訂

## 役割
あなたは章設計の改稿者です。レビュー結果に基づき、章を修正します。

## 指示
以下のレビュー結果に基づいて、章設計を改訂せよ。

## 現在の章設計
{current_design}

## レビュー結果
{review}

## 改訂指示

### 修正順序（厳守）
1. `severity` が `致命的` の issue を最優先で修正すること
2. `severity` が `重大` の issue を必ず修正すること
3. `severity` が `重要` の issue を可能な限り修正すること
4. `severity` が `軽微` の issue は余力があれば修正すること

### 修正時の必須処理
- レビュー結果の `issues` 配列に含まれる**すべての issue** を確認すること
- 各 issue の `description` を読み、何が問題かを正確に理解すること
- 各 issue の `suggestion` 配列に記載された修正指示に**すべて**従うこと
- `affected_elements` に記載されたシーン番号を特定し、該当シーンを重点的に修正すること
- 章の役割・テーマ・感情弧を改善すること
- シーン配分を見直すこと
- **レビューで指摘されていないフィールド（purpose, theme, title等）は絶対に変更しないこと。指摘されたissueに関連するフィールドのみを修正すること。**

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ChapterDesignRevision",
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "章タイトル"
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
      "description": "章の役割。物語全体におけるこの章の機能。"
    },
    "theme": {
      "type": "string",
      "description": "章のテーマ"
    },
    "emotional_arc": {
      "type": "string",
      "description": "感情の弧"
    },
    "foreshadowing_notes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "伏線メモのリスト"
    },
    "subplot_notes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "サブプロットメモのリスト"
    }
  },
  "required": [
    "title",
    "purpose",
    "theme",
    "emotional_arc"
  ],
  "description": "章の詳細設計。章の役割、テーマ、感情アーク、伏線・サブプロットの扱いを定義する。"
}
```
