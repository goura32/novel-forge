# スキーマファイル修正時の再発防止チェックリスト

## 修正前の確認

1. `json.load()` でパース確認
   ```bash
   python -c "import json; json.load(open('schemas/series_plan_characters.json'))"
   ```

2. 全スキーマファイルの一括検証
   ```bash
   python scripts/validate_schemas.py
   ```

## 修正後の確認

1. 修正対象ファイルのパース確認
2. `validate_schemas.py` で全ファイル確認
3. `plan` コマンドで実動作確認（`--raw-log` 付き）

## よくある落とし穴

### trailing comma（末尾カンマ）

```json
// ❌ ダメ
{
  "maxItems": 5,
}

// ✅ 良い
{
  "maxItems": 5
}
```

LLM が生成した JSON に trailing comma が含まれることが多い。
`json.load()` はデフォルトで trailing comma を許可しない。

### プロンプトでの予防

スキーマ生成プロンプトに以下を追加：
- 「JSON の末尾に trailing comma（末尾カンマ）は含めないこと」
- 「有効な JSON のみを出力し、説明文は含めないこと」

### 自動修正

`json_parser.py` の `_fix_trailing_comma()` で LLM 出力の trailing comma
は自動修正されるが、スキーマファイル自体には適用されない。
スキーマファイルを手動修正した場合は必ず `json.load()` で確認すること。
