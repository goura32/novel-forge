# NovelForge

**NovelForge** は、Ollama モデルを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

KDP での商用出版を視野に入れ、LLM の出力揺れや能力不足をツール側で補う設計にしています。**シリーズ > 巻 > 章 > シーン** の階層で制作を管理します。

> **注意**: NovelForge は「出版保証ツール」ではありません。KDP 出版可能品質の最終判断は人間が行う前提です。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/PIPELINE.md](docs/PIPELINE.md) | パイプライン設計（CLI コマンド、エンジン、状態遷移） |
| [docs/PROMPTS.md](docs/PROMPTS.md) | プロンプト管理（一覧、役割定義、言語制約） |
| [docs/dev/ARCHITECTURE.md](docs/dev/ARCHITECTURE.md) | アーキテクチャ設計（レイヤー構成、データフロー、記憶モデル） |
| [docs/dev/SPECIFICATION.md](docs/dev/SPECIFICATION.md) | 実装仕様（プロジェクト構造、データモデル、設定ファイル） |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 用語集 |

---

## セットアップ

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv
source .venv/bin/activate
uv pip install -e .
```

Ollama に `qwen3.6:35b-a3b-mtp-q4_K_M` が存在することを確認してください。

## モデル接続確認

```bash
uv run novel-forge probe-model
```

## クイックスタート

```bash
# 段階的に進める
uv run novel-forge plan    --workdir /mnt/hdd/novel --keywords "近未来東京 記憶探偵"
uv run novel-forge design  --workdir /mnt/hdd/novel
uv run novel-forge write   --workdir /mnt/hdd/novel
uv run novel-forge export  --workdir /mnt/hdd/novel

# 次巻へ進む
uv run novel-forge design  --workdir /mnt/hdd/novel --volume 2

# 中断・再開
uv run novel-forge status  --workdir /mnt/hdd/novel
uv run novel-forge resume  --workdir /mnt/hdd/novel
```

## 主要機能

| 機能 | 説明 | 人間介入 |
|---|---|---|
| シリーズ企画 | キーワードから世界観・キャラクター・構成案を生成 | 確認（暗黙承認） |
| 巻デザイン | 3フェーズ（章構成→章設計→シーン設計）で生成 | なし（LLM自律） |
| シーン執筆 | Blackboard + Bible による継続性維持 | なし（LLM自律） |
| 自律レビュー | 全工程 LLM が自己レビュー・改稿・品質ゲート | なし（LLM自律） |
| Bible 管理 | キャラクター、伏線、関係性、サブプロットの自動追跡 | なし（LLM自律） |
| KDP メタデータ | タイトル案、内容紹介、カテゴリ、キーワード | なし（LLM自律） |
| Markdown エクスポート | 完成原稿の KDP 確認用出力 | なし |
| 最終レビュー | 全巻通読結果を kdp_readiness_report.md に記録 | 任意で確認 |

## 排他制御

同一シリーズ内では `plan` / `design` / `write` / `export` / `resume` は同時に実行できません。

- `series_dir/.lock` ファイルで排他制御
- ロック保持プロセスが終了していたら自動回収（stale lock detection）
- 5分以上経過したロックも stale として強制取得
- `status` はロック不要（読み取り専用）

```bash
# 同時実行しようとすると即座にエラー
$ novel-forge write --workdir /mnt/hdd/novel
✗ Lock held by PID=12345 (active, 120s ago). Another process is running on this series.
  Wait for it to finish, or remove the lock file manually:
  rm /mnt/hdd/novel/.lock
```

## アーキテクチャ

```
cli.py → engine/ → scene_writer.py
                    → context_builder.py
                    → bible_manager.py
        → llm_client.py → json_parser.py
        → quality_gate.py
        → schemas.py
        → storage.py
```

- **CLI Interface** (`cli.py`): ユーザー対話、排他制御
- **NovelEngine** (`engine/`): オーケストレーション層（Mixin パターン）
- **SceneWriter** (`scene_writer.py`): シーン執筆パイプライン（draft/review/revise/summarize）
- **ContextBuilder** (`context_builder.py`): コンテキスト構築（Bible + Blackboard）
- **BibleManager** (`bible_manager.py`): Bible 管理（キャラクター、伏線、関係性、サブプロット）
- **LLMClient** (`llm_client.py`): LLM API 通信（リトライ、ログ、タイムアウト）
- **json_parser** (`json_parser.py`): JSON パース（8段階フォールバック）、型変換
- **QualityGate** (`quality_gate.py`): シーン品質評価、レビュースコア再計算

## テスト

```bash
uv run pytest tests/ -x -q   # 全テスト
uv run ruff check .          # lint
```

## ライセンス

MIT
