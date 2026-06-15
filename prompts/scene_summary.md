# シーン要約の生成

## 指示

以下のシーン本文から、事実記録（Blackboard）に格納する要約を生成せよ。

## 入力

- シーン本文: `{scene}`
- 出力言語: `{lang}`

## 要約の要件

1. シーン内の主要な事実（キャラクターの行動、状態変化、イベント）を抽出すること
2. 事実は `(subject, predicate, object, confidence)` の4-tuple 形式で記録すること
3. 伏線の設置・回収があれば記録すること
4. 次シーンへの引き継ぎ事項（continuity_notes）を抽出すること

## 出力スキーマ

`scene_summary.json` に適合する JSON を出力すること。

## 出力形式

```json
{
  "summary": "string",
  "facts": [
    {
      "subject": "string",
      "predicate": "string",
      "object": "string",
      "confidence": 0.0
    }
  ],
  "continuity_notes": ["string"],
  "foreshadowing": ["string"]
}
```
