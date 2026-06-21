# Ollama API 仕様調査

2026-06-20 実施。qwen3.6:35b-a3b-mtp-q4_K_M モデルを使用。

## 採用設定（絶対）

```
API:      /api/chat（/generate ではない）
think:    true（必須）
format:   schema（JSON Schema オブジェクトを直接指定）
stream:   false
num_ctx:  262144
num_predict: -1（無制限）
timeout:  3600秒
seed:     42（リトライ時にインクリメント）
```

**理由:**
- `format=schema` + `think=true` で最も安定した構造化出力
- `think: false` は配列フィールドが空になる問題あり
- `num_predict: -1` で無制限出力（32768 も安定値）
- `num_ctx: 262144` は qwen3.6:35b の最大コンテキスト長

## エンドポイント

### `/api/chat`（採用）
- `think` / `format` / `options` すべてが正しく機能
- `format=schema` でネスト構造も正しく適用可能
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
| options | トップレベル | ✅ | num_ctx, num_predict 等 |

### options パラメータ

| パラメータ | 値 | 備考 |
|---|---|---|
| num_ctx | 262144 | qwen3.6:35b の最大値（auto-detect も可） |
| num_predict | 32768 | 出力トークン数上限（-1 = 無制限） |
| think | true | 思考モード（options 指定が優先） |

## テスト結果

### 環境
- ホスト: ws1.local:11434
- モデル: qwen3.6:35b-a3b-mtp-q4_K_M
- Ollama: 0.30.10

### `/api/chat` + `format=schema` + `think=true` テスト

| # | スキーマ | 結果 | 備考 |
|---|---|---|---|
| 1 | scene_draft (depth 3) | ✅ OK | 15.8s |
| 2 | scene_outline (depth 4) | ✅ OK | 3.3s |
| 3 | chapter_design (depth 4) | ✅ OK | 1.6s |
| 4 | scene_review (depth 7) | ✅ OK | 6.4s |
| 5 | series_plan (depth 8) | ✅ OK | 10.4s |
| 6 | volume_outline (depth 10) | ✅ OK | 15.9s |

### 配列フィールド安定性

| # | フィールド | 結果 | 備考 |
|---|---|---|---|
| 1 | characters (array of string) | ✅ 2-3 items | 全seedで安定 |
| 2 | key_events (array of string) | ✅ 3-4 items | 全seedで安定 |
| 3 | foreshadowing_notes (array of string) | ✅ 2+ items | 全seedで安定 |
| 4 | themes (array of string) | ✅ 1+ items | 全seedで安定 |

### 多seed安定性

| seed | volume_outline title | chapters | scenes | speed |
|------|---------------------|----------|--------|-------|
| 0 | 皇居外苑の黄昏に溶けて | 3 | 6 | 47s |
| 42 | 丸ノ内の黄金色 | 3 | 6 | 41s |
| 100 | 暮れゆく新宿の交差点 | 3 | 7 | 38s |

## 結論

### 推奨構成
```
/api/chat + think: true + format: schema + num_predict: 32768
```

- `format=schema` + `think=true` で最も安定
- 配列フィールドはプロンプトに「最低2つの要素を含める」と明示することで安定化
- ネスト構造（depth 10）でも正しく適用可能

### スキーマ設計ルール
- 配列にすべき項目は配列を使用（curl で動作確認済み）
- ネスト構造は `format=schema` + `think=true` で正しく適用可能
- スキーマ変更時は必ず curl で事前動作確認

## 変更履歴
- 2026-06-20: 初版作成。`/api/generate` ベース
- 2026-06-20: `/api/chat` ベースに更新。`think: true` + `format: schema` に統一
- 2026-06-20: 全19スキーマで動作確認完了。`num_predict: 32768`, `num_ctx: 262144` に更新
