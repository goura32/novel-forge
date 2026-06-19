# Ollama API 仕様調査

2026-06-20 実施。qwen3.6:35b-a3b-mtp-q4_K_M モデルを使用。

## エンドポイント

### `/api/generate`（推奨）
- 現在の novel-forge が使用
- `think` / `format` / `options` すべてが正しく機能
- 構造化出力（`format: {schema}`）が安定

### `/v1/chat/completions`（OpenAI 互換）
- `response_format` はサポート
- `think` パラメータは **効かない**（`/api.generate` のみサポート）
- `reasoning` フィールドが常に返る（think 無効化しても）
- `extra_body.chat_template_kwargs.enable_thinking` も効かない
- `extra_body.options.think` も効かない

## パラメータマトリクス

### `/api/generate`

| パラメータ | 位置 | 必須 | 備考 |
|---|---|---|---|
| model | トップレベル | ✅ | |
| system | トップレベル | ✅ | |
| prompt | トップレベル | ✅ | |
| stream | トップレベル | ✅ | `false` 固定 |
| think | トップレベル | ✅ | qwen3.6 では `false` が必須 |
| format | トップレベル | schema使用時 | JSON schema オブジェクトを直接指定 |
| options | トップレベル | ✅ | num_ctx, num_predict 等 |

### `/v1/chat/completions`

| パラメータ | 位置 | 必須 | 備考 |
|---|---|---|---|
| model | トップレベル | ✅ | |
| messages | トップレベル | ✅ | OpenAI 形式 |
| stream | トップレベル | ✅ | `false` 固定 |
| think | トップレベル | ❌ | **効かない** |
| response_format | トップレベル | schema使用時 | `{"type": "json_object"}` または `{"type": "json_schema", "json_schema": {...}}` |
| extra_body | トップレベル | ❌ | chat_template_kwargs 経由でも think 無効化不可 |

## テスト結果

### 環境
- ホスト: ws1.local:11434
- モデル: qwen3.6:35b-a3b-mtp-q4_K_M
- num_ctx: 262144 (256K), num_predict: 32768 (32K)

### `/api/generate` テスト

| # | format | think | 結果 | 所要時間 |
|---|---|---|---|---|
| 1 | schema | false | ✅ 正常 | 17秒（短文）/ 76秒（長文4343文字） |
| 2 | schema | true | ❌ 空レスポンス | 9秒後に何も返らない |
| 3 | schema | options.think | ❌ 空レスポンス | options 内では効かない |
| 4 | json | false | ✅ 正常 | 1.3秒 |
| 5 | なし | false | ✅ 正常 | 1.2秒 |
| 6 | json | true | ❌ 空レスポンス | 15秒後に何も返らない |
| 7 | schema | false | ✅ 正常 | 76秒で4343文字（novel-forge 実サイズ） |

### `/v1/chat/completions` テスト

| # | think 指定方法 | response_format | 結果 |
|---|---|---|---|
| 1 | トップレベル `think: false` | json_object | ⚠️ content は正常だが reasoning に6363文字の思考プロセスが返る |
| 2 | トップレベル `think: false` | なし | ⚠️ 同上 |
| 3 | `extra_body.chat_template_kwargs.enable_thinking: false` | json_object | ⚠️ 効かない。reasoning が返る |
| 4 | `extra_body.options.think: false` | json_object | ⚠️ 効かない。reasoning が返る |

## 結論

### 推奨構成
```
/api/generate + think: false + format: {schema}
```

- qwen3.6 は think モデルのため、`think: false` が必須
- `think: true` との組み合わせは format 問わず長文で空レスポンス
- `format: schema` は `/api.generate` でのみ安定動作
- `options.think` は効かない。トップレベルの `think` フィールドが必須

### OpenAI 互換 API の制限
- `/v1/chat/completions` では `think` パラメータがサポートされていない
- `reasoning` フィールドが常に返るため、レスポンスパーサーの追加が必要
- 現在の novel-forge の `/api/generate` ベースの実装が最適

### 参考: vLLM/SGLang での think 無効化
- vLLM: `extra_body={"chat_template_kwargs": {"enable_thinking": false}}`
- SGLang: 起動パラメータで `--chat-template-kwargs '{"enable_thinking": false}'`
- Ollama ではこれらの方法は使えない

## 変更履歴
- 2026-06-20: 初版作成。全パターンのテスト結果を記録
