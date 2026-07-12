# NovelForge

NovelForge は Ollama を使い、シリーズ小説を **企画 → 設計 → 執筆 → 出力** する Python CLI です。すべての工程は immutable run / attempt / artifact と selection snapshot を使い、入力と出力の追跡可能性を保ちます。

> **出版品質は保証しません。** `export --format markdown` は読者向け原稿を作りますが、DOCX / EPUBやKDP提出用データは出力しません。提出前に人が原稿を整形・確認してください。

## セットアップ

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
uv pip install -e .

# 任意: canonical runtime設定を作成
mkdir -p ~/.config/novel-forge
cp config.example.yaml ~/.config/novel-forge/config.yaml
uv run novel-forge doctor
```

設定は `~/.config/novel-forge/config.yaml` だけを読みます。作業ディレクトリは各コマンドの `--workdir`、または設定の `workspace.root` で指定します。既定モデルは `qwen3.6:35b-a3b-mtp-q4_K_M` です。

## クイックスタート

```bash
# 段階実行
uv run novel-forge plan -w <workdir> "近未来東京 記憶探偵"
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
uv run novel-forge write -w <workdir> -s <series-slug> -V 1

# 監査用のimmutable JSON artifact（既定）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
# 読者向けMarkdown原稿
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown

# 新規シリーズを一括実行（JSON exportまで）
uv run novel-forge complete -w <workdir> "近未来東京 記憶探偵"
```

`plan` は series slug と最初のselection snapshotを作ります。以後の `design` / `write` / `export` / `resume` では `-s <series-slug>` を指定します。

## 主なコマンド

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画とCanon seedを生成 |
| `design` | 巻・章・scene設計を生成し、Canon frontierを更新 |
| `write` | scene草稿・レビュー・改稿・continuity summaryを生成 |
| `export` | snapshotをpinしたJSONまたはMarkdown manuscript artifactを出力 |
| `complete` | `plan → design → write → export` を新規シリーズに対して実行 |
| `resume` / `status` | 中断地点からの再開 / 現在のselection状態の表示 |
| `doctor` / `list` | Ollama接続診断 / workdir内シリーズ一覧 |
| `runs` / `run` / `attempt` | run・attemptの読み取り専用監査 |
| `llm` / `artifact` | LLM evidence・artifactの比較 |

## 成果物とLLM evidence

成果物と証跡は、固定ファイルを上書きせず次の配下へappend-onlyで保存されます。

```text
<workdir>/.novel-forge/
  runs/<run-id>/attempts/<attempt-id>/
    attempt.json
    artifacts/
    llm/
      request.json
      response.ndjson
      response.content.json
      parsed.json
      validation.json
```

`llm/` は `--verbose` の有無にかかわらず、LLMを呼んだattemptに保存されます。JSON/Schema validationに失敗したattemptでは、`parsed.json` がなく `validation.json` に失敗結果が残ることがあります。

## ドキュメント

| 対象 | 読む文書 |
|---|---|
| 利用者 | [使い方](docs/USER_GUIDE.md) · [CLIリファレンス](docs/CLI_REFERENCE.md) · [運用runbook](docs/OPERATIONS.md) |
| 開発者 | [アーキテクチャ](docs/dev/ARCHITECTURE.md) · [Prompt / Schema対応](docs/PROMPT_SCHEMA_MAP.md) · [LLM evidence形式](docs/dev/raw_log_format.md) · [スキーマ保守](docs/dev/schema_maintenance.md) |
| 全体 | [ドキュメント索引](docs/INDEX.md) |

## 開発品質ゲート

```bash
uv run python scripts/check_dev_quality.py
# 配布物のbuildも確認する場合
uv run python scripts/check_dev_quality.py --full
```

## ライセンス

MIT
