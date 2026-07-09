# OPERATIONS — 運用 runbook


## 0 通常運用手順 ( plan → design → write → export )

```bash
uv run novel-forge plan    -w <dir> "keyword1 keyword2"
uv run novel-forge design  -w <dir> --volume 0   # —all volumes
uv run novel-forge write   -w <dir>
uv run novel-forge export  -w <dir>
```

`complete` を使えば全部一発:

```bash
uv run novel-forge complete -w <dir> "keyword1 keyword2"
```


## 1 オプション共通

| オプション                    | 省略時の解決                         | 役割                        |
|------------------------------|-----------------------------------|-----------------------------|
| `--workdir, -w`            | `.`                              | 系列の出力先 / `config.yaml` 探索起点 |
| `--model, -m`              | `config.yaml` → `qwen3.6:35b-a3b-mtp-q4_K_M` | Ollama モデル名          |
| `--max-generation-count`   | `config.yaml` → `4`              | 生成・バリデーションの最大試行数 |
| `--max-review-count`       | `config.yaml` → `4`              | レビュー→修正サイクルの最大数 |
| `--verbose, -v`            | `config.yaml` → `false`          | 詳細ログ出力                 |


省略時の優先順位は `CLI引数 > NOVEL_FORGE_CONFIG > --workdir/config.yaml > カレントディレクトリから親方向のconfig.yaml > built-in既定値` です。`config.yaml` が存在しなくても built-in 既定値で動作します。

> **注意**: `--strict` フラグは廃止済み。スキーマ validation failure で即座に停止します。

## 2 raw log とデバッグ

```bash
# LLM request/response の raw log と人間向けsummaryを書き出す
uv run novel-forge write -w <dir>
```

| path | 内容 |
|------|------|
| `_raw_logs/<phase>/<ts>_<pid>_<seq>_<kind>/summary.md` | 人間向け索引。詳細Markdownとgzip rawへのリンク |
| `_raw_logs/<phase>/<ts>_<pid>_<seq>_<kind>/summary/request_*.md` | API設定とprompt本文 |
| `_raw_logs/<phase>/<ts>_<pid>_<seq>_<kind>/summary/response_*.md` | `message.content` のみをJSON整形。`thinking` は含めない |
| `_raw_logs/<phase>/<ts>_<pid>_<seq>_<kind>/details/*.json.gz` | 完全な生request/response。thinking確認が必要な場合はこちらを展開 |

---


## 3 中断・再開

```bash
uv run novel-forge complete -w <dir> "keyword1"
# ⏸️ Ctrl-C or network error

uv run novel-forge status -w <dir>    # current state / latest step
uv run novel-forge resume   -w <dir>  # next step to resume
```


| ステータス      | 意味                                  |
|----------------|---------------------------------------|
| `PlanCreated` | 企画終了。次は design。                 |
| `DesignReady` | デザイン中 / design が完了              |
| `Writing`     | write フェーズ実行中                    |
| `DraftComplete` | 初稿完了。次は export                |


## 4 Ollama 接続失敗時

```bash
curl -s http://localhost:11434/api/tags > /dev/null && echo OK || echo FAIL
uv run novel-forge doctor
```

---


## 5 スキーマ validation failure 時

スキーマ違反で停止した場合 → 人間向けsummaryで LLM が返したJSONを確認できます:

```bash
less _raw_logs/<phase>/<ts>_<pid>_<seq>_<kind>/summary/response_*.md
# 完全な生NDJSONが必要な場合
gzip -dc _raw_logs/<phase>/<ts>_<pid>_<seq>_<kind>/details/response_*.json.gz
```

`issues[].before / issues[].after` はレビューの指摘内容（修正前後の差分例示）である。改訂は機械的な before→after 置換ではなく、LLM がレビュー全体を読んで文脈理解で柔軟に行う。指摘内容から設計情報・プロンプト・スキーマの改善点を抽出し、必要に応じて修正後にリトライする。


## 6 プロンプト placeholder 不整合時

```bash
uv run python scripts/validate_prompts.py
```

不一致の出力例:

```text
⚠️ {volume_title} → design.py (chapter_design) not found
```

→ `src/novel_forge/engine/design.py` で prompt variables (`prompt_vars`) に該当する変数を追加するか、テンプレート側の placeholder を修正してください。


## 7 開発用ローカル品質ゲート

CIは前提にせず、コミット前にローカルで同じゲートをまとめて実行します。

```bash
uv run python scripts/check_dev_quality.py
```

実行内容:

- `uv run pytest tests -q`
- `uv run ruff check src/novel_forge tests scripts`
- `uv run mypy src/novel_forge tests --show-error-codes`
- `uv run python scripts/validate_prompts.py`

配布物まで確認する場合:

```bash
uv run python scripts/check_dev_quality.py --full
```

`--full` は上記に加えて `uv build` を実行します。


## 8 設定ファイル

`config.example.yaml` をコピーしてローカル環境用に調整します。

```bash
cp config.example.yaml config.yaml
```

`NOVEL_FORGE_CONFIG=/path/to/config.yaml` を指定すると任意の設定ファイルを読めます。

設定探索順:

1. CLI引数
2. `NOVEL_FORGE_CONFIG`
3. `--workdir/config.yaml`（series dir指定時は親も確認）
4. カレントディレクトリから親方向の `config.yaml`
5. built-in 既定値

`config.yaml` が存在しない場合の主要built-in既定値は、`model=qwen3.6:35b-a3b-mtp-q4_K_M`, `ollama_host=ws1.local:11434`, `max_generation_count=3`, `max_review_count=8`, `raw_log=false` です。


## 9 lock エラー



| error                           |   action                                       |
|---------------------------------|--------------------------------------------------|
| stale lock (PID not found)      | `rm series_dir/.lock`                          |


```bash
# ロック状態の確認
cat <dir>/.lock.json
```
