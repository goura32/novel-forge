# シリーズ企画（各巻）の改訂

## 指示
以下のレビュー結果に基づいて、各巻設計を改訂せよ。

## 現在の各巻設計
{current_volumes}

## レビュー結果
{review}

## 改訂指示
- レビューで指摘された問題をすべて解決すること
- 巻間の連続性、クライフハンガー、テーマの整合性を改善すること

## 出力スキーマ
`series_plan_volumes.json` に適合する JSON を出力すること。

```json
{
  "planned_volumes": [
    {
      "title": "巻タイトル",
      "premise": "巻のあらすじ",
      "theme": "巻のテーマ",
      "emotional_arc": "感情の弧",
      "key_events": ["主要イベント1"],
      "cliffhanger": "次巻へのフック"
    }
  ]
}
```

言語: {lang}
