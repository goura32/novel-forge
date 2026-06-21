# シリーズ企画（各巻）の改訂

## 指示
以下のレビュー結果に基づいて、各巻設計を改訂せよ。

## 現在の各巻設計
{current_volumes}

## レビュー結果
{review}

## 改訂指示

### 修正順序（厳守）
1. `severity` が `blocker` の issue を最優先で修正すること
2. `severity` が `critical` の issue を必ず修正すること
3. `severity` が `major` の issue を可能な限り修正すること
4. `severity` が `minor` の issue は余力があれば修正すること

### 修正時の必須処理
- レビュー結果の `issues` 配列に含まれる**すべての issue** を確認すること
- 各 issue の `description` を読み、何が問題かを正確に理解すること
- 各 issue の `suggestion` 配列に記載された修正指示に**すべて**従うこと
- `affected_elements` に記載された巻番号を特定し、該当巻を重点的に修正すること
- 巻間の連続性、クライフハンガー、テーマの整合性を改善すること
- レビューで指摘されていない部分を勝手に変更しないこと
- 修正後も JSON Schema に適合すること

### changes フィールドの出力
修正内容を `changes` 配列に列挙すること。各要素は以下の形式:
- `"「[修正前の表現]」を「[修正後の表現]」に置換"`
- 複数の変更がある場合は、すべての変更を配列要素として列挙すること
- 各要素は100字以内に収めること

## 出力スキーマ
`series_plan_volumes_revision.json` に適合する JSON を出力すること。

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
  ],
  "changes": ["修正内容1", "修正内容2"]
}
```

言語: {lang}
