# シリーズ企画（キャラクター）の改訂

## 指示
以下のレビュー結果に基づいて、キャラクター設計を改訂せよ。

## 現在のキャラクター設計
{current_characters}

## レビュー結果
{review}

## 改訂指示
- レビューで指摘された問題をすべて解決すること
- キャラクターの差別化、成長弧、世界観適合を改善すること

## 出力スキーマ
`series_plan_characters.json` に適合する JSON を出力すること。

```json
{
  "main_characters": [
    {
      "name": "キャラクター名",
      "role": "主人公",
      "arc": "成長の方向性",
      "gender": "男性",
      "age": "28歳",
      "occupation": "職業",
      "personality": "性格",
      "appearance": "外見",
      "background": "経歴",
      "motivation": "動機",
      "flaw": "欠点",
      "growth": "成長"
    }
  ]
}
```

言語: {lang}
