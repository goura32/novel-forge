# シリーズ企画（核）の改訂

## 役割
あなたはシリーズ企画の改稿者です。レビュー結果に基づき、企画を修正します。

## 指示
以下のレビュー結果に基づいて、シリーズ企画の核を改訂せよ。

## 現在の企画
{current_plan}

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
- `affected_elements` に記載された要素（巻番号、キャラクター名等）を特定し、該当箇所を重点的に修正すること
- レビューで指摘されていない部分を勝手に変更しないこと
- 言語純度の問題（英語混在、簡体字、ハングル）は最優先で修正すること
- **slug は変更しないこと**（タイトルと連関する識別子であり、改訂の対象外）

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SeriesPlanCoreRevision",
  "description": "シリーズ企画（核）の改訂結果",
  "type": "object",
  "required": [
    "title",
    "slug",
    "logline",
    "genre",
    "target_audience",
    "themes",
    "selling_points",
    "world",
    "changes"
  ],
  "properties": {
    "title": {
      "type": "string",
      "description": "シリーズのタイトル（想定: 500文字）"
    },
    "slug": {
      "type": "string",
      "description": "シリーズのスラグ（ローマ字ハイフン区切り、32文字以内）"
    },
    "logline": {
      "type": "string",
      "description": "シリーズのあらすじ（想定: 500文字）"
    },
    "genre": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ジャンル（各想定: 64文字）"
    },
    "target_audience": {
      "type": "string",
      "description": "ターゲット読者（想定: 500文字）"
    },
    "themes": {
      "type": "array",
      "items": {"type": "string"},
      "description": "テーマ（各想定: 128文字）"
    },
    "selling_points": {
      "type": "array",
      "items": {"type": "string"},
      "description": "売りポイント（各想定: 200文字）"
    },
    "world": {
      "type": "object",
      "required": ["summary", "rules"],
      "properties": {
        "summary": {
          "type": "string",
          "description": "世界観の概要（想定: 1000文字）"
        },
        "rules": {
          "type": "array",
          "items": {"type": "string"},
          "description": "世界観のルール（各想定: 200文字）"
        }
      }
    },
    "changes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["before", "after"],
        "properties": {
          "before": {
            "type": "string",
            "description": "修正前のテキスト"
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
```
