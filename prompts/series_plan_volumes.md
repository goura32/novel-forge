# シリーズ企画（各巻）の生成

## 指示
以下のシリーズ核とキャラクターに基づいて、各巻のタイトルと前提を設計せよ。

## シリーズ核
{core_text}

## メインキャラクター
{characters_text}

## 設計要件
- 各巻にタイトル、前提、テーマ、感情の弧、主要イベント、次巻へのフックを設定すること
- 巻全体でシリーズのテーマをカバーすること
- 各巻が独立した物語として完結しつつ、全体として大きなアークを形成すること

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

**注意**:
- `planned_volumes` は最低1個以上
- `key_events` は最低1個以上
- `cliffhanger` は最終巻以外必須

言語: {lang}
