# シリーズ企画（各巻）の改訂

## 役割
あなたは巻構成の改稿者です。レビュー結果に基づき、構成を修正します。

## 指示
以下のレビュー結果に基づいて、各巻設計を改訂せよ。

## 現在の各巻設計
{current_volumes}

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
- `affected_elements` に記載された巻番号を特定し、該当巻を重点的に修正すること
- 巻間の連続性、クライフハンガー、テーマの整合性を改善すること
- レビューで指摘されていない部分を勝手に変更しないこと

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SeriesPlanVolumesRevision",
  "description": "シリーズ企画（各巻）の改訂結果",
  "type": "object",
  "properties": {
    "planned_volumes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {
            "type": "string",
            "description": "巻タイトル（想定: 500文字）"
          },
          "premise": {
            "type": "string",
            "description": "巻のあらすじ（想定: 1000文字）"
          },
          "theme": {
            "type": "string",
            "description": "巻のテーマ（想定: 600文字）"
          },
          "emotional_arc": {
            "type": "string",
            "description": "巻全体の感情の弧（想定: 500文字）"
          },
          "key_events": {
            "type": "array",
            "items": {"type": "string"},
            "description": "巻内の主要イベント（1個以上、各想定: 200文字）"
          },
          "cliffhanger": {
            "type": "string",
            "description": "次巻へのフック（最終巻以外必須、想定: 1000文字）"
          }
        }
      }
    }
  },
  "required": ["planned_volumes"]
}
```
