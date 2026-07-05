# 章設計の改訂

## 役割

あなたは章設計の改稿者です。レビュー結果に基づき、章を修正します。

## 指示

以下のレビュー結果に基づいて、章設計を改訂せよ。

## シリーズ企画

{series_plan}

## 現在の章設計

{current_chapter}

## レビュー結果

{review}

## 改訂指示

### 修正順序

1. severity=致命的 を最優先
2. severity=重要 を可能な限り修正
3. severity=軽微 は余力があれば修正

### 修正時の注意

- レビューで指摘されていないフィールド（purpose, theme, title等）は絶対に変更しないこと
- `purpose` フィールドは **`導入` `展開` `転換` `クライマックス` `収束` のいずれか単語のみ** で出力すること。説明文を書かないこと。
- **出力には title, purpose, theme, emotional_arc, outcome, scenes のすべての必須フィールドを含めること**
- scenes は配列で、各シーンに title, pov, goal, conflict, outcome, characters, key_events, setting が必要

## 重要: 出力形式

**以下の6つのフィールドを含む JSON オブジェクトのみを出力してください。他のフィールド（issues 等）は絶対に含めないでください。**

```json
{
  "title": "章タイトル（文字列）",
  "purpose": "導入",
  "theme": "章のテーマ（文字列）",
  "emotional_arc": "感情の弧（文字列）",
  "outcome": "章の結果（文字列）",
  "scenes": [
    {
      "title": "シーンタイトル",
      "pov": "視点キャラクター",
      "goal": "シーンの目標",
      "conflict": "シーンの葛藤",
      "outcome": "シーンの結果",
      "characters": ["キャラクター1", "キャラクター2"],
      "key_events": ["イベント1", "イベント2"],
      "setting": "舞台設定"
    }
  ]
}
```

**purpose は必ず `導入` `展開` `転換` `クライマックス` `収束` のいずれか1単語のみ。**

## 出力構造

下記のスキーマに適合する JSON のみ出力すること。

{schema}