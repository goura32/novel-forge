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

| オプション                    | デフォルト                          | 役割                        |
|------------------------------|-----------------------------------|-----------------------------|
| `--workdir, -w`            | `.`                              |系列の出力先               |
| `--model, -m`              | `qwen3.6:35b-a3b-mtp-q4_K_M`   | Ollama モデル名          |
| `--max-generation-count`   | 3                                 | 生成・バリデーションのリトライ最大数 |
| `--max-review-count`       | 7                                 | レビュー→修正サイクルの最大数    |
| `--verbose, -v`            |                                   | 詳細ログ出力                 |


> **注意**: `--strict` フラグは廃止済み。スキーマ validation failure で即座に停止します。

## 2 raw log とデバッグ

```bash
# シーンの raw log を /dir/raw_logs/ に書き出す
uv run novel-forge write -w <dir> --raw-log
```

| file | 内容                                          |
|------|---------------------------------------------|
| `_raw_logs/design/vol01/<ts>_*.jsonl`    | デザイン phase raw                          |
| `_raw_logs/text/<scene_id>/<ts>_*.jsonl` | scene write raw                             |
| `_raw_logs/review/<scene_id>/<ts>_review.json`   | review / revise output (JSON)     |

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

スキーマ違反で停止した場合 → raw log を見れば LLM が返した JSON データが残っています:

```bash
cat _raw_logs/review/<scene_id>/<ts>_review.json
```

`issues[].before / issues[].after` の差分を元に手動で修正するか、設計情報に問題があれば
スキーマやプロンプトテンプレートを更新後リトライします。


## 6 プロンプト placeholder 不整合時

```bash
uv run python scripts/validate_prompts.py
```

不一致の出力例:

```text
⚠️ {volume_title} → design.py (chapter_design) not found
```

→ `src/novel_forge/engine/design.py` で prompt variables (`prompt_vars`) に該当する変数を追加するか、テンプレート側の placeholder を修正してください。


## 7 lock エラー



| error                           |   action                                       |
|---------------------------------|--------------------------------------------------|
| stale lock (PID not found)      | `rm series_dir/.lock`                          |


```bash
# ロック状態の確認
cat <dir>/.lock.json
```
