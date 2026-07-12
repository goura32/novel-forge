# 運用 runbook

## 通常の実行順

```bash
uv run novel-forge plan -w <workdir> "キーワード"
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
uv run novel-forge write -w <workdir> -s <series-slug> -V 1
# immutable JSON artifact（既定）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
# 人が読むためのMarkdown原稿
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown
```

一括実行には `complete` を使えます。複数シリーズがある workdir では、plan 後の command に必ず `-s <series-slug>` を渡してください。

## 中断・再開

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge resume -w <workdir> -s <series-slug>
```

write はシーンごとに状態を保存します。通信断や停止後は status を確認してから resume を実行してください。

## Ollama 接続不良

```bash
curl -fsS http://localhost:11434/api/tags >/dev/null && echo OK || echo FAIL
uv run novel-forge doctor -w <workdir>
uv run novel-forge doctor -w <workdir> --ollama-host <host:port>
```

モデル名・接続先は `config.yaml`、`NOVEL_FORGE_CONFIG`、CLI 引数で解決されます。優先順位は [使い方ガイド](USER_GUIDE.md#6-設定の優先順位) を参照してください。

## LLM 出力または schema validation の失敗

生成・JSON parse・schema / semantic validation の失敗は、`--max-generation-count` の上限まで再生成されます。上限に達した場合は、verbose で再実行して raw log を確認してください。

```bash
uv run novel-forge design -w <workdir> -s <series-slug> -V 1 -v
```

`-v` を指定した実行では、`<workdir>/_raw_logs/` に request / response の raw gzip と、人間向け summary が保存されます。形式は [RAW_LOG_FORMAT](dev/raw_log_format.md) を参照してください。

## レビューが収束しない

`--max-review-count` 到達時の扱いは工程により異なります。raw log の review 入出力を確認し、次を区別してください。

- schema / JSON の破損: prompt または schema / parser の問題
- 同じ根拠ある指摘の反復: prompt / revision の問題
- 根拠のない好みや no-op 指摘: review prompt または validator の問題

修正では raw request / response を先に確認し、プロンプト単体で期待出力を出せるかを判断してください。

## export の preflight 失敗

export は選択snapshotにpinされた対象巻の設計・Canon・全sceneのdraft / summary / final reviewを検証できない場合に停止します。

不足のあるsceneは `write` で処理してから export を再実行してください。`--format markdown` は同じ検証済み入力から読者向け本文を派生しますが、DOCX / EPUBを生成するものではありません。

## lock の問題

同一シリーズでは同時実行を避けてください。停止したプロセスの lock は runtime が stale と判定すれば回収します。残る場合はまず `status` と lock ファイルの PID を確認し、実行中プロセスがないことを確かめてから対処してください。

## 開発品質ゲート

```bash
uv run python scripts/check_dev_quality.py
# wheel build も含める場合
uv run python scripts/check_dev_quality.py --full
```

このスクリプトは pytest、ruff、mypy、prompt validator をまとめて実行します。
