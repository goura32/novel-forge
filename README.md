# NovelForge

NovelForge は、Ollama を使って小説シリーズを **企画 → 設計 → 執筆 → 出力** する Python CLI です。シリーズ、巻、章、シーンの階層で制作物を管理し、各生成工程で JSON Schema 検証とレビュー・改稿を行います。

> **出版品質は保証しません。** KDP などへの提出前に、原稿・メタデータ・準備完了レポートを人が確認してください。

## セットアップ

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
uv pip install -e .

# 任意: ローカル設定を固定する場合
cp config.example.yaml config.yaml
uv run novel-forge doctor
```

既定モデルは `qwen3.6:35b-a3b-mtp-q4_K_M` です。Ollama の接続先・モデル・品質上限は `config.yaml`、環境変数、CLI 引数で上書きできます。

## クイックスタート

```bash
# 段階実行
uv run novel-forge plan -w <workdir> "近未来東京 記憶探偵"
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
uv run novel-forge write -w <workdir> -s <series-slug> -V 1
# immutable JSON artifact（既定）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
# 人が読むためのMarkdown原稿
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown

# 一括実行
uv run novel-forge complete -w <workdir> "近未来東京 記憶探偵"
```

`plan` はシリーズ slug を生成します。以後の `design` / `write` / `export` では、複数シリーズを置く workdir なら `-s <series-slug>` を指定してください。

## 主なコマンド

| コマンド | 役割 |
|---|---|
| `plan` | キーワードからシリーズ企画を生成 |
| `design` | 巻・章・シーンの設計を生成 |
| `write` | シーン草稿を生成・レビュー・改稿 |
| `export` | selection snapshotをpinしたJSON artifact、または読者向けMarkdown原稿を出力 |
| `complete` | `plan → design → write → export` を実行 |
| `resume` / `status` | 中断地点からの再開 / 現在状態の表示 |
| `doctor` / `list` | Ollama 接続診断 / workdir 内シリーズ一覧 |

## ドキュメント

| 対象 | 読む文書 |
|---|---|
| 利用者 | [使い方](docs/USER_GUIDE.md) · [CLI リファレンス](docs/CLI_REFERENCE.md) · [運用 runbook](docs/OPERATIONS.md) |
| 開発者 | [アーキテクチャ](docs/dev/ARCHITECTURE.md) · [Prompt / Schema 対応](docs/PROMPT_SCHEMA_MAP.md) · [スキーマ保守](docs/dev/schema_maintenance.md) |
| Series Bible v2 実装 | [Canon Event Architecture](docs/dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) |
| 全体 | [ドキュメント索引](docs/INDEX.md) |

## 開発品質ゲート

```bash
uv run python scripts/check_dev_quality.py
# 配布物の build まで確認する場合
uv run python scripts/check_dev_quality.py --full
```

## Series Bible の状態

現在の runtime は v1 の `bible.json` / `blackboard.json` を使用します。将来の破壊的移行である Canon Event ベースの Series Bible v2 は、まだ実装されていません。v2 の唯一の仕様正本は [`SERIES_BIBLE_SCHEMA_REDESIGN.md`](docs/dev/SERIES_BIBLE_SCHEMA_REDESIGN.md) です。

## ライセンス

MIT
