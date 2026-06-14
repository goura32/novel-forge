# LLM実動作検証レポート

- 検証日時(UTC): 2026-06-10T04:41:43.318166+00:00 〜 2026-06-10T04:43:44.978163+00:00
- API URL: `http://ws1.local:11434/v1/chat/completions`
- モデル: `qwen3.6:35b-a3b-mtp-q4_K_M`
- クライアントタイムアウト想定: 3600秒

## 結果サマリー
- models_endpoint: status=200, elapsed=0.15s
- basic_connect_and_model_load: status=200, elapsed=17.69s, json_ok=False
- json_stability_1: status=200, elapsed=8.85s, json_ok=False
- json_stability_2: status=200, elapsed=7.93s, json_ok=False
- json_stability_3: status=200, elapsed=8.19s, json_ok=False
- schema_following_prompt_only: status=200, elapsed=13.30s, json_ok=False
- schema_following_response_format_json_object: status=200, elapsed=13.00s, json_ok=False
- long_input_long_output: status=200, elapsed=52.51s, json_ok=False
- client_timeout_0_001_sec: status=None, elapsed=0.00s, json_ok=None
- invalid_model_error: status=None, elapsed=0.02s, json_ok=None

## 観測事項

- 詳細RAWログは `workspace/logs/llm/probe/*.json` に保存した。
- JSON安定性は `json_ok` と parse_error を基準に評価した。
- `response_format={"type":"json_object"}` の効果も検証対象に含めた。
- タイムアウトはクライアント側で短時間タイムアウトを発生させ、例外形状を確認した。
- 不正モデル指定により、APIエラー形状を確認した。

## 実装方針への反映

- LLM応答は不正JSON・コードフェンス混入を前提に、抽出→JSON parse→スキーマ検証→修復リトライの順で処理する。
- OpenAI互換APIの `response_format` は利用可能なら送るが、プロンプト側の明示スキーマと後段検証を必須にする。
- 1時間タイムアウトを既定値にしつつ、RAWログに経過時間・例外・リトライ回数を必ず残す。
- モデルロード時間が長い前提で、小さなLLM呼び出しの大量分割を避け、階層ごとにまとまった設計生成を行う。
