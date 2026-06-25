# シーン設計の改訂

## 役割
あなたはシーン設計の改稿者です。レビュー結果に基づき、シーンを修正します。

## 指示
以下のレビュー結果に基づいて、シーン設計を改訂せよ。

## 現在のシーン設計
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
- 目標・結果の連貫性を改善すること
- 葛藤を強化すること
- レビューで指摘されていない部分を勝手に変更しないこと

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SceneDesignRevision",
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "シーンタイトル"
    },
    "goal": {
      "type": "string",
      "description": "シーン開始時の状況と主人公の行動"
    },
    "outcome": {
      "type": "string",
      "description": "シーン終了時の実際の結果"
    },
    "conflict": {
      "type": "string",
      "description": "シーン内の障害・対立"
    },
    "pov": {
      "type": "string",
      "description": "視点人物"
    },
    "characters": {
      "type": "array",
      "items": {"type": "string"},
      "description": "登場人物"
    },
    "key_events": {
      "type": "array",
      "items": {"type": "string"},
      "description": "主要イベント"
    },
    "setting": {
      "type": "string",
      "description": "舞台設定"
    }
  },
  "required": ["title", "goal", "outcome"],
  "description": "シーンの詳細設計。1シーン毎に生成される。デザインであり、シーンの目標・結果・葛藤・POV・キャラクター・キーイベント・設定を含む詳細設計書。"
}
```
