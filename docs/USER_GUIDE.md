# USER_GUIDE — 使い方ガイド


## 0. はじめに

NovelForge は Ollama モデルを使って**小説シリーズの企画・構成・執筆・レビュー・出力**を自動化する Python CLI です。**"出版保証"**ではありませんが、LLM の出力揺れや能力不足をスキーマ validation / 自律レビューで補います。


## セットアップ

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
uv venv --python 3.14 .venv && uv pip install -e .
```

Ollama に `qwen3.6:35b-a3b-mtp-q4_K_M` がインストール済みであることを確認してください。


## モデル接続確認

```bash
uv run novel-forge doctor
```

✅ なら問題ありません。❌ なら Ollama が起動しているか、または `config.yaml / --model` を確認します。


## クイックスタート（一発完走）

```bash
uv run novel-forge complete -w <output_dir> "キーワード1 キーワード2"
```

これで plan → design → write → export が全工程実行されます。

ただし**段階的に進めたい場合**:

```bash
# 1. シリーズ企画
uv run novel-forge plan -w <dir> "近未来 Tokyo 記憶探偵"
...[truncated]