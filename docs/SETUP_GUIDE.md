# NovelForge Setup Guide

## 1. 環境要件

| 要件 | バージョン | 備考 |
|---|---|---|
| Python | 3.14+ | `uv` 推奨 |
| Ollama | 0.14+ | OpenAI互換API有効化 |
| RAM | 16GB+ | モデルによる |
| GPU | 推奨 | qwen3.6:35b は VRAM 24GB+ |

## 2. セットアップ

### 2.1 リポジトリのクローン

```bash
cd /mnt/hdd/projects
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

## 3. 動作確認

### 3.1 モデル接続確認

```bash
uv run novel-forge probe-model
```

成功例:

```json
{
  "ok": true,
  "note": "モデル接続成功"
}
```

### 3.2 スモーク検証 (LLMなし)

```bash
uv run python scripts/make_smoke_workspace.py \
  --root /tmp/novel-forge-smoke --slug smoke-one-scene
uv run novel-forge export --workdir /tmp/novel-forge-smoke --slug smoke-one-scene
```

### 3.3 テスト実行

```bash
uv run pytest -q
uv run ruff check .
```

## 4. クイックスタート

```bash
# シリーズ企画 → 1巻 → 全工程を一括実行
uv run novel-forge complete "近未来東京 記憶探偵 親子の和解" \
  --workdir ./work/series1 --volume 1

# 段階的に進める場合
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

# 進捗確認
uv run novel-forge status   --workdir ./work/series1
```

## 5. トラブルシューティング

### `probe failed: LLM did not return valid JSON`

- モデルがJSON以外の文章を返した
- `thinking` モデルが推論欄に出力した
- 対処: `probe_logs/` を確認、別モデルを指定

### `LLM HTTP error 404`

- モデルが存在しない
- 対処: `ollama list` → `ollama pull <model>`

### `LLM request timed out after ...s`

- モデルが遅い、入力が大きい
- 対処: `--timeout` を増やす、`--max-scenes 1` でスモーク検証

### `volume review has major final review issues`

- 品質ゲートが正常に動作
- 対処: `volume_revised.md` を確認、必要に応じて `--force` で強制出力

### GPU OOM

```bash
# Ollama 再起動
systemctl restart ollama

# 小さいモデルに切替
uv run novel-forge complete "..." --model qwen3.6:27b
```

## 6. 開発コマンド

```bash
# テスト
uv run pytest -q

# Lint
uv run ruff check .

# ビルド
uv build

# ロックファイル整合性
uv lock --offline --check
```

## 7. セキュリティ

- `shell=True` / `os.system` 不使用
- `eval` / `exec` 不使用
- `pickle` 不使用
- パストラバーサル (`../`) 拒否
- ハードコードされたシークレットなし
- RAW ログには未公開原稿が含まれる → 取り扱い注意

---

*Last updated: 2026-06-15*
