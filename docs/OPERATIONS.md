# 運用runbook

## 通常の実行順

```bash
uv run novel-forge plan -w <workdir> "キーワード"
uv run novel-forge design -w <workdir> -s <series-slug> -V 1
uv run novel-forge write -w <workdir> -s <series-slug> -V 1
# immutable JSON artifact（既定）
uv run novel-forge export -w <workdir> -s <series-slug> -V 1
# 読者向けMarkdown原稿
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown
```

一括実行には `complete` を使えます。`complete` のexportはJSON既定のため、Markdownが必要なら完了後に明示的な `export --format markdown` を実行します。

## 中断・再開

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge resume -w <workdir> -s <series-slug>
uv run novel-forge runs active -w <workdir>
```

後続工程は開始時にselection snapshotを固定します。通信断や停止後は `status` で選択状態を確認し、`resume` を実行してください。

## Ollama接続不良

```bash
curl -fsS http://<ollama-host>/api/tags >/dev/null && echo OK || echo FAIL
uv run novel-forge doctor -w <workdir>
uv run novel-forge doctor -w <workdir> --ollama-host <host:port>
```

接続先・モデル・品質上限は `~/.config/novel-forge/config.yaml` で設定します。`--workdir` を省略する場合は同設定の `workspace.root` が必要です。

## LLM contract failureの調査

JSON parseまたはSchema validationの失敗は、`quality.max_retry_count` の上限まで別attemptとして再生成されます。transport errorは自動再試行せず、1件の失敗attemptを残して停止します。

LLM evidenceはverboseに関係なく、LLMを呼んだattemptに保存されます。

```text
<workdir>/.novel-forge/runs/<run-id>/attempts/<attempt-id>/llm/
  request.json
  response.ndjson
  response.content.json
  parsed.json
  validation.json
```

```bash
uv run novel-forge run show -w <workdir> <run-id>
uv run novel-forge attempt show -w <workdir> <attempt-id>
uv run novel-forge llm diff -w <workdir> <attempt-a> <attempt-b>
```

`parsed.json` はparse・Schema validationを通過した場合だけ保存されます。失敗時はraw request / responseと `validation.json` を先に確認し、prompt単体で期待する構造を出せるかを判断してください。

## レビューが収束しない

`--max-review-count` と `--max-summary-review-count` は、review → reviseサイクルの上限です。上限に達しても未解決issueを含む候補は選択されません。

- schema / JSONの破損: promptまたはschema / parserの問題
- 同じ根拠ある指摘の反復: prompt / revisionの問題
- 根拠のない好みやno-op指摘: review promptまたはvalidatorの問題

## exportのpreflight失敗

exportは選択snapshotにpinされた対象巻の設計・Canon・全sceneのdraft / summary / final reviewを検証できない場合に停止します。

不足のあるsceneは `write` で処理してからexportを再実行してください。`--format markdown` は同じ検証済み入力から読者向け本文を派生しますが、DOCX / EPUBを生成しません。

## lockの問題

変更系コマンド（`plan` / `design` / `write` / `export` / `resume` / `complete`）はworkspaceまたはseries lockを取得します。同一シリーズへの並行実行は避けてください。

lock待機が必要な場合は `--wait-lock` を付けます。停止プロセスのlockはruntimeがstale判定して回収します。残る場合は `runs active` とPIDを確認し、実行中プロセスがないことを確かめてから対処してください。

## 開発品質ゲート

```bash
uv run python scripts/check_dev_quality.py
# wheel buildも含める場合
uv run python scripts/check_dev_quality.py --full
```

このスクリプトはpytest、ruff、mypy、prompt validatorをまとめて実行します。
