# シーン設計の改訂

## 指示
以下のレビュー結果に基づいて、シーン設計を改訂せよ。

## 現在のシーン設計
{current_design}

## レビュー結果
{review}

## 改訂指示
- レビューで指摘された問題をすべて解決すること
- 目標・結果の連貫性を改善すること
- 葛藤を強化すること

## 出力スキーマ
`scene_design_revision.json` に適合する JSON を出力すること。

```json
{
  "title": "シーンタイトル",
  "goal": "State: ... | Action: ...",
  "outcome": "結果",
  "conflict": "葛藤",
  "pov": "視点人物",
  "characters": ["キャラクター1"],
  "key_events": ["イベント1"],
  "setting": "舞台設定",
  "emotional_arc": "感情の弧"
}
```

言語: {lang}
