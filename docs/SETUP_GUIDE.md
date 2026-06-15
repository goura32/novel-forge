# NovelForge Setup Guide

## 1. 環境要件

| 要件 | バージョン | 備考 |
|---|---|---|
| Python | 3.14+ | `uv` 推奨 |
| Ollama | 0.14+ | |
| RAM | 16GB+ | モデルによる |
| GPU | 推奨 | qwen3.6:35b は VRAM 24GB+ |

## 2. セットアップ

### 2.1 リポジトリのクローン

```bash
git clone https://github.com/goura32/novel-forge.git
cd novel-forge
```

### 2.2 仮想環境の作成

```bash
uv venv --python 3.14 .venv
source .venv/bin/activate
uv pip install -e .
```

### 2.3 Ollama モデルの準備

```bash
# 推奨モデル
ollama pull qwen3.6:35b-a3b-mtp-q4_K_M

# 確認
ollama list
```

GPU OOM の場合:

```bash
# 小さいモデルに切替
ollama pull qwen3.6:27b
# --model qwen3.6:27b を指定
```

## 3. LLM API 設定

### 3.1 API Endpoint

`/api/generate` を採用。

- `format: JSON Schema` + `think: false` で安定した構造化出力

### 3.2 プリウォーミング（モデル事前ロード）

```bash
curl -X POST http://ws1.local:11434/api/generate \
  -d '{"model":"qwen3.6:35b-a3b-mtp-q4_K_M","prompt":"","stream":false,"keep_alive":-1}'
```

- `keep_alive: -1` で GPU メモリに固定
- プリロードはツール起動時に1回だけ実行

### 3.3 タイムアウト設計

| 工程 | タイムアウト |
|---|---|
| プリロード（`keep_alive:-1`） | 30s |
| 短文生成（100字） | 60s |
| 中段生成（200字） | 60s |
| 長文生成（1000字） | 120s |
| 超長文（企画・構成） | 180s |

### 3.4 `think:true` + `format:json` の排他性

Ollama のアーキテクチャ上、`format: "json"` と `think: true` は排他的。JSON 出力が指定されると GBNF 文法制御により思考タグを生成できなくなる。**必ず `think: false` を使用すること**。

## 4. 動作確認

### 4.1 モデル接続確認

```bash
uv run novel-forge probe-model
```

成功例:

```json
{
  "ok": true,
  "model": "qwen3.6:35b-a3b-mtp-q4_K_M",
  "response_time_ms": 1234
}
```

### 4.2 スモーク検証 (LLMなし)

```bash
uv run python scripts/make_smoke_workspace.py \
  --root /tmp/novel-forge-smoke --slug smoke-one-scene
uv run novel-forge export --workdir /tmp/novel-forge-smoke --slug smoke-one-scene
```

### 4.3 テスト実行

```bash
uv run pytest -q
uv run ruff check .
```

## 5. クイックスタート

```bash
# シリーズ企画 → 1巻 → 全工程を一括実行
uv run novel-forge complete "近未来東京 記憶探偵 亲子の和解" \
  --workdir ./work/series1 --volume 1

# 段階的に進める場合
uv run novel-forge plan     --workdir ./work/series1 --keywords "近未来東京 記憶探偵"
uv run novel-forge outline  --workdir ./work/series1 --volume 1
uv run novel-forge write    --workdir ./work/series1 --volume 1
uv run novel-forge export   --workdir ./work/series1 --volume 1

# 次巻へ進む
uv run novel-forge next-volume --workdir ./work/series1

# 破損状態からの復旧
uv run novel-forge recover --workdir ./work/series1

# 進捗確認
uv run novel-forge status   --workdir ./work/series1

# 中断・再開
uv run novel-forge resume   --workdir ./work/series1
```

## 6. トラブルシューティング

### `probe failed: LLM did not return valid JSON`

- モデルが JSON 以外の文章を返した
- 対処: `probe_logs/` を確認。`/api/generate` + `format:"json"` + `think:false` を使用しているか確認

### `thinking` モデルが reasoning を返す

- Qwen 3.6 は `/v1/chat/completions` の `think:false` を無視して reasoning を返す場合がある
- **対処**: `/api/generate` エンドポイント + `think:false` + `format:"json"` を使用。`/v1/chat/completions` は使わない

### `LLM HTTP error 404`

- モデルが存在しない
- 対処: `ollama list` → `ollama pull <model>`

### `LLM request timed out after ...s`

- モデルが遅い、入力が大きい
- 対処: `--timeout` を増やす

### GPU OOM

```bash
# Ollama 再起動
systemctl restart ollama
```

### 品質ゲートで不合格が続く

- 対処: `.novel-forge/volumes/vol{N}/quality_reports/` を確認。`force_exported` フラグが立つと `--force` で出力可能

## 7. 設計書

詳細な仕様・設計については以下のドキュメントを参照してください。

| ファイル | 内容 |
|---|---|
| [README.md](README.md) | 概要、セットアップ、クイックスタート |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | アーキテクチャ設計（レイヤー構成、データフロー、記憶モデル） |
| [docs/SPECIFICATION.md](docs/SPECIFICATION.md) | 実装仕様（プロジェクト構造、データモデル、エラーハンドリング） |
| [docs/PIPELINE.md](docs/PIPELINE.md) | パイプライン設計（CLI コマンド、全コンポーネント） |
| [docs/PROMPTS.md](docs/PROMPTS.md) | プロンプト管理 |

## 8. セキュリティ

- `shell=True` / `os.system` 不使用
- `eval` / `exec` 不使用
- `pickle` 不使用
- パストラバーサル (`../`) 拒否
- ハードコードされたシークレットなし
- RAW ログには未公開原稿が含まれる → 共有しないこと

---

*Last updated: 2026-06-16*
