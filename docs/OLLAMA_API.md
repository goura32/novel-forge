# Ollama API 仕様調査

2026-06-20 実施。qwen3.6:35b-a3b-mtp-q4_K_M モデルを使用。

## 採用設定（絶対）

```
API:      /api/chat（/generate ではない）
think:    true（必須）
format:   json（schema ではない）
stream:   false
num_ctx:  262144
num_predict: 32768
seed:     42
timeout:  3600秒
```

**理由:**
- `format=schema` は Ollama 0.30.10 でネストされたオブジェクト構造を正しく適用できない
- `think: true` は LLM がスキーマをより正確に遵守できる
- `format=json` + Python 側バリデーションが最も安定

## エンドポイント

### `/api/chat`（採用）
- 現在の novel-forge が使用
- `think` / `format` / `options` すべてが正しく機能
- 配列内のオブジェクトも正しく適用可能

### `/api/generate`（非採用）
- 旧バージョンで使用。現在は非推奨
- `think: true` + `format: schema` で空レスポンス問題

### `/v1/chat/completions`（OpenAI 互換、非採用）
- `think` パラメータは **効かない**
- `reasoning` フィールドが常に返る

## パラメータマトリクス

### `/api/chat`

| パラメータ | 位置 | 必須 | 備考 |
|---|---|---|---|
| model | トップレベル | ✅ | |
| messages | トップレベル | ✅ | OpenAI 形式 |
| stream | トップレベル | ✅ | `false` 固定 |
| think | トップレベル | ✅ | qwen3.6 では `true` を採用 |
| format | トップレベル | schema使用時 | JSON schema オブジェクトを直接指定 |
| options | トップレベル | ✅ | num_ctx, num_predict, seed 等 |

## テスト結果

### 環境
- ホスト: ws1.local:11434
- モデル: qwen3.6:35b-a3b-mtp-q4_K_M
- Ollama: 0.30.10

### `/api/chat` + `format=schema` テスト

| # | スキーマ | think | 結果 | 備考 |
|---|---|---|---|---|
| 1 | フラット | true | ✅ 全フィールド適用 | ネストなし |
| 2 | ネスト | true | ⚠️ ネスト内フィールド欠落 | structural_validity.score 等 |
| 3 | ネスト | false | ❌ スキーマ無視 | 任意フィールド生成 |
| 4 | 配列内オブジェクト | true | ✅ 正しく適用 | |
| 5 | なし | true | ⚠️ プロンプト依存 | |

### `/api/chat` + `format=json` テスト

| # | think | 結果 | 備考 |
|---|---|---|---|
| 1 | true | ✅ プロンプト依存 | フィールド明示すればOK |
| 2 | false | ⚠️ スキーマ無視 | LLMが任意フィールド生成 |

### 配列テスト

| # | 内容 | 結果 |
|---|---|---|
| 1 | 文字列の配列 | ✅ `["red", "green", "blue"]` |
| 2 | オブジェクトの配列 | ✅ 各フィールド正しく適用 |

## 結論

### 推奨構成
```
/api/chat + think: true + format: json + Python側バリデーション
```

- `format=schema` はネスト構造でフィールド欠落が発生
- `think: true` でスキーマ遵守精度が向上
- `format=json` + Python 側バリデーションが最も安定
- 配列は正しく適用可能

### スキーマ設計ルール
- 配列にすべき項目は配列を使用（curl で動作確認済み）
- ネスト構造は `format=schema` で問題があるため、`format=json` 使用時は Python 側でバリデーション
- スキーマ変更時は必ず curl で事前動作確認

## 変更履歴
- 2026-06-20: 初版作成。`/api/generate` ベース
- 2026-06-20: `/api/chat` ベースに更新。`think: true` + `format: json` に統一
