# シリーズ企画（キャラクター）の改訂

## 役割
あなたはキャラクター設計の改稿者です。レビュー結果に基づき、キャラクターを修正します。

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
- **キャラクター名の重複を確認すること**: `main_characters` 内に同じ名前のキャラクターが複数存在する場合、それぞれを異なる名前・性格・背景のキャラクターに変更すること。重複キャラクターは許容されない。
- **役割の重複を禁止すること**: 各キャラクターは異なる役割を持つこと。2人以上が同じ役割にならないこと。
- **growth フィールドを空欄にしないこと**: すべてのキャラクターに成長の方向性を具体的に記述すること。
- **キャラクター数の最適化**: レビューで指摘された問題を解決するため、必要に応じてキャラクター数を増減すること。ただし、最低2人以上を維持すること。

## 出力スキーマ

以下の JSON スキーマに適合する JSON を出力すること。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SeriesPlanCharactersRevision",
  "description": "シリーズ企画（キャラクター）の改訂結果",
  "type": "object",
  "properties": {
    "main_characters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "キャラクター名（フルネーム、想定: 500文字）"
          },
          "role": {
            "type": "string",
            "description": "役割（例: 主人公、ヒロイン、相棒、敵対者、師匠、仲間等）"
          },
          "personality": {
            "type": "string",
            "description": "性格・特徴（想定: 1000文字）"
          },
          "motivation": {
            "type": "string",
            "description": "動機・目標（想定: 1000文字）"
          },
          "flaw": {
            "type": "string",
            "description": "欠点・弱み（想定: 1000文字）"
          },
          "arc": {
            "type": "string",
            "description": "シリーズを通じた成長・変化（想定: 600文字）"
          },
          "age": {
            "type": "string",
            "description": "年齢（例: 28歳、想定: 500文字）"
          },
          "occupation": {
            "type": "string",
            "description": "職業・立場（想定: 500文字）"
          },
          "appearance": {
            "type": "string",
            "description": "外見的特徴（想定: 500文字）"
          },
          "background": {
            "type": "string",
            "description": "過去・経歴（想定: 1000文字）"
          }
        }
      },
      "description": "メインキャラクター（2-5人）"
    }
  },
  "required": ["main_characters"]
}
```
