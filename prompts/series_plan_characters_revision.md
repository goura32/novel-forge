# シリーズ企画（キャラクター）の改訂

## 指示
以下のレビュー結果に基づいて、キャラクター設計を改訂せよ。

## 現在のキャラクター設計
{current_characters}

## レビュー結果
{review}

## 改訂指示

### 修正順序（厳守）
1. `severity` が `致命的` の issue を最優先で修正すること
2. `severity` が `重大` の issue を必ず修正すること
3. `severity` が `重要` の issue を可能な限り修正すること
4. `severity` が `軽微` の issue は余力があれば修正すること

### 修正時の必須処理
- レビュー結果の `issues` 配列に含まれる**すべての issue** を確認すること
- 各 issue の `description` を読み、何が問題かを正確に理解すること
- 各 issue の `suggestion` 配列に記載された修正指示に**すべて**従うこと
- `affected_elements` に記載されたキャラクター名を特定し、該当キャラクターを重点的に修正すること
- キャラクターの差別化、成長弧、世界観適合を改善すること
- レビューで指摘されていない部分を勝手に変更しないこと
- 修正後も JSON Schema に適合すること

### changes フィールドの出力（ペア形式）
修正内容を `changes` 配列に列挙すること。各要素は before（修正前）と after（修正後）を含むオブジェクト。
- `{"before": "修正前のテキスト", "after": "修正後のテキスト"}`
- 例: `"「主人公の性格」を「主人公の性格（修正後）」に置換"`
- 複数の変更がある場合は、すべての変更を配列要素として列挙すること
- 各要素は100字以内に収めること

## 出力スキーマ
`series_plan_characters_revision.json` に適合する JSON を出力すること。

```json
{
  "main_characters": [
    {
      "name": "キャラクター名",
      "role": "主人公",
      "arc": "成長の方向性（200文字以内）",
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
  ],
  "changes": ["修正内容1", "修正内容2"]
}
```

言語: {lang}
