# NovelForge

**NovelForge** は、ローカル Ollama モデルを使って小説シリーズを企画・構成・執筆・レビュー・改稿・出力する Python CLI ツールです。

KDP での商用出版を視野に入れ、LLM の出力揺れや能力不足をツール側で補う設計にしています。**シリーズ > 巻 > 章 > シーン** の階層で制作を管理します。

> **注意**: NovelForge は「出版保証ツール」ではありません。KDP 出版可能品質の最終判断は人間が行う前提です。

## セットアップ

```bash
cd /mnt/hdd/projects/novel-forge
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
uv run novel-forge review   --workdir ./work/series1 --volume 1
uv run novel-forge revise   --workdir ./work/series1 --volume 1
uv run novel-forge export   --workdir ./work/series1 --volume 1

# 次巻へ進む
uv run novel-forge next-volume --workdir ./work/series1

# 破損状態からの復旧
uv run novel-forge recover-state --workdir ./work/series1

# 中断・再開
uv run novel-forge status   --workdir ./work/series1
uv run novel-forge write    --workdir ./work/series1 --volume 1  # 未完了工程から再開
```

## 主要機能

- **シリーズ企画生成**: キーワードから世界観・キャラクター・構成案を生成
- **巻構成生成**: MVME `(S > A | R)` 構造的アンカーを適用したシーン目標
- **シーン本文生成**: Blackboard + Bible による継続性維持
- **シーンレビュー / 改稿 / 品質ゲート**: 多層的な自動検証
- **巻レビュー / 改稿**: 長文チャンク分割対応
- **KDP メタデータ生成**: タイトル案、内容紹介、カテゴリ、キーワード
- **Markdown / EPUB エクスポート**: KDP 確認用ドラフト
- **Blackboard**: 物語の事実を蓄積し、矛盾を検出
- **Bible**: キャラクター・用語・伏線・世界観ルールを管理
- **中断・再開**: state.json 永続化 + バックアップ復旧
- **RAW ログ**: 全 LLM リクエスト/レスポンスを保存

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | アーキテクチャ設計書（レイヤー構成、データフロー、記憶モデル） |
| [docs/SPECIFICATION.md](docs/SPECIFICATION.md) | 実装仕様書（プロジェクト構造、CLI コマンド、データモデル、コンポーネント） |
| [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) | セットアップガイド（環境構築、動作確認、トラブルシューティング） |

## テスト

```bash
uv run pytest -q        # 全テスト
uv run ruff check .     # lint
uv lock --offline --check  # ロックファイル整合性
```

## ライセンス

MIT
