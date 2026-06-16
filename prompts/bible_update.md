# Bible 更新

## あなたの役割
あなたはプロの小説編集者です。シーン本文を分析し、Bible（作品の世界観・キャラクター・伏線・サブプロット）を更新するための情報を抽出してください。

## シーン本文
{scene_text}

## 現在の Bible 情報
{current_bible}

## 抽出項目

以下の情報を JSON 形式で抽出してください：

### 1. 伏線 (foreshadowing)
- 本文内で新しく設置された伏線
- 本文内で回収された伏線（既存の伏線のうち、このシーンで解決したもの）
- 各伏線には「設置シーン番号」または「回収シーン番号」を含める

### 2. キャラクター更新 (characters)
- 既存キャラクターの性格・外見・動機の変化
- 新しく登場したキャラクター情報

### 3. キャラクター関係性変化 (relationships)
- キャラクター間の関係性に変化があった場合、その内容
- 関係性の種類（敵対・協力・恋愛・師弟など）と変化の方向（改善・悪化・変化なし）
- 関係性変化のトリガーとなった出来事

### 4. サブプロット進捗 (subplots)
- 進行中のサブプロットの進捗状況
- このシーンでサブプロットに進展があった場合、その内容
- サブプロットの状態（未開始 / 進行中 / 完了）

### 5. 用語 (glossary)
- 本文で新しく登場した固有名詞・専門用語
- 既存用語の定義変更

### 6. 世界観ルール (world_rules)
- 本文で明示された世界観のルール
- 既存ルールの変更や例外

### 7. 事実 (facts)
- 本文内で確定した事実（キャラクターが知っている情報、世界の状態など）

### 8. 引き継ぎメモ (continuity_notes)
- 次シーン以降で注意すべき連続性のポイント
- 未解決の緊張感や疑問

## 出力スキーマ

```json
{
  "foreshadowing": [
    {
      "id": "string",
      "description": "string",
      "type": "setup | resolution",
      "resolved": "boolean",
      "scene_number": "number"
    }
  ],
  "characters": [
    {
      "name": "string",
      "personality": "string",
      "appearance": "string",
      "motivation": "string",
      "arc": "string",
      "is_new": "boolean"
    }
  ],
  "relationships": [
    {
      "character_a": "string",
      "character_b": "string",
      "type": "string",
      "change_direction": "improved | worsened | changed | unchanged",
      "trigger_event": "string"
    }
  ],
  "subplots": [
    {
      "id": "string",
      "name": "string",
      "status": "not_started | in_progress | completed",
      "progress_note": "string"
    }
  ],
  "glossary": [
    {
      "term": "string",
      "definition": "string",
      "is_new": "boolean"
    }
  ],
  "world_rules": [
    {
      "rule": "string",
      "is_new": "boolean"
    }
  ],
  "facts": [
    {
      "subject": "string",
      "predicate": "string",
      "object": "string"
    }
  ],
  "continuity_notes": ["string"]
}
```

## ルール

1. 確実に本文に根拠がある情報のみ抽出する（推測しない）
2. 伏線の設置・回収は明示的に判断する（曖昧な場合は設置しない）
3. キャラクター関係性の変化は、本文内で明確に描写されている場合のみ抽出する
4. サブプロットの進捗は、本文内で具体的な進展があった場合のみ更新する
