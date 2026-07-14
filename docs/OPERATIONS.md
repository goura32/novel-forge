# 運用runbook

本番運用は合成コマンドを使わず、**plan → design → write → export** を個別の immutable run として実行します。各工程は開始時に selection snapshot を固定します。失敗した工程だけを調査・再実行でき、後から入力・LLM応答・内部状態を追跡できます。

## 標準フロー

```bash
# 1. 新規シリーズの Series Contract を作成・accept
uv run novel-forge plan -w <workdir> --volumes 3 "女性向けロマンスファンタジーのキーワード"

# 2. 対象巻を設計。--chapters を明示して設計量を固定する
uv run novel-forge design -w <workdir> -s <series-slug> -V 1 --chapters 3

# 3. snapshot に選択済みの scene を執筆・review・revision する
uv run novel-forge write -w <workdir> -s <series-slug> -V 1

# 4. export preflight を通した本文を Markdown として出力する
uv run novel-forge export -w <workdir> -s <series-slug> -V 1 --format markdown
```

`complete` コマンドは存在しません。合成実行では、どの工程・どの契約で失敗したか、どの snapshot を次工程へ渡したかが曖昧になるためです。

## 進捗と状態の確認

設計・執筆では `run.events.jsonl` に durable な `progress` event を記録します。chapter / scene ごとに `current` と `total`、phase、scope ID を保存するので、端末出力を失っても処理位置を復元できます。

```bash
uv run novel-forge status -w <workdir> -s <series-slug>
uv run novel-forge run show -w <workdir> <run-id>
uv run novel-forge attempt show -w <workdir> <attempt-id>
uv run novel-forge runs active -w <workdir>
```

中断後はまず `status` で selection snapshot と不足 artifact を確認します。plan / design をやり直さずに済む場合だけ、対象巻へ `resume` を実行します。`resume` は write + markdown export の再実行であり、明示的な監査用途では `write` と `export` を個別に実行する方が分かりやすいです。

## LLM evidence と失敗調査

実LLM呼出しごとに、呼出し**前**に evidence-only attempt を作成します。成功・失敗どちらでも attempt は終端化され、次の証跡が残ります。

```text
<workdir>/.novel-forge/runs/<run-id>/attempts/<attempt-id>/
  attempt.json
  completion.json              # 成功したLLM evidence attempt
  error.json                   # 失敗した場合
  llm/
    request.json               # secret をredactした送信payload
    response.ndjson            # providerのraw chunks
    response.content.json      # 結合応答
    parsed.json                # JSON parse成功時のみ
    validation.json            # passed / failed と error_code
```

JSON parse・schema validation・schema echo は、出力を補完・空文字化せず失敗として保存します。まず `request.json` と `response.content.json`、次に `validation.json` を読み、**prompt単体で期待JSONを返せるか**を判断してください。

```bash
uv run novel-forge llm diff -w <workdir> <attempt-a> <attempt-b>
```

## LLM既定値

canonical runtime config は `~/.config/novel-forge/config.yaml` です。リポジトリの `config.example.yaml` はコピー元、`config.yaml` は開発用の追跡テンプレートです。

```yaml
llm:
  ollama_options:
    temperature: 1.0
    top_p: 0.95
    top_k: 20
    min_p: 0.0
```

優先順位は CLI option > canonical config > built-in default です。`think` は Ollama の top-level payload へ分離して送信します。

## Ollama接続不良

```bash
curl -fsS http://<ollama-host>/api/tags >/dev/null && echo OK || echo FAIL
uv run novel-forge doctor -w <workdir>
uv run novel-forge doctor -w <workdir> --ollama-host <host:port>
```

## export preflight 失敗

export は selected snapshot に pin された設計・Canon・全 scene の draft / summary / final review を検証できない場合に停止します。欠けた scene は `write` で回復してから export を実行してください。

## lock

変更系コマンド（`plan` / `design` / `write` / `export` / `resume`）は workspace または series lock を取得します。同一シリーズへの並行実行は避けます。必要なら `--wait-lock` を付け、stale lock を疑う前に `runs active` と PID を確認します。

## 開発品質ゲート

```bash
uv run python scripts/check_dev_quality.py
# wheel buildも含める場合
uv run python scripts/check_dev_quality.py --full
```

このスクリプトは pytest、ruff、mypy、prompt validator をまとめて実行します。
