# NovelForge

**NovelForge** は、Ollama モデルを使って小説シリーズを企画・構成・執筆・レビュー・出力する Python CLI ツールです。

KDP での商用出版を視野に入れ、LLM の出力揺れや能力不足をツール側で補う設計にして
います。**シリーズ > 巻 > 章 > シーン** の階層で制作を管理します。

> **注意**: NovelForge は「出版保証ツール」ではありません。KDP 出版可能品質の最終判断は人間が行う前提です。

## インストール

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv && uv pip install -e .
```

Ollama に `qwen3.6:35b-a3b-mtp-q4_K_M` が存在することを確認してください。

## クイックスタート

```bash
# 段階的に進める（KEYWORDS はスペース区切り）
uv run novel-forge plan    --workdir <output_dir> "近未来東京 記憶探偵"
uv run novel-forge design  --workdir <output_dir>      # デフォルト vol.01
uv run novel-forge write   --workdir <output_dir>
uv run novel-forge export  --workdir <output_dir>

# 全工程を一度に実行（complete）
uv run novel-forge complete --workdir <output_dir> "キーワード"
```

詳細: [USER_GUIDE.md](docs/USER_GUIDE.md) | [CLI_REFERENCE.md](docs/CLI_REFERENCE.md)

## キーコマンド

| コマンド      | 役割                        |
|-------------|----------------------------|
| `plan`     | シリーズ企画を生成           |
| `design`   | 巻デザイン（章構成→章設計→シーン設計） |
| `write`    | シーン執筆                   |
| `export`   | KDP 用エクスポート            |
| `complete` | plan → design → write → export を一発実行 |
| `resume`   | 中断した工程から再開           |
| `status`   | プロジェクトのステータス表示      |
| `doctor`   | Ollama 接続とモデル確認         |
| `list`     | 利用可能なシリーズ一覧           |

## ドキュメント

| カテゴリ     | ファイル                              |
|------------|--------------------------------------|
| **利用者用**   | [INDEX](docs/INDEX.md) · [USER_GUIDE](docs/USER_GUIDE.md) · [CLI_REFERENCE](docs/CLI_REFERENCE.md) · [OPERATIONS](docs/OPERATIONS.md) |
| **開発者用**  | [ARCHITECTURE](docs/dev/ARCHITECTURE.md) · [MASTER_IMPROVEMENT_PLAN](docs/dev/MASTER_IMPROVEMENT_PLAN.md) |
| その他      | [GLOSSARY](docs/GLOSSARY.md) · [KEYWORD_GUIDE](docs/KEYWORD_SELECTION_GUIDE.md) |

## 品質ゲート

開発中のコミット前チェック:

```bash
uv run pytest tests -q
uv run ruff check src/novel_forge tests scripts
uv run python scripts/validate_prompts.py
```

## ライセンス

MIT
