# Schema / Prompt変更時の検証

JSON Schema、prompt template、対応するPython実行経路のどれかを変更した場合は、三者を同じ変更単位で確認します。

## 必須手順

1. JSONを構文検査する。
   ```bash
   python -m json.tool src/novel_forge/resources/schemas/<name>.json >/dev/null
   ```
2. prompt placeholderを検査する。
   ```bash
   uv run python scripts/validate_prompts.py
   ```
3. 関連するcontract / unit testを実行する。
   ```bash
   uv run pytest tests/contract -q
   ```
4. 品質ゲートを実行する。
   ```bash
   uv run python scripts/check_dev_quality.py
   ```

## ルール

- Schemaは機械検証すべき構造・型・有限enum・必須の整合制約を定義する
- Promptは各fieldに何を書くか、品質基準、工程責務を明示する
- Reviewは対象artifactと前工程の根拠に基づくissueを出す。好み・根拠のない言い換えはissueにしない
- Revisionはissueを反映するが、未指摘fieldを壊さない
- `{schema}` は `PromptManager.render_task()` が対応Schemaから自動注入する。Python側で `schema` 変数を渡さない
- 新taskはTaskRegistry、`workflow_task_runner._TASK_VARIABLES`、prompt、schema、runtime呼び出しを同時に追加する
- schemaのdescriptionはcontract testが要求する十分な説明文を持たせ、必須field変更時はfixtureも更新する

Scene designのCanon patch、selection snapshot、frontier replayの境界を変更する場合は、関連するruntime E2E testを先に失敗させてから実装します。
