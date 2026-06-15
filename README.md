# NovelForge

**NovelForge** は、ローカル Ollama モデルを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

KDP での商用出版を視野に入れ、LLM の出力揺れや能力不足をツール側で補う設計にしています。**シリーズ > 巻 > 章 > シーン** の階層で制作を管理します。

> **注意**: NovelForge は「出版保証ツール」ではありません。KDP 出版可能品質の最終判断は人間が行う前提です。

## ドキュメント

### 運用ガイド

| ファイル | 内容 |
|---|---|
| [README.md](README.md) | このファイル。概要、セットアップ、クイックスタート |

### 設計書

| ファイル | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | アーキテクチャ設計（レイヤー構成、データフロー、記憶モデル） |
| [docs/SPECIFICATION.md](docs/SPECIFICATION.md) | 実装仕様（プロジェクト構造、データモデル、エラーハンドリング） |
| [docs/PIPELINE.md](docs/PIPELINE.md) | パイプライン設計（CLI コマンド、全コンポーネント、状態遷移） |
| [docs/PROMPTS.md](docs/PROMPTS.md) | プロンプト管理（一覧、レビュー/改稿の分離ルール） |

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
# 1巻を一括実行
uv run novel-forge complete "近未来東京 記憶探偵 亲子の和解" \
  --workdir ./work/series1 --volume 1

# 段階的に進める
uv run novel-forge plan     --workdir ./work/series1 --keywords "近未来東京 記憶探偵"
uv run novel-forge outline  --workdir ./work/series1 --volume 1
uv run novel-forge write    --workdir ./work/series1 --volume 1
uv run novel-forge export   --workdir ./work/series1 --volume 1

# 次巻へ進む
uv run novel-forge next-volume --workdir ./work/series1

# 破損状態からの復旧
uv run novel-forge recover --workdir ./work/series1

# 中断・再開
uv run novel-forge status   --workdir ./work/series1
uv run novel-forge resume   --workdir ./work/series1
```

## 主要機能

| 機能 | 説明 | 人間介入 |
|---|---|---|
| シリーズ企画 | キーワードから世界観・キャラクター・構成案を生成 | 確認（暗黙承認） |
| 巻アウトライン | MVME `(S > A | R)` 構造的アンカーを適用したシーン構成 | なし（LLM自律） |
| シーン執筆 | Blackboard + Bible による継続性維持 | なし（LLM自律） |
| 自律レビュー | 全工程 LLM が自己レビュー・改稿・品質ゲート | なし（LLM自律） |
| KDP メタデータ | タイトル案、内容紹介、カテゴリ、キーワード | なし（LLM自律） |
| Markdown エクスポート | 完成原稿の KDP 確認用出力 | なし |
| 最終レビュー | 全巻通読結果を kdp_readiness_report.md に記録 | 任意で確認 |

## テスト

```bash
uv run pytest -q        # 全テスト
uv run ruff check .     # lint
uv lock --offline --check  # ロックファイル整合性
```

## ライセンス

MIT
