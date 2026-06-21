# 章設計の改訂

## 指示
以下のレビュー結果に基づいて、章設計を改訂せよ。

## 現在の章設計
{current_design}

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
- `affected_elements` に記載されたシーン番号を特定し、該当シーンを重点的に修正すること
- 章の役割・テーマ・感情弧を改善すること
- シーン配分を見直すこと
- レビューで指摘されていない部分を勝手に変更しないこと
- 修正後も JSON Schema に適合すること

### changes フィールドの出力
修正内容を `changes` 配列に列挙すること。各要素は以下の形式:
- `"「[修正前の表現]」を「[修正後の表現]」に置換"`
- 複数の変更がある場合は、すべての変更を配列要素として列挙すること
- 各要素は100字以内に収めること

## 出力スキーマ
`chapter_design_revision.json` に適合する JSON を出力すること。

```json
{
  "title": "章タイトル",
  "purpose": "導入",
  "theme": "章のテーマ",
  "emotional_arc": "感情の弧",
  "foreshadowing_notes": ["伏線1"],
  "subplot_notes": ["サブプロット1"],
  "changes": ["修正内容1", "修正内容2"]
}
```

言語: {lang}
