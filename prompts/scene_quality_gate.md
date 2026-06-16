# シーン品質ゲート（合格/不合格判定）

## 注意

このプロンプトは参照用です。品質ゲート判定は `QualityGate.check_scene()` で実行されます。
LLM を呼び出す必要はありません。

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
