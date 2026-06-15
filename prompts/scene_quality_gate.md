# シーン品質ゲート（合格/不合格判定）

## 指示

以下のシーン本文とレビュー結果に基づき、品質ゲートの合格/不合格を判定せよ。

## 入力

- シーン本文: `{scene}`
- レビュー結果: `{review}`
- 出力言語: `{lang}`

## 合格基準

- `score >= 70.0` かつ `critical` issue が0件 → 合格
- それ以外 → 不合格

## 出力スキーマ

`scene_quality_gate.json` に適合する JSON を出力すること。

## 出力形式

```json
{
  "passed": true,
  "score": 0.0,
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "string",
      "description": "string"
    }
  ]
}
```
