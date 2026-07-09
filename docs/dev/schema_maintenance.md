# Schema / Prompt 変更時の検証

JSON Schema、prompt template、対応する Python のどれかを変更した場合は、三者を同じ変更単位で確認します。

## 必須手順

1. JSON を構文検査する。
   ```bash
   python -m json.tool schemas/<name>.json >/dev/null
   ```
2. prompt placeholder を検査する。
   ```bash
   uv run python scripts/validate_prompts.py
   ```
3. 関連する contract / unit test を実行する。
   ```bash
   uv run pytest tests/contract -q
   ```
4. 変更を含む品質ゲートを実行する。
   ```bash
   uv run python scripts/check_dev_quality.py
   ```

## ルール

- Schema は機械検証すべき構造・型・有限 enum・必要な整合制約を定義する。
- Prompt は各フィールドに何を書くか、品質基準、工程の責務を明示する。
- Review は対象 artifact と前工程の根拠に基づいて issue を出す。好み・根拠のない言い換えは issue にしない。
- Revision は issue を反映するが、未指摘 field を壊さない。
- `{schema}` は `PromptManager.render()` が対応 Schema から自動展開する。Python 側で `schema` 変数を渡さない。

Series Bible v2 の Schema は、実装開始後に Pydantic domain model の `model_json_schema()` から生成します。現行の `schemas/bible*.json` は v1 runtime の契約です。
