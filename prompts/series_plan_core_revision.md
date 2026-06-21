# シリーズ企画（核）の改訂

## 指示
以下のレビュー結果に基づいて、シリーズ企画の核を改訂せよ。

## 現在の企画
{current_plan}

## レビュー結果
{review}

## 改訂指示
- レビューで指摘された問題をすべて解決すること
- タイトル、あらすじ、世界観を改善すること

## 出力スキーマ
`series_plan_core.json` に適合する JSON を出力すること。

```json
{
  "title": "シリーズタイトル",
  "logline": "あらすじ",
  "genre": ["ジャンル1"],
  "target_audience": "ターゲット読者",
  "themes": ["テーマ1"],
  "selling_points": ["売りポイント1"],
  "world": {
    "summary": "世界観の概要",
    "rules": ["ルール1"]
  }
}
```

言語: {lang}
